from io import BytesIO
from zipfile import ZipFile

import pandas as pd
from fastapi import APIRouter, Depends, Response, Request, HTTPException, UploadFile, File
from datetime import datetime, timedelta

from sqlalchemy import func, inspect
from starlette.responses import StreamingResponse

from admin.models import AdminSessionModel, AdminUserModel

from admin.utils import set_type, process_reviews_tasks_xlsx
from auth.models import UserModel, UserSessionModel
from orgs.repository import MembershipRepository
from payments.router import current_prices
from picker.models import PickerServerScheduleModel, PickerSettingsModel, PickerServerContractorModel, \
    PickerHistoryModel, PickerServerModel, PickerOrderStatus, PickerServerClientModel

from gutils import Strings
from database import Repository, AdminAuditLog
from orders.models import OrdersAddressModel, OrdersOrderModel, OrdersContractorModel, OrdersAccountModel, \
    OrderAddressStatusModel
from orgs.models import OrganizationModel, OrganizationMembershipModel
from payments.models import BalanceBillModel, BalanceSourceModel, BalancePricesModel, BalanceHistoryModel, \
    BalanceTargetModel, BalanceActionModel
from products.models import ProductModel, ReviewModel
from strings import *

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

tables_access = {
    'users': (UserModel, 4096, {}),
    'logs': (AdminAuditLog, 1048576, {}),
    'organizations': (OrganizationModel, 2048, {}),
    'organizations_full': (
        OrganizationModel, 2048,
        {
            'select_related': [OrganizationModel.owner, OrganizationModel.level, OrganizationModel.server],
            'filters': [OrganizationModel.status != 4]
        }
    ),
    'organizations_full_forced': (
        OrganizationModel, 2048,
        {
            'select_related': [OrganizationModel.owner, OrganizationModel.level, OrganizationModel.server],
        }
    ),
    'sizes': (ProductModel, 64, {}),
    'actions': (BalanceActionModel, 256, {}),
    'orgs': (OrganizationModel, 2048, {}),
    'bills': (BalanceBillModel, 256, {}),
    'balance': (BalanceHistoryModel, 256, {}),
    'orders': (OrdersOrderModel, 16, {}),
    'addresses': (OrdersAddressModel, 4, {}),
    'accounts': (OrdersAccountModel, 32, {'select_related': [OrdersAccountModel.address, OrdersAccountModel.server]}),
    'addresses_full': (OrdersAddressModel, 256, {'select_related': [OrdersAddressModel.contractor]}),
    'products': (ProductModel, 64, {}),
    'reviews': (ReviewModel, 128, {}),
    'admins': (AdminUserModel, 16384, {}),
    'usersessions': (UserSessionModel, 65536, {}),
    'usersessions_full': (
        UserSessionModel, 65536,
        {
            'select_related': [UserSessionModel.user]
        }
    ),
    'adminsessions_full': (
        AdminSessionModel, 131072,
        {
            'select_related': [AdminSessionModel.admin]
        }
    ),
    'adminsessions': (AdminSessionModel, 131072, {}),
    'contractors': (OrdersContractorModel, 8, {}),
    'pickerstatuses': (PickerOrderStatus, 2, {}),
    'banks': (BalanceSourceModel, 1024, {}),
    'prices': (BalancePricesModel, 512, {}),
    'schedules': (PickerServerScheduleModel, 524288, {}),
    'servercontractors': (PickerServerContractorModel, 8, {}),
    'pickersettings': (PickerSettingsModel, 2, {}),
    'pickerhistory': (PickerHistoryModel, 2, {}),
    'levels': (BalancePricesModel, 2048, {}),
    'members': (OrganizationMembershipModel, 2048, {}),

    'pickerorgs': (
        PickerServerClientModel, 2,
        {
            'select_related': [PickerServerClientModel.organization],
            'deep_related': [
                [PickerServerClientModel.organization, OrganizationModel.server],
            ]
        }
    ),

    'reviews_full': (
        ReviewModel, 128,
        {
            'select_related': [ReviewModel.media, ReviewModel.product],
            'deep_related': [
                [ReviewModel.product, ProductModel.organization]
            ]
        }
    ),
    'products_full': (
        ProductModel, 64,
        {
            'select_related': [ProductModel.organization]
        }
    ),
    'orders_full': (
        OrdersOrderModel, 16,
        {
            'select_related': [OrdersOrderModel.account, OrdersOrderModel.product],
            'deep_related': [
                [OrdersOrderModel.account, OrdersAccountModel.address],
                [OrdersOrderModel.product, ProductModel.organization]

            ]
        }
    ),

    'servers': (
        PickerServerModel, 1,
        {
            'prefetch_related': [
                PickerServerModel.schedule,
                PickerServerModel.contractors,
            ],
            'order_by': [PickerServerModel.id.asc()]
        }
    ),
    'bills_full': (
        BalanceBillModel, 256,
        {
            'select_related': [
                BalanceBillModel.organization,
                BalanceBillModel.source,
                BalanceBillModel.status,
            ]
        }
    ),
    'address_statuses': (OrderAddressStatusModel, 4, {}),
    'express_reviews': (
        ReviewModel, 128,
        {
            'filters': [
                ReviewModel.is_express.is_(True),
                ReviewModel.status.in_([1, 2])
            ]
        }
    ),

}


