from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from admin.models import AdminSessionModel
from auth.models import UserSessionModel
from auth.schemas import UserReadSchema
from auth.router import every
from admin.router import every as admin_every
from database import Repository
from orgs.models import OrganizationModel
from orgs.repository import MembershipRepository
from payments.models import BalanceBillModel

router = APIRouter()

templates = Jinja2Templates(directory='frontend/templates')

sections = {
    'dashboard': 0,
    'wallet': 32,
    'loyalty': 0,
    'products': 2,
    'tasks': 4,
    'reviews': 8,
    'orders': 16,
}

pages_levels = {
    'servers': 1,
    'planner': 2,
    'addresses': 4,
    'contractors': 8,
    'orders': 16,
    'balances': 256,
    'accounts': 32,
    'products': 64,
    'reviews': 128,
    'payments': 256,
    'prices': 512,
    'banks': 1024,
    'organizations': 2048,
    'users': 4096,
    'admins': 16384,
    'storage': 32768,
    'usersessions': 65536,
    'adminsessions': 131072,
    'settings': 262144,
    'pickerstatuses': 2,
    'address_statuses': 4,
    'logs': 1048576,
    'pickerorgs': 2
}


@router.get('/admin')
async def page(request: Request,
               session: AdminSessionModel = Depends(admin_every)):
    if not session:
        return RedirectResponse('/admin-login')

    return templates.TemplateResponse('admin-dashboard.html', {'request': request})


@router.get('/admin-login')
async def page(request: Request,
               session: AdminSessionModel = Depends(admin_every)):
    if session:
        return RedirectResponse('/admin')

    return templates.TemplateResponse('admin-login.html', {'request': request})


@router.get('/admin-{action}/{section}')
async def page(section: str,
               action: str,
               request: Request,
               session: AdminSessionModel = Depends(admin_every)):
    if not session:
        return RedirectResponse('/admin-login')

    if not pages_levels.get(section, None):
        return RedirectResponse('/404')

    if not pages_levels[section] & session.admin.level:
        return RedirectResponse('/403')

    if action == 'tables':
        try:
            return templates.TemplateResponse(f'admin-tables-{section}.html', {'request': request})
        except:
            return templates.TemplateResponse(f'admin-record-tables.html', {'request': request})

    if action == 'scripts':
        try:
            return templates.TemplateResponse(f'admin-scripts-{section}.html', {'request': request})
        except:
            return RedirectResponse('/404')

    if action == 'create':
        return templates.TemplateResponse(f'admin-record-create.html', {'request': request})

    return RedirectResponse('/404')


@router.get('/admin-edit/{table}/{id}')
async def page(request: Request,
               table: str,
               session: AdminSessionModel = Depends(admin_every)):

    if not session:
        return RedirectResponse('/admin-login')

    try:
        return templates.TemplateResponse(f'admin-edit-{table}.html', {'request': request})

    except:
        return templates.TemplateResponse(f'admin-record-edit.html', {'request': request})


# AUTH PAGES
@router.get('/')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if session:
        return RedirectResponse('/dashboard')

    return RedirectResponse('/login')


@router.get('/register')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if session:
        return RedirectResponse('/dashboard')

    return templates.TemplateResponse('auth-register.html', {'request': request})


@router.get('/login')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if session:
        return RedirectResponse('/dashboard')

    return templates.TemplateResponse('auth-login.html', {'request': request})


@router.get('/success')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if session:
        return RedirectResponse('/dashboard')

    return templates.TemplateResponse('auth-success.html', {'request': request})


# PRIMARY PAGES
@router.get('/dashboard')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    return templates.TemplateResponse('general-dashboard.html', {'request': request})


@router.get('/wallet/{org_id}/{dates}')
async def page(request: Request, org_id: int, dates: str = None, session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    organizations = await Repository.get_records(
        OrganizationModel,
        filters=[OrganizationModel.id == org_id]
    )

    if len(organizations) != 1:
        return RedirectResponse('/404')

    organization = organizations[0]

    if organization.owner_id != session.user.id:
        membership = await MembershipRepository.read_current(session.user.id, org_id)
        if not membership or membership.status != 1 or not (membership.level & 32):
            return RedirectResponse('/403')


    return templates.TemplateResponse(f'payments-details.html', {'request': request})


@router.get('/organization/{section}/{org_id}')
async def page(request: Request,
               section: str,
               org_id: int,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    organizations = await Repository.get_records(
        OrganizationModel,
        filters=[OrganizationModel.id == org_id]
    )

    if len(organizations) != 1:
        return RedirectResponse('/404')

    organization = organizations[0]

    if section in sections:
        if organization.owner_id != session.user.id:
            membership = await MembershipRepository.read_current(session.user.id, org_id)
            if not membership or membership.status != 1 or not (membership.level & sections[section]):
                return RedirectResponse('/403')

        return templates.TemplateResponse(f'orgs-{section}.html', {'request': request})

    return RedirectResponse('/404')


# SUBPAGES
@router.get('/bill/{bill_id}')
async def page(request: Request,
               bill_id: int,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    bills = await Repository.get_records(
        BalanceBillModel,
        filters=[BalanceBillModel.id == bill_id]
    )

    if len(bills) != 1:
        return RedirectResponse('/404')

    bill = bills[0]

    organizations = await Repository.get_records(
        OrganizationModel,
        filters=[OrganizationModel.id == bill.org_id]
    )

    if len(organizations) != 1:
        return RedirectResponse('/404')

    organization = organizations[0]

    if organization.status != 2:
        return RedirectResponse('/403')

    if organization.owner_id != session.user.id:
        membership = await MembershipRepository.read_current(session.user.id, organization.id)
        if not membership or membership.status != 1 or not (membership.level & 32):
            return RedirectResponse('/403')

    return templates.TemplateResponse('payments-bill.html', {'request': request})


@router.get('/profile')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    return templates.TemplateResponse('user-profile.html', {'request': request})


@router.get('/settings')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    return templates.TemplateResponse('user-settings-general.html', {'request': request})


@router.get('/security')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    return templates.TemplateResponse('user-settings-security.html', {'request': request})


# UTILITY PAGES
@router.get('/403')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    return templates.TemplateResponse('misc-403.html', {'request': request})


@router.get('/404')
async def page(request: Request,
               session: UserSessionModel = Depends(every)):
    if not session:
        return RedirectResponse('/login')

    return templates.TemplateResponse('misc-404.html', {'request': request})
