import datetime
import math
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from database import Repository
from orders.models import OrdersOrderModel
from payments.repository import PaymentsRepository
from payments.utils import payment_week, get_previous_week_dates, get_current_week_dates
from products.models import ProductModel
from strings import *
from auth.router import authed
from orgs.router import check_access
from auth.models import UserSessionModel
from payments.models import (
    BalanceBillModel,
    BalanceSourceModel,
    BalanceHistoryModel, BalancePricesModel
)
from payments.schemas import (
    BalanceBillCreateSchema,
    BalanceBillReadSchema,
    BalanceSourceSchema,
    BalanceHistoryReadSchema, BalanceLevelSchema
)

router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)


async def current_prices(organization):
    ws, we = get_previous_week_dates()

    if not organization.level_id:
        purchases = await get_purchases_count(ws, we, organization.id)
        levels = await get_public_levels()
        selected_level = next((level for level in levels if purchases < level.amount), levels[-1])
    else:
        purchases = await get_purchases_count(ws, we, organization.id)
        levels = await get_level_by_id(organization.level_id)
        selected_level = levels

    return selected_level, purchases


async def nex_prices(organization):
    ws, we = get_current_week_dates()

    if not organization.level_id:
        purchases = await get_purchases_count(ws, we, organization.id)
        levels = await get_public_levels()
        selected_level = next((level for level in levels if purchases < level.amount), levels[-1])
    else:
        purchases = await get_purchases_count(ws, we, organization.id)
        levels = await get_level_by_id(organization.level_id)
        selected_level = levels

    return selected_level, purchases


async def get_purchases_count(ws, we, org_id):
    return len(await Repository.get_records(
        model=OrdersOrderModel,
        filters=[
            OrdersOrderModel.dt_ordered is not None,
            OrdersOrderModel.dt_ordered > ws,
            OrdersOrderModel.dt_ordered < we,
        ],
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
        filtration=[ProductModel.org_id == org_id]
    ))


async def get_public_levels():
    return await Repository.get_records(
        BalancePricesModel,
        filters=[BalancePricesModel.is_public],
        order_by=[BalancePricesModel.number.asc()]
    )


async def get_level_by_id(level_id):
    levels = await Repository.get_records(
        BalancePricesModel,
        filters=[BalancePricesModel.id == level_id]
    )
    if len(levels) != 1:
        raise HTTPException(status_code=404, detail=string_payments_no_levels)
    return levels[0]


async def get_current_balance(org_id):
    history = await Repository.get_records(
        BalanceHistoryModel,
        filters=[BalanceHistoryModel.org_id == org_id]
    )
    total = 0
    for record in history:
        if record.action_id == 1:
            total += record.amount
        elif record.action_id == 2:
            total -= record.amount
        elif record.action_id == 3:
            total -= record.amount
        elif record.action_id == 4:
            total += record.amount

    return total


@router.get('/currentBalance')
async def current_level(org_id: int, session: UserSessionModel = Depends(authed)):
    organization, membership = await check_access(org_id, session.user.id, 32)
    return [await get_current_balance(org_id), organization.balance_limit]


@router.get('/currentLevel')
async def current_level(org_id: int, session: UserSessionModel = Depends(authed)):
    organization, membership = await check_access(org_id, session.user.id, 62)

    if organization.level_id:
        level = await get_level_by_id(organization.level_id)
        ws, we = get_previous_week_dates()
        purchases = await get_purchases_count(ws, we, organization.id)

    else:
        level, purchases = await current_prices(organization)

    return {
        'level': BalanceLevelSchema.model_validate(level, from_attributes=True),
        'purchases': purchases,
        'personal': organization.level_id,
    }


@router.get('/futureLevel')
async def get_levels(org_id: int, session: UserSessionModel = Depends(authed)):
    organization, membership = await check_access(org_id, session.user.id, 32)

    levels = await Repository.get_records(
        BalancePricesModel,
        filters=[BalancePricesModel.is_public],
        order_by=[BalancePricesModel.number.asc()]
    )

    if organization.level_id:
        level = await get_level_by_id(organization.level_id)
        ws, we = get_current_week_dates()
        purchases = await get_purchases_count(ws, we, organization.id)

    else:
        level, purchases = await nex_prices(organization)

    return {
        'all': [BalanceLevelSchema.model_validate(level, from_attributes=True) for level in levels],
        'progress': BalanceLevelSchema.model_validate(level, from_attributes=True),
        'purchases': purchases,
        'personal': organization.level_id,
    }