async def every(request: Request = Request):
    token = request.cookies.get(cookies_admin_token_key)

    if not token:
        return None

    sessions = await Repository.get_records(
        AdminSessionModel,
        filters=[AdminSessionModel.token == token, AdminSessionModel.expires > func.now()],
        select_related=[AdminSessionModel.admin]
    )

    if len(sessions) != 1:
        return None

    session = sessions[0]

    if not session or session.ip != request.client.host or session.user_agent != request.headers.get('user-agent'):
        return None

    if not session.admin.is_active:
        return None

    return session


async def authed(request: Request = Request):
    result = await every(request)
    if not result:
        raise HTTPException(status_code=401, detail=string_401)
    return result


async def not_authed(request: Request = Request):
    result = await every(request)
    if result:
        raise HTTPException(status_code=409, detail=string_409)
    return result


@router.post('/login')
async def login(request: Request, response: Response, username: str, password: str,
                session: AdminSessionModel = Depends(not_authed)):
    admin_check = await Repository.get_records(
        AdminUserModel,
        filters=[AdminUserModel.username == username.lower().replace(' ', '')]
    )

    if len(admin_check) != 1:
        raise HTTPException(status_code=403, detail=string_user_wrong_password)

    if Strings.hmac(password) != admin_check[0].password:
        raise HTTPException(status_code=403, detail=string_user_wrong_password)

    if not admin_check[0].is_active:
        raise HTTPException(status_code=403, detail=string_user_inactive_user)

    token = Strings.alphanumeric(256)
    await Repository.save_records([
        {
            'model': AdminSessionModel,
            'records': [
                {
                    'user_id': admin_check[0].id,
                    'token': token,
                    'user_agent': request.headers.get('user-agent'),
                    'ip': request.client.host,
                    'expires': datetime.now() + timedelta(days=3)
                }
            ]
        }
    ])

    response.set_cookie(key=cookies_admin_token_key, value=token)


@router.get('/logout')
async def logout(response: Response, session: AdminSessionModel = Depends(authed)):
    await Repository.save_records([
        {'model': AdminSessionModel, 'records': [{'id': session.id, 'expires': func.now()}]}
    ])
    response.delete_cookie(cookies_admin_token_key)


@router.get('/profile')
async def logout(response: Response, session: AdminSessionModel = Depends(authed)):
    data = session.admin.__dict__
    del data['password']
    return data


