from typing import Annotated
from sqlalchemy import text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import datetime

from admin.models import Base

pk = Annotated[int, mapped_column(primary_key=True)]
dt = Annotated[datetime.datetime, mapped_column(server_default=text('NOW()'))]


class PickerSettingsModel(Base):
    __tablename__ = 'admin_picker_settings'

    id: Mapped[pk]
    r2: Mapped[float]
    r3: Mapped[float]
    r4: Mapped[float]

    l2: Mapped[float]
    l3: Mapped[float]
    l4: Mapped[float]
    l5: Mapped[float]

    lo: Mapped[int]
    al: Mapped[int]

    k_format: Mapped[str]


class PickerHistoryModel(Base):
    __tablename__ = 'admin_picker_history'

    id: Mapped[pk]
    date: Mapped[dt]
    logs: Mapped[str]
    result: Mapped[str | None]

    # FK
    server_id: Mapped[int] = mapped_column(
        ForeignKey('orders_server.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    server: Mapped['PickerServerModel'] = relationship(lazy=False)


# Server
class PickerServerContractorModel(Base):
    __tablename__ = 'orders_server_contractor'

    id: Mapped[pk]
    load_percent: Mapped[float]
    load_j_min: Mapped[int]
    load_j_max: Mapped[int]
    load_l_min: Mapped[int]
    load_l_max: Mapped[int]
    load_t_min: Mapped[int]
    load_t_max: Mapped[int]
    load_i: Mapped[int]
    load_m: Mapped[datetime.date]

    # FK
    contractor_id: Mapped[int] = mapped_column(
        ForeignKey('orders_contractor.id', ondelete='CASCADE', onupdate='CASCADE')
    )
    server_id: Mapped[int] = mapped_column(
        ForeignKey('orders_server.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    contractor: Mapped['OrdersContractorModel'] = relationship(lazy='selectin')


class PickerServerScheduleModel(Base):
    __tablename__ = 'orders_server_schedule'

    id: Mapped[pk]
    title: Mapped[str]
    time_min_min_per_step: Mapped[float]
    time_max_min_per_step: Mapped[float]
    time_start: Mapped[datetime.time]
    time_end: Mapped[datetime.time]
    time_first_point: Mapped[datetime.time]
    time_second_point: Mapped[datetime.time]


class PickerServerClientModel(Base):
    __tablename__ = 'orders_server_client'
    id: Mapped[pk]
    load_i: Mapped[int]

    org_id: Mapped[int] = mapped_column(
        ForeignKey('organization.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    organization: Mapped['OrganizationModel'] = relationship(lazy='noload')


class PickerServerModel(Base):
    __tablename__ = 'orders_server'

    id: Mapped[pk]
    number: Mapped[str]
    name: Mapped[str]
    is_active: Mapped[bool]

    # FK
    schedule_id: Mapped[int] = mapped_column(
        ForeignKey('orders_server_schedule.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    schedule: Mapped['PickerServerScheduleModel'] = relationship(lazy='noload')
    contractors: Mapped[list['PickerServerContractorModel']] = relationship(lazy='noload')


class PickerOrderStatus(Base):
    __tablename__ = 'admin_picker_orders_status'

    id: Mapped[pk]
    title: Mapped[str]
    description: Mapped[str | None]
    full_match: Mapped[bool]
    status_number: Mapped[int]
    pay_product: Mapped[bool]
    refund_product: Mapped[bool]
    refund_services: Mapped[bool]
    is_success: Mapped[bool]
