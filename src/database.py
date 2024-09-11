import datetime
import io
from typing import Annotated

import boto3
from PIL import Image
from sqlalchemy import update, select, delete, Column, JSON, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, selectinload, joinedload, Mapped, mapped_column

from strings import *
from config import (
    DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER,
    S3KID, S3KEY, S3BUCKET,
    ACCEPTABLE_IMAGE_TYPES, ACCEPTABLE_FILE_TYPES, DEFAULT_MAX_FILE_SIZE
)

# PostgreSQL
async_engine = create_async_engine(url=f'postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}')
async_session_factory = async_sessionmaker(async_engine)

# S3 Object Storage
s3 = boto3.session.Session().client(
    service_name='s3',
    endpoint_url='https://storage.yandexcloud.net',
    aws_access_key_id=S3KID,
    aws_secret_access_key=S3KEY
)

pk = Annotated[int, mapped_column(primary_key=True)]
dt = Annotated[datetime.datetime, mapped_column(server_default=text('NOW()'))]

models_to_logs = ['OrdersOrderModel', 'ReviewModel', 'ProductSizeModel', 'ProductModel']


class Base(DeclarativeBase):
    pass


class AdminAuditLog(Base):
    __tablename__ = 'admin_audit_log'

    # action 1: create, 2: update, 3: delete
    id: Mapped[pk]
    date: Mapped[dt]
    session_id: Mapped[int]
    is_admin: Mapped[bool]
    table: Mapped[str]
    record_id: Mapped[int]
    action: Mapped[int]
    old_data = Column(JSON, nullable=False)
    new_data = Column(JSON, nullable=False)