@router.get('/get/{section}')
async def reading_data(request: Request, section: str, session: AdminSessionModel = Depends(authed)):
    if not tables_access.get(section, None):
        raise HTTPException(status_code=404, detail=string_404)

    model, level, default_kwargs = tables_access[section]

    if not level & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    kwargs = default_kwargs.copy()
    params = request.query_params.multi_items()

    if params:
        filters = []
        for key, value in params:
            if key == 'limit':
                if int(value) > 0:
                    kwargs['limit'] = int(value)
            else:
                field = getattr(model, key)
                filters.append(field == set_type(value, str(field.type)))

        if kwargs.get('filters', None):
            kwargs['filters'] = kwargs['filters'] + filters

        else:
            kwargs['filters'] = filters

    records = await Repository.get_records(model, **kwargs)

    return [record.__dict__ for record in records]


@router.get('/fields/{section}')
async def reading_fields(section: str, session: AdminSessionModel = Depends(authed)):
    if not tables_access.get(section, None):
        raise HTTPException(status_code=404, detail=string_404)

    model, level, select_models = tables_access[section]

    if not level & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    mapper = inspect(model)
    fields = {}

    for column in mapper.columns:
        fields[column.name] = str(column.type)

    return fields


@router.post('/save')
async def creating_data(data: dict[str, list[dict]], request: Request, session: AdminSessionModel = Depends(authed)):
    models_with_typed_records = []

    for section in data:

        if not tables_access.get(section, None):
            raise HTTPException(status_code=404, detail=string_404)

        model, level, select_models = tables_access[section]

        if not level & session.admin.level:
            raise HTTPException(status_code=403, detail=string_403)

        mapper = inspect(model)
        model_fields = {}

        for column in mapper.columns:
            model_fields[column.name] = str(column.type)

        model_with_typed_records = []

        for record in data[section]:
            model_record_with_typed_values = {}
            for field, value in record.items():

                typed_value = set_type(value, model_fields[field])

                if field == 'password':
                    typed_value = Strings.hmac(str(typed_value))

                model_record_with_typed_values[field] = typed_value

            model_with_typed_records.append(model_record_with_typed_values)

        models_with_typed_records.append({
            'model': model,
            'records': model_with_typed_records
        })

    await Repository.save_records(models_with_typed_records, session_id=session.id, is_admin=True)


@router.delete('/delete/{section}/{record_id}')
async def reading_fields(section: str, record_id: int, session: AdminSessionModel = Depends(authed)):
    if not tables_access.get(section, None):
        raise HTTPException(status_code=404, detail=string_404)

    model, level, select_models = tables_access[section]

    if not level & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    await Repository.delete_record(model, record_id)


@router.post('/uploadBillMedia')
async def uploading_bill_media(bill_id: int, file: UploadFile = File(), session: AdminSessionModel = Depends(authed)):
    try:
        await Repository.verify_file(file, ['jpg', 'jpeg', 'png', 'webp', 'pdf', 'doc', 'docx', 'zip', 'rar'])

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")

    bills = await Repository.get_records(BalanceBillModel, filters=[BalanceBillModel.id == bill_id])

    if len(bills) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    bill = bills[0]

    content = await file.read()
    n, t = await Repository.s3_autosave(content,
                                        f"{Strings.alphanumeric(32)}.{file.filename.rsplit('.', maxsplit=1)[1]}")

    record = {'id': bill.id, 'media': f'{n}.{t}'}

    if bill.status_id == 6:
        record['status_id'] = 3

    await Repository.save_records([
        {'model': BalanceBillModel, 'records': [record]}
    ])


