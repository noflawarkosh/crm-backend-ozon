import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, Response, Request, HTTPException
from sqlalchemy import func

from auth.models import UserSessionModel
from auth.router import authed
from database import Repository
from orgs.models import OrganizationModel, OrganizationInvitationModel, OrganizationMembershipModel

from orgs.schemas import (
    OrganizationCreateSchema,
    OrganizationReadSchema,
    OrganizationInvitationCreateSchema,
    OrganizationInvitationReadSchema,
    OrganizationMembershipReadSchema
)
from orgs.repository import (
    MembershipRepository
)
from orgs.utils import generate_invitation_code
from strings import *

router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"]
)


async def check_access(org_id: int, user_id: int, level: int):
    organizations = await Repository.get_records(
        OrganizationModel,
        filters=[OrganizationModel.id == org_id]
    )

    if len(organizations) != 1:
        raise HTTPException(status_code=404, detail=string_orgs_org_not_found)

    organization = organizations[0]

    if organization.status != 2:
        raise HTTPException(status_code=403, detail=string_orgs_org_not_active)

    if organization.owner_id == user_id:
        return organization, None

    membership = await MembershipRepository.read_current(user_id, organization.id)

    if not membership or membership.status != 1 or not (membership.level & level):
        raise HTTPException(status_code=403, detail=string_403)

    return organization, membership


# Organizations
@router.post('/createOrganization')
async def create_organization(data: Annotated[OrganizationCreateSchema, Depends()],
                              session: UserSessionModel = Depends(authed)):
    level_id = None
    if data.is_competitor:
        level_id = 1

    await Repository.save_records(
        [{'model': OrganizationModel, 'records': [{**data.model_dump(), 'owner_id': session.user.id, 'status': 1, 'level_id': level_id}]}]
    )


@router.get('/readOrganizations')
async def read_user_organizations(session: UserSessionModel = Depends(authed)) -> list[OrganizationReadSchema]:
    organizations = await Repository.get_records(
        OrganizationModel,
        filters=[OrganizationModel.owner_id == session.user.id]
    )
    return [OrganizationReadSchema.model_validate(organization, from_attributes=True) for organization in organizations]


@router.get('/readOrganization')
async def read_user_organization(org_id: int, session: UserSessionModel = Depends(authed)
                                 ) -> OrganizationReadSchema:
    organization, membership = await check_access(org_id, session.user.id, 62)
    return OrganizationReadSchema.model_validate(organization, from_attributes=True)


# Invitations
@router.post('/createInvitation')
async def create_invitation(data: Annotated[OrganizationInvitationCreateSchema, Depends()],
                            session: UserSessionModel = Depends(authed)):
    await check_access(data.org_id, session.user.id, 0)

    if data.expires <= datetime.datetime.now():
        raise HTTPException(status_code=400, detail=string_inv_wrong_expires)

    invitations = await Repository.get_records(
        OrganizationInvitationModel,
        filters=[
            OrganizationInvitationModel.org_id == data.org_id,
            OrganizationInvitationModel.expires > func.now(),
        ]
    )

    if len(invitations) >= 5:
        raise HTTPException(status_code=403, detail=string_inv_max_invitations)

    await Repository.save_records(
        [{'model': OrganizationInvitationModel, 'records': [{**data.model_dump(), 'code': generate_invitation_code()}]}]
    )


@router.get('/readInvitations')
async def read_invitations(org_id: int,
                           session: UserSessionModel = Depends(authed)
                           ) -> list[OrganizationInvitationReadSchema]:
    await check_access(org_id, session.user.id, 0)

    invitations = await Repository.get_records(
        OrganizationInvitationModel,
        filters=[OrganizationInvitationModel.org_id == org_id, OrganizationInvitationModel.expires > func.now()],
        prefetch_related=[OrganizationInvitationModel.usages]
    )

    return [OrganizationInvitationReadSchema.model_validate(
        invitation, from_attributes=True) for invitation in invitations]


