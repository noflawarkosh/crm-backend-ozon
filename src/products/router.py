import datetime
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import func

from admin.models import CrmSettingsModel
from auth.models import UserSessionModel
from auth.router import authed
from database import Repository
from gutils import Strings
from orgs.models import OrganizationModel

from orgs.router import check_access
from products.models import ProductModel, ReviewModel, ReviewMediaModel
from products.repository import ReviewsRepository
from products.schemas import ProductPOSTSchema, ProductReadSchema, ProductCreateSchema, ReviewCreateSchema, \
    ReviewReadSchema, ReviewUpdateSchema

from products.utils import process_reviews_xlsx, parse_ozon_card

from strings import *

router_products = APIRouter(
    prefix="/products",
    tags=["Products"]
)

router_reviews = APIRouter(
    prefix="/reviews",
    tags=["Reviews"]
)


@router_products.post('/create')
async def create_product(data: Annotated[ProductPOSTSchema, Depends()], session: UserSessionModel = Depends(authed)):
    organization, membership = await check_access(data.org_id, session.user.id, 2)

    crm_settings = await Repository.get_records(
        CrmSettingsModel,
        filters=[CrmSettingsModel.id == 1]
    )

    cookies = crm_settings[0].parser_cookies
    useragent = crm_settings[0].parser_useragent

    result = parse_ozon_card(data.ozon_url, cookies, useragent)

    product_check = await Repository.get_records(
        ProductModel,
        filters=[
            ProductModel.ozon_article == result['article'],
            ProductModel.status != 3
        ],
        joins=[OrganizationModel],
        select_related=[ProductModel.organization],
    )

    for product in product_check:

        if not product.organization.is_competitor and not organization.is_competitor:
            raise HTTPException(status_code=400, detail=string_products_product_already_exists)

        if product.organization.id == organization.id and organization.is_competitor:
            raise HTTPException(status_code=400, detail=string_products_product_already_exists)

    filename = Strings.alphanumeric(32) if result['image'] else None

    await Repository.save_records(
        [
            {
                'model': ProductModel,
                'records': [
                    {
                        'org_id': organization.id,
                        'ozon_article': result['article'],
                        'ozon_title': result['title'],
                        'ozon_size': result['size'],
                        'ozon_price': result['price'],
                        'barcode': None,
                        'status': 2,
                        'media': filename + '.webp',
                    },
                ]
            }
        ]
    )

    if result['image']:
        await Repository.s3_save_image(result['image'], filename + '.webp')


@router_products.get('/refresh')
async def refresh_product(product_id: int, session: UserSessionModel = Depends(authed)):
    products = await Repository.get_records(
        ProductModel,
        filters=[ProductModel.id == product_id, ProductModel.status != 3],
        select_related=[ProductModel.sizes]
    )

    if len(products) != 1:
        raise HTTPException(status_code=404, detail=string_products_product_not_found)

    await check_access(products[0].org_id, session.user.id, 2)

    if products[0].last_update + datetime.timedelta(minutes=5) > datetime.datetime.now():
        remaining = (products[0].last_update + datetime.timedelta(minutes=5)) - datetime.datetime.now()

        raise HTTPException(
            status_code=403,
            detail=string_product_refresh_error + f'. Вы сможете обновить этот товар через {remaining}'
        )

    # TODO


@router_products.get('/getOwned')
async def get_owned_products(org_id: int, session: UserSessionModel = Depends(authed)):
    await check_access(org_id, session.user.id, 30)

    products = await Repository.get_records(
        ProductModel,
        filters=[ProductModel.org_id == org_id, ProductModel.status != 3],
    )
    return [ProductReadSchema.model_validate(product, from_attributes=True) for product in products]