@router.get("/xlsxReviewsTasks")
async def download_xlsx_reviews(type: int, session: AdminSessionModel = Depends(authed)):
    if not 128 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    if type == 1:
        reviews = await Repository.get_records(
            ReviewModel,
            filters=[
                ReviewModel.status == 1,
                ReviewModel.is_express.is_(False),
                ReviewModel.stars == 5
            ],
            select_related=[
                ReviewModel.media,
                ReviewModel.product
            ],
            filtration=[
                ReviewModel.media == None,
                OrganizationModel.is_competitor == False,
            ],
            joins=[
                ProductModel,
                OrganizationModel
            ],
            deep_related=[
                [ReviewModel.product, ProductModel.organization]
            ]
        )

    elif type == 2:
        reviews = await Repository.get_records(
            ReviewModel,
            filters=[
                ReviewModel.status == 1,
                ReviewModel.is_express.is_(False),
                ReviewModel.stars == 1
            ],
            select_related=[
                ReviewModel.media,
                ReviewModel.product
            ],
            filtration=[
                ReviewModel.media == None,
                OrganizationModel.is_competitor == True,
            ],
            joins=[
                ProductModel,
                OrganizationModel
            ],
            deep_related=[
                [ReviewModel.product, ProductModel.organization]
            ]
        )

    else:
        raise HTTPException(status_code=403, detail=string_403)

    if len(reviews) == 0:
        raise HTTPException(status_code=415, detail=string_404)

    tasks = {}
    revs_to_update = reviews
    for review in reviews:
        if tasks.get(review.product.ozon_article):
            tasks[review.product.ozon_article].append(review)
        else:
            tasks[review.product.ozon_article] = [review]



    zip_file = BytesIO()
    with ZipFile(zip_file, 'w') as zip_archive:
        for article, reviews in tasks.items():
            excel_file = BytesIO()
            texts = []
            advs = []
            disadvs = []
            ids = []

            for review in reviews:
                texts.append(review.text if review.text else '')
                advs.append(review.advs if review.text else '')
                disadvs.append(review.disadvs if review.text else '')
                ids.append(review.id)

            data = {
                "Достоинства": advs,
                "Недостатки": disadvs,
                "Комментарий к отзыву": texts,
                "Пол": [''] * len(texts),
                "Размер": [''] * len(texts),
                "Фото": [''] * len(texts),
                "": [''] * len(texts),
                " ": [''] * len(texts),
                "Видео": [''] * len(texts),
                "Соответствие размеру": [''] * len(texts),
                "Аккаунт": [''] * len(texts),
                "Статус": [''] * len(texts),
                "Результат": [''] * len(texts),
                "Системный ID": ids
            }

            df = pd.DataFrame(data)
            df.to_excel(excel_file, index=False, sheet_name=article)
            excel_file.seek(0)
            zip_archive.writestr(f"{article}.xlsx", excel_file.getvalue())

    zip_file.seek(0)

    headers = {
        'Content-Disposition': f'attachment; filename=tasks.zip'
    }

    await Repository.save_records(
        [
            {
                'model': ReviewModel,
                'records': [{'id': review.id, 'status': 2} for review in revs_to_update]
            }
        ]
    )

    return StreamingResponse(zip_file, media_type='application/zip', headers=headers)