@router.post('/createBill')
async def create_organization(data: Annotated[BalanceBillCreateSchema, Depends()],
                              session: UserSessionModel = Depends(authed)):
    organization, membership = await check_access(data.org_id, session.user.id, 32)

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail=string_400)

    level, purchases = await current_prices(organization)

    status_id = 3
    penalty = 0

    if data.source_id == 1:
        penalty = math.ceil(data.amount * level.price_percent_penalty / 100)
        status_id = 6

    bill_id = await PaymentsRepository.create_bill({**data.model_dump(), 'status_id': status_id, 'penalty': penalty})
    return bill_id


@router.get('/getBill')
async def create_organization(bill_id: int,
                              session: UserSessionModel = Depends(authed)
                              ) -> BalanceBillReadSchema:
    bills = await Repository.get_records(
        BalanceBillModel,
        filters=[BalanceBillModel.id == bill_id],
        prefetch_related=[
            BalanceBillModel.source,
            BalanceBillModel.status,
            BalanceBillModel.organization
        ]
    )

    if len(bills) != 1:
        raise HTTPException(status_code=404, detail=string_404) if len(bills) == 0 else None

    await check_access(bills[0].org_id, session.user.id, 32)

    return BalanceBillReadSchema.model_validate(bills[0], from_attributes=True)


@router.get('/getOwnedBills')
async def create_organization(org_id: int,
                              session: UserSessionModel = Depends(authed)
                              ) -> list[BalanceBillReadSchema]:
    await check_access(org_id, session.user.id, 32)
    bills = await Repository.get_records(
        BalanceBillModel,
        filters=[BalanceBillModel.org_id == org_id],
        prefetch_related=[
            BalanceBillModel.source,
            BalanceBillModel.status,
        ]
    )
    return [BalanceBillReadSchema.model_validate(record, from_attributes=True) for record in bills]


@router.get('/getBalance')
async def create_organization(org_id: int, session: UserSessionModel = Depends(authed)):
    await check_access(org_id, session.user.id, 32)

    try:
        int(org_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=string_400)

    query = 'SELECT SUM(' \
            'CASE ' \
            'WHEN action_id IN (1, 4) THEN amount ' \
            'WHEN action_id IN (2, 3) THEN -amount ' \
            'ELSE 0 ' \
            'END) AS total_amount ' \
            'FROM balance_history ' \
            f'WHERE org_id = {org_id};'


    result = await Repository.execute_sql(query)

    return result[0][0]


@router.post('/updateBillStatus')
async def create_organization(bill_id: int, status_id: int,
                              session: UserSessionModel = Depends(authed)):
    bills = await Repository.get_records(
        BalanceBillModel,
        filters=[BalanceBillModel.id == bill_id]
    )

    if len(bills) != 1:
        raise HTTPException(status_code=404, detail=string_404)

    await check_access(bills[0].org_id, session.user.id, 32)

    if status_id not in [2, 4]:
        raise HTTPException(status_code=403, detail=string_403)

    if status_id == 2 and bills[0].status_id not in [3]:
        raise HTTPException(status_code=403, detail=string_403)

    elif status_id == 4 and bills[0].status_id not in [3]:
        raise HTTPException(status_code=403, detail=string_403)

    await Repository.save_records(
        [{'model': BalanceBillModel, 'records': [{'id': bill_id, 'status_id': status_id}]}]
    )


@router.get('/getActiveSources')
async def create_organization(session: UserSessionModel = Depends(authed)) -> list[BalanceSourceSchema]:
    sources = await Repository.get_records(
        BalanceSourceModel,
        filters=[BalanceSourceModel.is_active]
    )
    return [BalanceSourceSchema.model_validate(record, from_attributes=True) for record in sources]


@router.get('/getHistory')
async def create_organization(org_id: int,
                              session: UserSessionModel = Depends(authed)
                              ) -> list[BalanceHistoryReadSchema]:
    await check_access(org_id, session.user.id, 32)
    history = await Repository.get_records(
        BalanceHistoryModel,
        filters=[BalanceHistoryModel.org_id == org_id]
    )
    return [BalanceHistoryReadSchema.model_validate(record, from_attributes=True) for record in history]


