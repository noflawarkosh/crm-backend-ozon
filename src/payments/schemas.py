import datetime
from typing import Optional
from pydantic import BaseModel, constr

from orgs.schemas import OrganizationReadSchema


# Balance Action
class BalanceActionSchema(BaseModel):
    id: int
    title: str


class BalanceTargetSchema(BaseModel):
    id: int
    title: str


class BalanceHistoryReadSchema(BaseModel):
    id: int
    action_id: int
    description: str | None
    org_id: int
    amount: int
    date: datetime.datetime
    record_id: int | None
    target_id: int | None

    organization: Optional['OrganizationReadSchema']
    action: Optional['BalanceActionSchema']
    target: Optional['BalanceTargetSchema']


# Balance Source
class BalanceSourceSchema(BaseModel):
    id: int
    bank: str
    recipient: str
    number: str
    bill: str
    description: str | None
    is_active: bool
    priority: int | None


# Balance Status
class BalanceBillStatusSchema(BaseModel):
    id: int
    title: str


class BalanceBillCreateSchema(BaseModel):
    org_id: int
    amount: int
    source_id: int


class BalanceBillReadSchema(BalanceBillCreateSchema):
    id: int
    status_id: int
    date: datetime.datetime
    media: Optional[str] = None
    penalty: Optional[int] = None

    organization: Optional['OrganizationReadSchema']
    source: Optional['BalanceSourceSchema']
    status: Optional['BalanceBillStatusSchema']


class BalanceLevelSchema(BaseModel):
    id: int
    title: str
    number: int
    amount: int | None
    is_public: bool

    price_buy: int
    price_collect: int
    price_review: int
    price_review_media: int
    price_review_request: int
    price_box: int
    price_pass: int
    price_percent: float
    price_percent_limit: int
    price_percent_penalty: float