@router.post('/xlsxReviewsTasksPay')
async def get_reviews_of_organization(file: UploadFile = File(...), session: AdminSessionModel = Depends(authed)):
    if not 128 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    try:
        await Repository.verify_file(file, ['xlsx'])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")

    try:
        await process_reviews_tasks_xlsx(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")


@router.post('/updateReviewStatus')
async def update_review_status(review_id: int, status: int, session: AdminSessionModel = Depends(authed)):
    if not 128 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    reviews = await Repository.get_records(
        ReviewModel,
        filters=[
            ReviewModel.id == review_id
        ]
    )

    if len(reviews) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    review = reviews[0]

    if status not in [2, 4]:
        raise HTTPException(status_code=400, detail=string_400)

    if status == 2 and review.status != 1:
        raise HTTPException(status_code=400, detail=string_400)

    if status == 4 and review.status not in [1, 2]:
        raise HTTPException(status_code=400, detail=string_400)

    await Repository.save_records(
        [
            {
                'model': ReviewModel,
                'records': [{'id': review.id, 'status': status}]
            }
        ]
    )


@router.post('/payReview')
async def update_review_status(review_id: int, session: AdminSessionModel = Depends(authed)):
    if not 128 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    reviews = await Repository.get_records(
        ReviewModel,
        filters=[
            ReviewModel.id == review_id
        ],
        select_related=[ReviewModel.media, ReviewModel.product],
        deep_related=[
            [ReviewModel.product, ProductModel.organization]
        ]
    )

    if len(reviews) != 1:
        raise HTTPException(status_code=404, detail=string_404)
    review = reviews[0]

    if review.status != 2:
        raise HTTPException(status_code=400, detail=string_400)

    level, purchases = await current_prices(review.product.organization)

    price = level.price_review
    target_id = 7

    if review.media:
        price = level.price_review_media
        target_id = 5

    if review.is_express is True:
        price = level.price_review_request
        target_id = 6

    await Repository.save_records(
        [
            {
                'model': ReviewModel,
                'records': [
                    {
                        'id': review.id,
                        'status': 3
                    }
                ]
            },
            {
                'model': BalanceHistoryModel,
                'records': [
                    {
                        'amount': price,
                        'org_id': review.product.organization.id,
                        'target_id': target_id,
                        'record_id': review.id,
                        'action_id': 3
                    }
                ]
            }
        ]
    )

    target = await Repository.get_records(BalanceTargetModel, filters=[BalanceTargetModel.id == target_id])

    return f'{target[0].title} ({price} руб.)'


@router.get('/getPaymentsDetails')
async def create_organization(org_id: int, start: datetime, end: datetime,
                              session: AdminSessionModel = Depends(authed)):
    if not 2048 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

    history = await Repository.get_records(
        BalanceHistoryModel,
        filters=[
            BalanceHistoryModel.org_id == org_id,
            BalanceHistoryModel.date >= start,
            BalanceHistoryModel.date <= end,
        ]
    )

    return [record.__dict__ for record in history]


@router.get('/get_managers')
async def create_organization(org_id: int, session: AdminSessionModel = Depends(authed)):
    if not 128 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    records = await MembershipRepository.read_memberships_of_organization(org_id)

    return [record.__dict__ for record in records]


@router.get('/getBalance')
async def create_organization(org_id: int = None, session: AdminSessionModel = Depends(authed)):
    if not 2048 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    query = 'SELECT SUM(' \
            'CASE ' \
            'WHEN action_id IN (1, 4) THEN amount ' \
            'WHEN action_id IN (2, 3) THEN -amount ' \
            'ELSE 0 ' \
            'END) AS total_amount ' \
            'FROM balance_history '

    if org_id is not None:

        try:
            int(org_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=string_400)

        query += f'WHERE org_id = {org_id};'

    result = await Repository.execute_sql(query)

    return result[0][0]


@router.get('/getBalances')
async def create_organization(session: AdminSessionModel = Depends(authed)):
    if not 2048 & session.admin.level:
        raise HTTPException(status_code=403, detail=string_403)

    query = 'SELECT org_id,' \
            'SUM(' \
            'CASE ' \
            'WHEN action_id IN (1, 4) THEN amount ' \
            'WHEN action_id IN (2, 3) THEN -amount ' \
            'ELSE 0 ' \
            'END) AS balance ' \
            'FROM balance_history ' \
            'GROUP BY org_id;'

    result = await Repository.execute_sql(query)

    return {x[0]: x[1] for x in result}


# Forced saves
"""
async def force_save_product(wb_article, wb_title, wb_size_origName, wb_size_optionId, org_id):
    try:
        wb_url = f'https://www.wildberries.ru/catalog/{wb_article}/detail.aspx'

        title, p_article, sizes, picture_data = parse_wildberries_card(wb_url)

        filename = generate_filename() if picture_data else None

        await ProductsRepository.create_product(
            {
                'org_id': int(org_id),
                'wb_article': wb_article,
                'wb_title': wb_title,
                'status': 1,
                'media': filename + '.webp',
            },
            [size.model_dump() for size in sizes]
        )

        if picture_data:
            await s3_save(picture_data, filename, 'webp')

        return True

    except Exception as e:

        await ProductsRepository.create_product(
            {
                'org_id': int(org_id),
                'wb_article': wb_article,
                'wb_title': wb_title,
                'status': 1,
            },
            [{
                'wb_size_origName': wb_size_origName,
                'wb_size_optionId': wb_size_optionId,
                'wb_in_stock': False,
                'wb_price': None,
                'barcode': None,
                'is_active': True,
            }]
        )

        return False


async def force_save_order(x):
    db_sizes = await DefaultRepository.get_records(ProductSizeModel)
    db_products = await DefaultRepository.get_records(ProductModel)
    db_organizations = await DefaultRepository.get_records(OrganizationModel)

    df_products = pd.DataFrame([{'id': x.id, 'org_id': x.org_id, 'article': x.wb_article} for x in db_products])
    df_organizations = pd.DataFrame([{'id': x.id, 'title': x.title} for x in db_organizations])
    df_sizes = pd.DataFrame([{'id': x.id, 'product_id': x.product_id, 'wb_size_origName': x.wb_size_origName,
                              'wb_size_name': x.wb_size_name} for x in db_sizes])
    for xx in x:
        if force_save:

            query = df_organizations.query(f"title == '{line['organization_title']}'")
            organization_id = query['id'].iloc[0] if len(query.values) != 0 else None

            if not organization_id:
                logs_orders.append(
                    {
                        'target': line['order_uuid'],
                        'success': False,
                        'detail': 'Организация не найдена',
                        'value': line['organization_title'],
                        'line': line['line_number'],
                        'orders_type': orders_type,
                        'server': server.name,
                    }
                )
                continue

            query = df_products.query(f"article == '{line['product_article']}'")
            product_id = query['id'].iloc[0] if len(query.values) != 0 else None

            if not product_id:
                logs_orders.append(
                    {
                        'target': line['order_uuid'],
                        'success': False,
                        'detail': f'Товар не найден в списке товаров {line["organization_title"]}',
                        'value': line['product_article'],
                        'line': line['line_number'],
                        'orders_type': orders_type,
                        'server': server.name,
                    }
                )
                continue

            query = df_sizes.query(f'product_id == {product_id}')

            if len(query) == 0:
                logs_orders.append(
                    {
                        'target': line['order_uuid'],
                        'success': False,
                        'detail': f'Размеры товара не найдены',
                        'value': line['product_article'],
                        'line': line['line_number'],
                        'orders_type': orders_type,
                        'server': server.name,
                    }
                )
                continue

            size_id = query['id'].iloc[0]

            if len(query) != 1:
                for i, row in query.iterrows():
                    if (row['wb_size_origName'] == line['product_size'] or
                            row['wb_size_name'] == line['product_size']):
                        size_id = row['id']
                        break

            data_orders_to_db.append(
                {
                    'wb_keyword': line['product_title'],
                    'wb_price': int(line['price']),
                    'wb_uuid': line['order_uuid'],
                    'wb_status': line['status'],
                    'wb_collect_code': line['collect_code'],

                    'status': 3,
                    'description': 'forced',

                    'dt_planed': detect_date(line['dt_ordered']),
                    'dt_ordered': detect_date(line['dt_ordered']),
                    'dt_delivered': detect_date(line['dt_delivered']),
                    'dt_collected': detect_date(line['dt_collected']),

                    'size_id': int(size_id),
                    'account_id': int(account_id)
                }
            )

            logs_orders.append(
                {
                    'target': line['order_uuid'],
                    'success': True,
                    'detail': 'Заказ сохранен методом ForceSave',
                    'value': line['order_uuid'],
                    'line': line['line_number'],
                    'orders_type': orders_type,
                    'server': server.name,
                }
            )
            continue

"""
