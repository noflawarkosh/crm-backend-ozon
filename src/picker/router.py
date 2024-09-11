import datetime

from fastapi import APIRouter, Depends, Response, Request, HTTPException, UploadFile, File

from admin.models import AdminSessionModel
from admin.router import authed

from picker.utils import refresh_active_and_collected, generate_plan_xlsx, generate_plan_xlsx_2, generate_plan_main
from picker.models import PickerServerScheduleModel, PickerSettingsModel, PickerServerContractorModel, \
    PickerHistoryModel, PickerServerModel

from gutils import Strings
from database import Repository

router = APIRouter(
    prefix="/picker",
    tags=["Admin"]
)


@router.post('/refreshOrders')
async def refresh_orders(request: Request, session: AdminSessionModel = Depends(authed)):
    data = dict(await request.form())

    servers = await Repository.get_records(
        PickerServerModel,
        filters=[PickerServerModel.is_active],
        select_related=[PickerServerModel.contractors, PickerServerModel.schedule]
    )

    for server in servers:
        if not data.get(f'active-{server.id}', None) or data.get(f'active-{server.id}') == 'undefined':
            raise HTTPException(status_code=400, detail=f'Отсутствует файл с активными заказами для {server.name}')

        if not data.get(f'collected-{server.id}', None) or data.get(f'collected-{server.id}') == 'undefined':
            raise HTTPException(status_code=400, detail=f'Отсутствует файл с полученными заказами для {server.name}')

        if not data.get(f'plan-{server.id}', None) or data.get(f'plan-{server.id}') == 'undefined':
            raise HTTPException(status_code=400, detail=f'Отсутствует файл плана для {server.name}')


    return await refresh_active_and_collected(data, servers, session)




@router.post('/generatePlan')
async def generate_plan(request: Request, date: datetime.date, session: AdminSessionModel = Depends(authed)):
    servers = await Repository.get_records(
        PickerServerModel,
        filters=[PickerServerModel.is_active],
        select_related=[PickerServerModel.contractors, PickerServerModel.schedule]
    )

    data = dict(await request.form())
    bad_accounts = data['bad_accounts']

    try:
        await generate_plan_main(servers, bad_accounts, date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'{str(e)}')


@router.post('/generatePlan2')
async def generate_plan(date: datetime.date, request: Request, session: AdminSessionModel = Depends(authed), ):
    servers = await Repository.get_records(
        PickerServerModel,
        filters=[PickerServerModel.is_active],
        select_related=[PickerServerModel.contractors, PickerServerModel.schedule]
    )

    await generate_plan_xlsx_2(servers, date)