@router.get('/getOrderedHistory')
async def create_organization(org_id: int,
                              session: UserSessionModel = Depends(authed)
                              ):
    await check_access(org_id, session.user.id, 32)
    history = await Repository.get_records(
        BalanceHistoryModel,
        filters=[BalanceHistoryModel.org_id == org_id]
    )

    db_orders = await Repository.get_records(
        OrdersOrderModel,
        select_related=[OrdersOrderModel.product, OrdersOrderModel.account, OrdersOrderModel.picker_status],

        joins=[ProductModel],
        filtration=[ProductModel.org_id == org_id]
    )

    df_orders = pd.DataFrame([
        {
            'id': x.id,
            'dt_planed': x.dt_planed,
        }
        for x in db_orders
    ])

    result = {}

    for record in history:

        if db_orders:
            query = df_orders.query(f"id == {record.record_id}")
            payment_date = query['dt_planed'].iloc[0] if len(query.values) != 0 else None

        else:
            payment_date = None

        if not payment_date:
            payment_date = record.date.date()

        payment_date = payment_date.strftime('%d.%m.%Y')
        if result.get(payment_date):
            result[payment_date].append(BalanceHistoryReadSchema.model_validate(record, from_attributes=True))
        else:
            result[payment_date] = [BalanceHistoryReadSchema.model_validate(record, from_attributes=True)]

    return result


@router.get('/getOrderedHistoryDetails')
async def create_organization(org_id: int, start: datetime.datetime, end: datetime.datetime,
                              session: UserSessionModel = Depends(authed)
                              ):
    await check_access(org_id, session.user.id, 32)

    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)

    history = await Repository.get_records(
        BalanceHistoryModel,
        filters=[BalanceHistoryModel.org_id == org_id]
    )

    db_orders = await Repository.get_records(
        OrdersOrderModel,
        select_related=[OrdersOrderModel.product, OrdersOrderModel.account, OrdersOrderModel.picker_status],
        joins=[ProductModel],
        filtration=[ProductModel.org_id == org_id],
        filters=[OrdersOrderModel.dt_planed >= start.date(), OrdersOrderModel.dt_planed <= end.date()]
    )

    order_ids = [x.id for x in db_orders]

    result = []

    for record in history:

        if record.record_id in order_ids:
            result.append(BalanceHistoryReadSchema.model_validate(record, from_attributes=True))

        elif record.date.date() >= start.date() and record.date.date() <= end.date():
            result.append(BalanceHistoryReadSchema.model_validate(record, from_attributes=True))

    return result


@router.get('/getPaymentsDetails')
async def create_organization(org_id: int, start: datetime.datetime, end: datetime.datetime,
                              session: UserSessionModel = Depends(authed)
                              ) -> list[BalanceHistoryReadSchema]:
    await check_access(org_id, session.user.id, 32)

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

    return [BalanceHistoryReadSchema.model_validate(record, from_attributes=True) for record in history]