@router.post('/disableInvitation')
async def disable_invitations(invitation_id: int,
                              session: UserSessionModel = Depends(authed)):
    invitations = await Repository.get_records(
        OrganizationInvitationModel,
        filters=[OrganizationInvitationModel.id == invitation_id]
    )

    if len(invitations) != 1:
        raise HTTPException(status_code=404, detail=string_inv_not_found)

    invitation = invitations[0]

    await check_access(invitation.org_id, session.user.id, 0)

    await Repository.save_records(
        [{'model': OrganizationInvitationModel, 'records': [{'id': invitation.id, 'expires': func.now()}]}]
    )


@router.post('/acceptInvitation')
async def accept_invitation(code: str,
                            session: UserSessionModel = Depends(authed)):
    invitations = await Repository.get_records(
        OrganizationInvitationModel,
        filters=[OrganizationInvitationModel.code == code]
    )

    if len(invitations) != 1:
        raise HTTPException(status_code=404, detail=string_inv_not_found)

    invitation = invitations[0]

    if invitation.expires <= datetime.datetime.now():
        raise HTTPException(status_code=403, detail=string_inv_expired)

    invitation_usages = await Repository.get_records(
        OrganizationMembershipModel,
        filters=[OrganizationMembershipModel.invitation_id == invitation.id]
    )

    if len(invitation_usages) >= invitation.amount:
        raise HTTPException(status_code=403, detail=string_inv_max_usages)

    organizations = await Repository.get_records(
        OrganizationModel,
        filters=[OrganizationModel.id == invitation.org_id]
    )

    if len(organizations) != 1:
        raise HTTPException(status_code=404, detail=string_orgs_org_not_found)

    organization = organizations[0]

    if organization.owner_id == session.user.id:
        raise HTTPException(status_code=403, detail=string_inv_owner_error)

    current_membership = await MembershipRepository.read_current(session.user.id, organization.id)

    if current_membership:

        if current_membership.status == 1:
            raise HTTPException(status_code=403, detail=string_inv_already_member)

        if current_membership.status == 4:
            raise HTTPException(status_code=403, detail=string_inv_blocked_member)

    await Repository.save_records([
        {
            'model': OrganizationMembershipModel,
            'records': [{
                'org_id': organization.id,
                'user_id': session.user.id,
                'level': invitation.level,
                'status': 1,
                'invitation_id': invitation.id
            }]
        }
    ])


# Membership
@router.get('/readUserMemberships')
async def read_memberships_of_user(session: UserSessionModel = Depends(authed)
                                   ) -> list[OrganizationMembershipReadSchema]:
    return [OrganizationMembershipReadSchema.model_validate(membership, from_attributes=True)
            for membership in await MembershipRepository.read_memberships_of_user(session.user.id)]


@router.get('/readOrganizationMemberships')
async def read_memberships_of_organization(org_id: int, session: UserSessionModel = Depends(authed)):
    await check_access(org_id, session.user.id, 0)

    users = await MembershipRepository.read_memberships_of_organization(org_id)
    dto = [OrganizationMembershipReadSchema.model_validate(row, from_attributes=True) for row in users]

    return dto


@router.post('/updateMember')
async def update_membership(member_id: int,
                            org_id: int,
                            status: int = None,
                            level: int = None,
                            session: UserSessionModel = Depends(authed)):
    organization, membership = await check_access(org_id, session.user.id, 0)

    current_membership = await MembershipRepository.read_current(member_id, org_id)

    if not current_membership:
        raise HTTPException(status_code=400, detail=string_orgs_member_not_found)

    if status == current_membership.status:
        raise HTTPException(status_code=403, detail=string_orgs_member_status_already_set)

    new_status = current_membership.status

    if status:
        if status == 4:
            new_status = 4
            level = 0

        elif status == 5:
            new_status = 5
            level = 0

        elif status == 3:
            if current_membership.status != 1:
                raise HTTPException(status_code=403)
            new_status = 3
            level = 0

    if not new_status and status:
        raise HTTPException(status_code=403, detail=string_403)

    await Repository.save_records([
        {
            'model': OrganizationMembershipModel,
            'records': [{
                'user_id': member_id,
                'org_id': organization.id,
                'level': level,
                'status': new_status,
                'invitation_id': None
            }]
        }
    ])
