from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.audit import AuditLogResponse
from app.schemas.workspace import (
    WorkspaceCreateRequest,
    WorkspaceMemberAddRequest,
    WorkspaceMemberResponse,
    WorkspaceMemberUpdateRequest,
    WorkspaceResponse,
)
from app.services.audit import list_workspace_audit_logs
from app.services.workspace import (
    SlugAlreadyExistsError,
    UserNotFoundError,
    WorkspaceLastOwnerError,
    WorkspaceMemberNotFoundError,
    WorkspaceNotFoundError,
    WorkspaceOwnerRequiredError,
    WorkspaceWithRole,
    add_workspace_member,
    create_workspace,
    get_workspace_for_user,
    list_workspace_members,
    list_workspaces,
    remove_workspace_member,
    require_workspace_owner,
    update_workspace_member_role,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace_endpoint(
    payload: WorkspaceCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> WorkspaceResponse:
    try:
        workspace = await create_workspace(
            session,
            user=current_user,
            name=payload.name,
            slug=payload.slug,
        )
    except SlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace slug is already in use.",
        ) from exc

    return workspace_response(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces_endpoint(
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[WorkspaceResponse]:
    workspaces = await list_workspaces(session, user=current_user)
    return [workspace_response(workspace) for workspace in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace_endpoint(
    workspace_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> WorkspaceResponse:
    try:
        workspace = await get_workspace_for_user(
            session,
            user=current_user,
            workspace_id=workspace_id,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc

    return workspace_response(workspace)


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
async def list_workspace_members_endpoint(
    workspace_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[WorkspaceMemberResponse]:
    try:
        members = await list_workspace_members(
            session,
            user=current_user,
            workspace_id=workspace_id,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc

    return [workspace_member_response(member) for member in members]


@router.get("/{workspace_id}/audit-logs", response_model=list[AuditLogResponse])
async def list_workspace_audit_logs_endpoint(
    workspace_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    limit: int = 100,
) -> list[AuditLogResponse]:
    try:
        await require_workspace_owner(session, user=current_user, workspace_id=workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can read audit logs.",
        ) from exc

    audit_logs = await list_workspace_audit_logs(
        session,
        workspace_id=workspace_id,
        limit=limit,
    )
    return [AuditLogResponse.model_validate(audit_log) for audit_log in audit_logs]


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_workspace_member_endpoint(
    workspace_id: UUID,
    payload: WorkspaceMemberAddRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> WorkspaceMemberResponse:
    try:
        member = await add_workspace_member(
            session,
            actor=current_user,
            workspace_id=workspace_id,
            email=payload.email,
            role=payload.role,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage members.",
        ) from exc

    return workspace_member_response(member)


@router.patch("/{workspace_id}/members/{user_id}", response_model=WorkspaceMemberResponse)
async def update_workspace_member_endpoint(
    workspace_id: UUID,
    user_id: UUID,
    payload: WorkspaceMemberUpdateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> WorkspaceMemberResponse:
    try:
        member = await update_workspace_member_role(
            session,
            actor=current_user,
            workspace_id=workspace_id,
            user_id=user_id,
            role=payload.role,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except WorkspaceMemberNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace member not found.",
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage members.",
        ) from exc
    except WorkspaceLastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace must keep at least one owner.",
        ) from exc

    return workspace_member_response(member)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workspace_member_endpoint(
    workspace_id: UUID,
    user_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> None:
    try:
        await remove_workspace_member(
            session,
            actor=current_user,
            workspace_id=workspace_id,
            user_id=user_id,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except WorkspaceMemberNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace member not found.",
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage members.",
        ) from exc
    except WorkspaceLastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace must keep at least one owner.",
        ) from exc


def workspace_response(workspace: WorkspaceWithRole) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.workspace.id,
        name=workspace.workspace.name,
        slug=workspace.workspace.slug,
        role=workspace.role,
    )


def workspace_member_response(member) -> WorkspaceMemberResponse:
    return WorkspaceMemberResponse(
        id=member.membership.id,
        workspace_id=member.membership.workspace_id,
        user_id=member.user.id,
        email=member.user.email,
        display_name=member.user.display_name,
        role=member.membership.role,
    )