@router.post('/tasksPay')
async def create_organization(org_id: int, data: list[int], session: UserSessionModel = Depends(authed)):
    organization, membership = await check_access(org_id, session.user.id, 32)

    orders = await Repository.get_records(
        model=OrdersOrderModel,
        filters=[OrdersOrderModel.id.in_(data)],
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
    )

    if len(orders) == 0:
        raise HTTPException(status_code=400, detail=string_orders_no_orders_to_pay)

    for order in orders:

        error_string_product = f'Товар арт. {order.product.ozon_article}'
        error_string = f'{error_string_product}: '

        if order.product.org_id != org_id:
            raise HTTPException(status_code=403, detail=f'Задача №{order.id}: ' + string_403)

        if order.status != 1 or order.ozon_price:
            raise HTTPException(status_code=400, detail=f'Задача №{order.id}: ' + string_orders_already_paid)

        if order.dt_planed < datetime.date.today():
            raise HTTPException(status_code=400, detail=f'Задача №{order.id}: ' + string_orders_old_to_pay)

        if datetime.datetime.now().hour > 9 and order.dt_planed < datetime.date.today():
            raise HTTPException(status_code=400, detail=f'Задача №{order.id}: ' + string_orders_time_error)

        if not order.product.barcode:
            raise HTTPException(status_code=403,
                                detail=f'Задача №{order.id}: ' + error_string + string_product_size_not_active)

        if not order.product.ozon_price:
            raise HTTPException(status_code=403,
                                detail=f'Задача №{order.id}: ' + error_string + string_product_size_not_active)

    level, purchases = await current_prices(organization)

    calculated_orders = []
    balance_records = []

    total_to_pay = 0
    current_balance = await get_current_balance(org_id)

    for order in orders:
        price_product = order.product.ozon_price
        price_commission = 0

        if price_product >= level.price_percent_limit:
            price_commission = int((price_product - level.price_percent_limit) * (level.price_percent / 100)) + 1

        balance_records.append({
            'amount': price_product,
            'org_id': org_id,
            'target_id': 1,
            'record_id': order.id,
            'action_id': 2
        })

        balance_records.append({
            'amount': level.price_buy,
            'org_id': org_id,
            'target_id': 2,
            'record_id': order.id,
            'action_id': 3
        })

        balance_records.append({
            'amount': level.price_collect,
            'org_id': org_id,
            'target_id': 3,
            'record_id': order.id,
            'action_id': 3
        })

        if price_commission > 0:
            balance_records.append({
                'amount': price_commission,
                'org_id': org_id,
                'target_id': 4,
                'record_id': order.id,
                'action_id': 3
            })

        calculated_orders.append({'id': order.id, 'ozon_price': price_product, 'status': 2})

        total_to_pay += price_product + price_commission + level.price_collect + level.price_buy

    if current_balance - total_to_pay < organization.balance_limit:
        raise HTTPException(status_code=403,
                            detail=string_payments_not_enough_balance + f'. Пополните кошелек минимум на {abs(current_balance - total_to_pay)} рублей для совершения оплаты')

    await Repository.save_records(
        [
            {'model': OrdersOrderModel, 'records': calculated_orders},
            {'model': BalanceHistoryModel, 'records': balance_records}
        ], session_id=session.id
    )


@router.get('/tasksCheckout')
async def create_organization(org_id: int, date: datetime.date, session: UserSessionModel = Depends(authed)):
    if date < datetime.date.today():
        raise HTTPException(status_code=403, detail=string_payments_wrong_date)

    organization, membership = await check_access(org_id, session.user.id, 32)

    orders = await Repository.get_records(
        model=OrdersOrderModel,
        filters=[
            OrdersOrderModel.status == 1,
            OrdersOrderModel.ozon_price.is_(None),
            OrdersOrderModel.dt_planed == date,
        ],
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
        filtration=[ProductModel.org_id == org_id]
    )

    level, purchases = await current_prices(organization)

    sum_price_product = 0
    sum_price_commission = 0
    sum_service_buy = 0
    sum_service_collect = 0
    total = []

    for order in orders:
        error_string_product = f'Товар арт. {order.product.ozon_article}'
        error_string = f'{error_string_product}: '

        if not order.product.barcode:
            raise HTTPException(status_code=403, detail=error_string + string_product_size_no_barcode)

        if not order.product.ozon_price:
            raise HTTPException(status_code=403, detail=error_string + string_product_size_no_price)

        price_product = order.product.ozon_price
        price_commission = 0

        if price_product >= level.price_percent_limit:
            price_commission = int((price_product - level.price_percent_limit) * (level.price_percent / 100)) + 1

        total.append({
            'order_id': order.id,
            'ozon_title': order.product.ozon_title,
            'ozon_article': order.product.ozon_article,
            'ozon_size': order.product.ozon_size,

            'price_product': price_product,
            'price_commission': price_commission,
            'price_buy': level.price_buy,
            'price_collect': level.price_collect,
            'price_total': price_product + price_commission + level.price_buy + level.price_collect,
        })

        sum_price_product += price_product
        sum_price_commission += price_commission
        sum_service_buy += level.price_buy
        sum_service_collect += level.price_collect

    return {
        'total': {
            'level': level.title,
            'per_buy': level.price_buy,
            'per_collect': level.price_collect,
            'percent': level.price_percent,
            'percent_limit': level.price_percent_limit,
            'sum_price_product': sum_price_product,
            'sum_price_commission': sum_price_commission,
            'sum_service_buy': sum_service_buy,
            'sum_service_collect': sum_service_collect,
            'sum_total': sum_price_product + sum_price_commission + sum_service_buy + sum_service_collect,
        },
        'trace': total
    }