@router_products.post('/barcode')
async def update_barcode(product_id: int, barcode: str, session: UserSessionModel = Depends(authed)):
    products = await Repository.get_records(
        ProductModel,
        filters=[ProductModel.id == product_id],
    )

    if len(products) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    product = products[0]

    await check_access(product.org_id, session.user.id, 2)

    await Repository.save_records(
        [{'model': ProductModel, 'records': [{'id': product_id, 'barcode': barcode}]}], session_id=session.id)


@router_products.get('/disable')
async def disable_product(product_id: int, session: UserSessionModel = Depends(authed)):
    products = await Repository.get_records(
        ProductModel,
        filters=[ProductModel.id == product_id, ProductModel.status != 3],
    )

    if len(products) != 1:
        raise HTTPException(status_code=404, detail=string_products_product_not_found)

    await check_access(products[0].org_id, session.user.id, 2)

    await Repository.save_records([{'model': ProductModel, 'records': [{'id': product_id, 'status': 3}]}],
                                  session_id=session.id)


@router_reviews.post('/create')
async def create_review(data: Annotated[ReviewCreateSchema, Depends()], files: List[UploadFile] = File(default=None),
                        session: UserSessionModel = Depends(authed)):
    if len(files) > 5:
        raise HTTPException(status_code=400, detail=string_product_too_many_files)

    if data.stars not in [1, 5]:
        raise HTTPException(status_code=400, detail='Рейтинг должен быть 1 или 5')

    sizes = await Repository.get_records(
        ProductModel,
        filters=[ProductModel.id == data.id],
    )

    if len(sizes) != 1:
        raise HTTPException(status_code=404, detail=string_products_product_not_found)

    size = sizes[0]

    if size.product.status == 3:
        raise HTTPException(status_code=404, detail=string_products_product_not_found)

    await check_access(size.product.org_id, session.user.id, 8)

    if not size.is_active:
        raise HTTPException(status_code=403, detail=string_product_size_not_active)

    if not size.barcode:
        raise HTTPException(status_code=403, detail=string_product_size_no_barcode)

    if not size.wb_in_stock:
        raise HTTPException(status_code=403, detail=string_product_size_not_in_stock)

    if data.match not in [None, 0, 1, 2, 3]:
        raise HTTPException(status_code=404, detail=string_404)

    if files[0].size != 0 or files[0].filename != '':
        for file in files:
            try:
                await Repository.verify_file(file, ['jpg', 'jpeg', 'png', 'webp', 'mp4', 'mov'])
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")

    filenames = []
    if files[0].size != 0 or files[0].filename != '':
        for file in files:
            content = await file.read()
            n, t = await Repository.s3_autosave(content,
                                                f"{Strings.alphanumeric(32)}.{file.filename.rsplit('.', maxsplit=1)[1]}")
            filenames.append(f"{n}.{t}")

    await ReviewsRepository.create_review(data, filenames)


@router_reviews.post('/xlsxUpload')
async def get_reviews_of_organization(org_id: int, file: UploadFile = File(...),
                                      session: UserSessionModel = Depends(authed)):
    await check_access(org_id, session.user.id, 8)

    try:
        await Repository.verify_file(file, ['xlsx'])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")

    try:
        await process_reviews_xlsx(file, org_id)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")


@router_reviews.get('/getOwned')
async def get_reviews_of_organization(org_id: int, session: UserSessionModel = Depends(authed)):
    await check_access(org_id, session.user.id, 8)
    reviews = await ReviewsRepository.get_owned_by_org_id(org_id)
    return [ReviewReadSchema.model_validate(record, from_attributes=True) for record in reviews]


@router_reviews.get('/get')
async def get_reviews_of_organization(review_id: int, session: UserSessionModel = Depends(authed)):
    reviews = await Repository.get_records(
        ReviewModel,
        filters=[ReviewModel.id == review_id],
        select_related=[ReviewModel.size, ReviewModel.media],
        deep_related=[[ReviewModel.size, ProductSizeModel.product]],
        joins=[ProductSizeModel, ProductModel],
        filtration=[ProductModel.status != 3]
    )

    if len(reviews) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    review = reviews[0]

    await check_access(review.size.product.org_id, session.user.id, 8)

    return ReviewReadSchema.model_validate(review, from_attributes=True)