class Repository:

    @classmethod
    async def verify_file(cls, file, acceptable_types: list):

        if file.size == 0:
            raise Exception(string_storage_empty_file)

        file_info = file.filename.rsplit('.', maxsplit=1)

        if len(file_info) < 2:
            raise Exception(string_storage_wrong_filetype)

        file_name = file_info[0]
        file_type = file_info[1].lower()

        if len(file_name) == 0:
            raise Exception(string_storage_empty_filename)

        if file_type not in acceptable_types:
            raise Exception(string_storage_wrong_filetype + f'. Только: {acceptable_types}')

        if file_type in {**ACCEPTABLE_FILE_TYPES, **ACCEPTABLE_IMAGE_TYPES}.keys():
            if file.size > {**ACCEPTABLE_FILE_TYPES, **ACCEPTABLE_IMAGE_TYPES}[file_type]:
                raise Exception(string_storage_max_size)
        else:
            if file.size > DEFAULT_MAX_FILE_SIZE:
                raise Exception(string_storage_max_size)

        return file_name, file_type

    @classmethod
    async def s3_autosave(cls, file_bytes, file_full_name):

        file_info = file_full_name.rsplit('.', maxsplit=1)
        file_name = file_info[0]
        file_type = file_info[1].lower()

        if file_type in ACCEPTABLE_IMAGE_TYPES.keys():
            await cls.s3_save_image(file_bytes, file_full_name)
            return file_name, 'webp'
        else:
            await cls.s3_save(file_bytes, file_full_name)
            return file_name, file_type

    @classmethod
    async def s3_save_image(cls, file_bytes, file_full_name):
        file_info = file_full_name.rsplit('.', maxsplit=1)
        file_name = file_info[0]

        image = Image.open(io.BytesIO(file_bytes))
        image.save(io.BytesIO(), format='WEBP', optimize=True, quality=15)

        webp_bytes = io.BytesIO()
        image.save(webp_bytes, format='WebP')
        file_content = webp_bytes.getvalue()
        s3.upload_fileobj(io.BytesIO(file_content), S3BUCKET, f'{file_name}.webp')

    @classmethod
    async def s3_save(cls, file_bytes, file_full_name):
        s3.upload_fileobj(io.BytesIO(file_bytes), S3BUCKET, file_full_name)

    @classmethod
    async def save_records(cls, models, session_id=None, is_admin=False):
        """
        :param is_admin: bool
        :param session_id: int
        :param models: [{'model': ,'records': [{}]}]
        :return: None
        """

        async def to_dict(r):
            data = {}
            for column in r.__table__.columns:

                value = getattr(r, column.name)
                if str(value) == 'now()':
                    data[column.name] = datetime.datetime.now().isoformat() if value is not None else None
                elif str(column.type) == 'DATE':
                    data[column.name] = value.isoformat() if value is not None else None
                elif str(column.type) == 'INTEGER':
                    data[column.name] = int(value) if value is not None else None
                elif str(column.type) == 'VARCHAR':
                    data[column.name] = str(value) if value is not None else None
                elif str(column.type) == 'DATETIME':
                    data[column.name] = value.isoformat() if value is not None else None
                else:
                    data[column.name] = value

            return data

        try:
            async with async_session_factory() as session:

                records_to_insert = []
                audit_log_records = []

                for model in models:
                    is_logging = model['model'].__name__ in models_to_logs

                    for record in model['records']:
                        if record.get('id'):

                            if session_id and is_logging:
                                old_data_model = await session.get(model['model'], record['id'])
                                old_data_dict = await to_dict(old_data_model)

                            new_data_model = await session.merge(model['model'](**record))

                            if session_id and is_logging:
                                new_data_dict = await to_dict(new_data_model)

                                audit_log_records.append(
                                    AdminAuditLog(
                                        session_id=session_id,
                                        is_admin=is_admin,
                                        table=model['model'].__tablename__,
                                        record_id=record['id'],
                                        action=2,
                                        old_data=old_data_dict,
                                        new_data=new_data_dict,
                                    )
                                )

                        else:
                            records_to_insert.append(model['model'](**record))

                session.add_all(records_to_insert)

                if audit_log_records:
                    session.add_all(audit_log_records)

                await session.flush()
                await session.commit()

        except Exception as e:
            await session.rollback()
            raise e

        finally:
            await session.close()

    @classmethod
    async def update_records(cls, model, records):
        try:
            async with async_session_factory() as session:
                for record in records:
                    query = update(model).where(model.id == record['id']).values(**record)
                    await session.execute(query)

                await session.commit()
        finally:
            await session.close()

    @classmethod
    async def get_records(cls, model, filters=None, joins=None, select_related=None, prefetch_related=None,
                          order_by=None, limit=None, offset=None, selects=None, deep_related=None, filtration=None):

        try:
            async with async_session_factory() as session:

                if selects:
                    query = select(model, *selects)
                else:
                    query = select(model)

                if filters:
                    for condition in filters:
                        query = query.where(condition)

                if joins:
                    for join in joins:
                        query = query.join(join)

                if select_related:
                    for select_model in select_related:
                        query = query.options(selectinload(select_model))

                if deep_related:
                    for deep_model in deep_related:
                        query = query.options(selectinload(*deep_model))

                if prefetch_related:
                    for prefetch_model in prefetch_related:
                        query = query.options(joinedload(prefetch_model))

                if filtration:
                    for filtration in filtration:
                        query = query.filter(filtration)

                if order_by:
                    query = query.order_by(*order_by)
                else:
                    query = query.order_by(model.id.desc())

                if limit:
                    query = query.limit(limit)

                if offset:
                    query = query.offset(offset)

                result = await session.execute(query)
                records = result.unique().scalars().all()
                return records

        except Exception as e:
            await session.rollback()
            raise e

        finally:
            await session.close()

    @classmethod
    async def delete_record(cls, model, record_id: int):

        try:
            async with async_session_factory() as session:

                query = (
                    delete(model)
                    .where(model.id == record_id)
                )

                await session.execute(query)
                await session.commit()

        finally:
            await session.close()

    @classmethod
    async def execute_sql(cls, query):
        try:
            async with async_session_factory() as session:
                db_response = await session.execute(text(query))
                return db_response.all()

        finally:
            await session.close()
