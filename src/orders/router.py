import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from auth.models import UserSessionModel
from auth.router import authed

from database import Repository
from orders.models import OrdersOrderModel
from orders.schemas import OrdersOrderReadModel, OrdersOrderCreateModel
from orgs.router import check_access
from products.models import ProductModel
from strings import *

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


@router.post('/cancelTask')
async def cancel_task(task_id: int, session: UserSessionModel = Depends(authed)):
    records = await Repository.get_records(
        model=OrdersOrderModel,
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
        filtration=[OrdersOrderModel.id == task_id]
    )

    if len(records) != 1:
        raise HTTPException(status_code=404, detail=string_orders_task_not_found)

    record = records[0]

    await check_access(record.product.org_id, session.user.id, 4)

    if record.status != 1:
        raise HTTPException(status_code=400, detail=string_403)

    await Repository.save_records([{
        'model': OrdersOrderModel,
        'records': [
            {
                'id': task_id,
                'status': 7,
            }]
    }], session_id=session.id)


@router.post('/replaceTasks')
async def cancel_task(data: dict, session: UserSessionModel = Depends(authed)):
    ids = data['id']
    date = datetime.date.fromisoformat(data['date'])
    org_id = int(data['org_id'])

    await check_access(org_id, session.user.id, 4)

    records = await Repository.get_records(
        model=OrdersOrderModel,
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
        filters=[OrdersOrderModel.id.in_(ids)],
    )

    for record in records:
        if record.status != 1:
            raise HTTPException(status_code=400,
                                detail=f'Задача {record.id}: перенос возможен только со статусом Не оплачен')
        if record.product.org_id != org_id:
            raise HTTPException(status_code=400,
                                detail=f'Задача {record.id}: перенос возможен только в рамках одной организации')

    update_records = [
        {
            'id': record.id,
            'dt_planed': date,
        } for record in records
    ]

    await Repository.save_records([{
        'model': OrdersOrderModel,
        'records': update_records
    }], session_id=session.id)


@router.post('/cancelTasks')
async def cancel_task(data: dict, session: UserSessionModel = Depends(authed)):
    ids = data['id']
    org_id = int(data['org_id'])

    await check_access(org_id, session.user.id, 4)

    records = await Repository.get_records(
        model=OrdersOrderModel,
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
        filters=[OrdersOrderModel.id.in_(ids)],
    )

    for record in records:
        if record.status != 1:
            raise HTTPException(status_code=400,
                                detail=f'Задача {record.id}: отмена возможна только со статусом Не оплачен')
        if record.product.org_id != org_id:
            raise HTTPException(status_code=400,
                                detail=f'Задача {record.id}: отмена возможна только в рамках одной организации')

    update_records = [
        {
            'id': record.id,
            'status': 7,
        } for record in records
    ]

    await Repository.save_records([{
        'model': OrdersOrderModel,
        'records': update_records
    }], session_id=session.id)


@router.get('/getPlan')
async def get_plan(org_id: int, date: datetime.datetime, session: UserSessionModel = Depends(authed)
                   ) -> list[OrdersOrderReadModel]:
    await check_access(org_id, session.user.id, 4)

    records = await Repository.get_records(
        model=OrdersOrderModel,
        filters=[OrdersOrderModel.dt_planed == date],
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
        filtration=[ProductModel.org_id == org_id]
    )

    return [OrdersOrderReadModel.model_validate(record, from_attributes=True) for record in records]


@router.get('/getOrders')
async def get_plan(org_id: int, date: datetime.date = None, session: UserSessionModel = Depends(authed)
                   ) -> list[OrdersOrderReadModel]:
    await check_access(org_id, session.user.id, 4)

    if date is None:
        records = await Repository.get_records(
            model=OrdersOrderModel,
            filters=[OrdersOrderModel.status != 1],
            select_related=[OrdersOrderModel.product],
            joins=[ProductModel],
            filtration=[ProductModel.org_id == org_id]
        )

    else:
        records = await Repository.get_records(
            model=OrdersOrderModel,
            filters=[OrdersOrderModel.status != 1],
            select_related=[OrdersOrderModel.product],
            joins=[ProductModel],
            filtration=[
                ProductModel.org_id == org_id,
                OrdersOrderModel.dt_planed == date
            ]
        )

    return [OrdersOrderReadModel.model_validate(record, from_attributes=True) for record in records]


@router.post('/savePlan')
async def save_data(amount: int, data: Annotated[OrdersOrderCreateModel, Depends()],
                    session: UserSessionModel = Depends(authed)):
    if amount > 100:
        raise HTTPException(status_code=400, detail=string_orders_max_amount)

    products = await Repository.get_records(
        ProductModel,
        filters=[ProductModel.id == data.product_id],
    )

    if len(products) != 1:
        raise HTTPException(status_code=404, detail=string_products_product_not_found)

    product = products[0]

    records = await Repository.get_records(
        model=OrdersOrderModel,
        filters=[OrdersOrderModel.dt_planed == data.dt_planed],
        select_related=[OrdersOrderModel.product],
        joins=[ProductModel],
        filtration=[ProductModel.org_id == product.org_id]
    )

    if len(records) + amount > 500:
        raise HTTPException(status_code=403, detail=string_products_max_tasks_per_day)

    if product.status == 3:
        raise HTTPException(status_code=404, detail=string_products_product_not_found)

    await check_access(product.org_id, session.user.id, 8)

    if not product.barcode:
        raise HTTPException(status_code=403, detail=string_product_size_no_barcode)

    if not product.ozon_price:
        raise HTTPException(status_code=403, detail=string_product_size_no_price)

    if data.dt_planed.date() < datetime.datetime.now().date():
        raise HTTPException(status_code=403, detail=string_orders_wrong_date)

    if datetime.datetime.now().hour > 9 and data.dt_planed.date() == datetime.datetime.now().date():
        raise HTTPException(status_code=400, detail=string_orders_time_error)

    await Repository.save_records([{
        'model': OrdersOrderModel,
        'records': [{
            **data.model_dump(),
            'status': 1,
        }] * amount
    }], session_id=session.id)