@router_reviews.get('/disable')
async def disable_review(review_id: int, session: UserSessionModel = Depends(authed)):
    reviews = await Repository.get_records(
        ReviewModel,
        filters=[ReviewModel.id == review_id],
        select_related=[ReviewModel.size],
        deep_related=[[ReviewModel.size, ProductSizeModel.product]]
    )

    if len(reviews) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    await check_access(reviews[0].size.product.org_id, session.user.id, 8)

    if reviews[0].status != 1:
        raise HTTPException(status_code=403, detail=string_403)

    await Repository.save_records([{'model': ReviewModel, 'records': [{'id': review_id, 'status': 4}]}],
                                  session_id=session.id)


@router_reviews.post('/update')
async def update_review(data: Annotated[ReviewUpdateSchema, Depends()], session: UserSessionModel = Depends(authed)):
    reviews = await Repository.get_records(
        ReviewModel,
        filters=[ReviewModel.id == data.id],
        select_related=[ReviewModel.size],
        deep_related=[[ReviewModel.size, ProductSizeModel.product]]
    )

    if len(reviews) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    review = reviews[0]

    organization, membership = await check_access(review.size.product.org_id, session.user.id, 8)

    if not organization.is_competitor and data.stars != 5:
        raise HTTPException(status_code=403, detail=string_403)

    if review.status != 1:
        raise HTTPException(status_code=403, detail=string_403)

    await Repository.save_records([{'model': ReviewModel, 'records': [data.model_dump()]}], session_id=session.id)


@router_reviews.post('/delMedia')
async def update_review(media_id: int, session: UserSessionModel = Depends(authed)):
    media = await Repository.get_records(
        ReviewMediaModel,
        filters=[ReviewMediaModel.id == media_id],
        select_related=[ReviewMediaModel.review],
        deep_related=[
            [ReviewMediaModel.review, ReviewModel.size],
            [ReviewMediaModel.review, ReviewModel.size, ProductSizeModel.product]
        ]
    )

    if len(media) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    review = media[0].review

    await check_access(review.size.product.org_id, session.user.id, 8)

    if review.status != 1:
        raise HTTPException(status_code=403, detail=string_403)

    await Repository.delete_record(ReviewMediaModel, media_id)


@router_reviews.post('/addMedia')
async def update_review(review_id: int = Form(), files: List[UploadFile] = File(...),
                        session: UserSessionModel = Depends(authed)):
    reviews = await Repository.get_records(
        ReviewModel,
        filters=[ReviewModel.id == review_id],
        select_related=[ReviewModel.size],
        deep_related=[[ReviewModel.size, ProductSizeModel.product]]
    )

    if len(reviews) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    await check_access(reviews[0].size.product.org_id, session.user.id, 8)

    if reviews[0].status != 1:
        raise HTTPException(status_code=403, detail=string_403)

    if files[0].size != 0 or files[0].filename != '':
        for file in files:
            try:
                await Repository.verify_file(file, ['jpg', 'jpeg', 'png', 'webp', 'mp4', 'mov'])

            except Exception as e:
                raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")

    filenames = []
    if files[0].size != 0 or files[0].filename != '':
        for file in files:
            content = await file.read()
            n, t = await Repository.s3_autosave(content,
                                                f"{Strings.alphanumeric(32)}.{file.filename.rsplit('.', maxsplit=1)[1]}")
            filenames.append(f"{n}.{t}")

    if not filenames:
        raise HTTPException(status_code=400, detail='Файлы не выбраны')

    await Repository.save_records([
        {
            'model': ReviewMediaModel,
            'records': [{'media': filename, 'review_id': review_id} for filename in filenames]
        }
    ])
