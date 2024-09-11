import datetime
from typing import Optional
from pydantic import BaseModel, constr

from auth.schemas import UserReadSchema


# Organization
class OrganizationCreateSchema(BaseModel):
    title: constr(max_length=200)
    inn: constr(min_length=10, max_length=12)
    is_competitor: bool


class OrganizationReadSchema(BaseModel):
    id: int
    title: str
    inn: str
    owner: Optional['UserReadSchema']
    level_id: int | None
    status: int
    is_competitor: bool


# Membership
class OrganizationMembershipReadSchema(BaseModel):
    id: int
    date: datetime.datetime
    user_id: int
    org_id: int
    level: int
    status: int
    invitation_id: Optional[int | None]

    user: Optional['UserReadSchema']
    organization: Optional['OrganizationReadSchema']


# Invitation
class OrganizationInvitationCreateSchema(BaseModel):
    org_id: int
    level: int
    expires: datetime.datetime
    amount: int


class OrganizationInvitationReadSchema(OrganizationInvitationCreateSchema):
    id: int
    org_id: int
    code: str
    created: datetime.datetime

    usages: list['OrganizationMembershipReadSchema'] | None
