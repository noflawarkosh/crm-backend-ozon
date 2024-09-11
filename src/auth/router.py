from io import BytesIO
from typing import Annotated, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Response, Request, HTTPException, File, UploadFile
from sqlalchemy import func

from auth.repository import AuthRepository
from strings import *
from database import Repository
from auth.models import UserModel, UserSessionModel
from auth.schemas import UserReadSchema, UserCreateSchema, UserUpdateSchema
from gutils import Strings

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)


async def every(request: Request = Request):
    token = request.cookies.get(cookies_token_key)

    if not token:
        return None

    sessions = await Repository.get_records(
        UserSessionModel,
        filters=[UserSessionModel.token == token, UserSessionModel.expires > func.now()],
        select_related=[UserSessionModel.user]
    )

    if len(sessions) != 1 or sessions[0].user.status != 2:
        return None

    return sessions[0]


async def authed(request: Request = Request):
    session = await every(request)

    if session:
        return session

    raise HTTPException(status_code=401)


async def not_authed(request: Request = Request):
    if await every(request):
        raise HTTPException(status_code=409)


@router.post('/register')
async def register(data: Annotated[UserCreateSchema, Depends()], session: UserSessionModel = Depends(not_authed)):
    data.telnum = data.telnum.replace(' ', '+')
    unique_fields = [
        ('email', data.email.lower(), string_user_email_exist),
        ('username', data.username.lower(), string_user_username_exist),
        ('telnum', data.telnum, string_user_telnum_exist),
        ('telegram', data.telegram, string_user_telegram_exist),
    ]

    for field, value, error in unique_fields:
        user_check = await Repository.get_records(
            UserModel,
            filters=[getattr(UserModel, field) == value]
        )
        if user_check:
            raise HTTPException(status_code=409, detail=error)

    data.password = Strings.hmac(data.password)
    data.username = data.username.lower()
    data.email = data.email.lower()

    await Repository.save_records([{'model': UserModel, 'records': [{**data.model_dump(), 'status': 1}]}])


@router.post('/login')
async def login(request: Request, response: Response, username: str, password: str,
                session: UserSessionModel = Depends(not_authed)):
    user_check = await Repository.get_records(
        UserModel,
        filters=[UserModel.username == username.lower().replace(' ', '')]
    )

    if len(user_check) != 1:
        raise HTTPException(status_code=403, detail=string_user_wrong_password)

    user_check = user_check[0]

    if Strings.hmac(password) != user_check.password:
        raise HTTPException(status_code=403, detail=string_user_wrong_password)

    if user_check.status != 2:
        raise HTTPException(status_code=403, detail=string_user_inactive_user)

    token = Strings.alphanumeric(128)
    await Repository.save_records([
        {
            'model': UserSessionModel,
            'records': [
                {
                    'user_id': user_check.id,
                    'token': token,
                    'useragent': request.headers.get('user-agent'),
                    'ip': request.client.host,
                }
            ]
        }
    ])

    response.set_cookie(key=cookies_token_key, value=token)


@router.get('/logout')
async def logout(request: Request, response: Response, session: UserSessionModel = Depends(authed)):
    await Repository.save_records([
        {
            'model': UserSessionModel,
            'records': [
                {
                    'id': session.id,
                    'expires': func.now()
                }
            ]
        }
    ])
    response.delete_cookie(cookies_token_key)


@router.get('/myProfile')
async def get_self_user_profile(session: UserSessionModel = Depends(authed)) -> UserReadSchema:
    return UserReadSchema.model_validate(session.user, from_attributes=True)


@router.post('/updateProfile')
async def register(data: Annotated[UserUpdateSchema, Depends()],
                   file: Optional[UploadFile] = File(default=None),
                   session: UserSessionModel = Depends(authed)):
    if file:
        try:
            await Repository.verify_file(file, ['jpg', 'jpeg', 'png', 'webp'])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"{file.filename}: {str(e)}")

    unique_fields = [
        ('email', data.email, string_user_email_exist),
        ('telnum', data.telnum, string_user_telnum_exist),
        ('telegram', data.telegram, string_user_telegram_exist),
    ]

    for field, value, error in unique_fields:
        user_check = await Repository.get_records(
            UserModel,
            filters=[getattr(UserModel, field) == value]
        )
        if user_check and user_check[0].id != session.user.id:
            raise HTTPException(status_code=409, detail=error)

    record = {**data.model_dump(), 'id': session.user.id}

    if file:
        href = Strings.alphanumeric(32)
        record['media'] = href + '.webp'

    await Repository.save_records([
        {'model': UserModel, 'records': [record]}
    ])

    if file:
        content = await file.read()
        await Repository.s3_save_image(content, f"{href}.{file.filename.rsplit('.', maxsplit=1)[1]}")


@router.post('/updatePassword')
async def update_password(opw: str, npw: str, session: UserSessionModel = Depends(authed)):
    if Strings.hmac(opw) != session.user.password:
        raise HTTPException(status_code=403, detail=string_user_wrong_opw)

    if Strings.hmac(opw) == Strings.hmac(npw):
        raise HTTPException(status_code=403, detail=string_user_wrong_npw)

    await Repository.save_records([
        {'model': UserModel, 'records': [{'id': session.user.id, 'password': Strings.hmac(npw)}]}
    ])

    await AuthRepository.expire_sessions(session.user.id, exclude_token=session.token)
