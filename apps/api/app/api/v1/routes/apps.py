from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.app import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    AppCreateRequest,
    AppResponse,
    BotResponse,
    CreatedApiKeyResponse,
    CreatedIncomingWebhookResponse,
    IncomingWebhookCreateRequest,
    IncomingWebhookResponse,
)
from app.services.app import (
    ApiKeyNotFoundError,
    AppNotFoundError,
    AppSlugAlreadyExistsError,
    BotNotFoundError,
    IncomingWebhookNotFoundError,
    WorkspaceOwnerRequiredError,
    create_api_key,
    create_app,
    create_incoming_webhook,
    get_app_for_owner,
    get_bot_for_app,
    list_api_keys,
    list_incoming_webhooks,
    list_workspace_apps,
    revoke_api_key,
    revoke_incoming_webhook,
)
from app.services.workspace import RoomNotFoundError, WorkspaceNotFoundError

workspace_router = APIRouter(prefix="/workspaces/{workspace_id}/apps", tags=["apps"])
app_router = APIRouter(prefix="/apps/{app_id}", tags=["apps"])


@workspace_router.post("", response_model=AppResponse, status_code=status.HTTP_201_CREATED)
async def create_app_endpoint(
    workspace_id: UUID,
    payload: AppCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> AppResponse:
    try:
        app = await create_app(
            session,
            user=current_user,
            workspace_id=workspace_id,
            name=payload.name,
            slug=payload.slug,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage apps.",
        ) from exc
    except AppSlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="App slug is already in use.",
        ) from exc

    return await app_response(session, app)


@workspace_router.get("", response_model=list[AppResponse])
async def list_workspace_apps_endpoint(
    workspace_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[AppResponse]:
    try:
        apps = await list_workspace_apps(session, user=current_user, workspace_id=workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage apps.",
        ) from exc

    return [await app_response(session, app) for app in apps]


@app_router.get("", response_model=AppResponse)
async def get_app_endpoint(
    app_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> AppResponse:
    try:
        app = await get_app_for_owner(session, user=current_user, app_id=app_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found.") from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage apps.",
        ) from exc

    return await app_response(session, app)


@app_router.post(
    "/api-keys",
    response_model=CreatedApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key_endpoint(
    app_id: UUID,
    payload: ApiKeyCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> CreatedApiKeyResponse:
    try:
        created = await create_api_key(session, user=current_user, app_id=app_id, name=payload.name)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found.") from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage API keys.",
        ) from exc

    return CreatedApiKeyResponse(
        api_key=ApiKeyResponse.model_validate(created.api_key),
        secret=created.secret,
    )


@app_router.post(
    "/incoming-webhooks",
    response_model=CreatedIncomingWebhookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_incoming_webhook_endpoint(
    app_id: UUID,
    payload: IncomingWebhookCreateRequest,
    request: Request,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> CreatedIncomingWebhookResponse:
    try:
        created = await create_incoming_webhook(
            session,
            user=current_user,
            app_id=app_id,
            room_id=payload.room_id,
            name=payload.name,
        )
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found.") from exc
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage incoming webhooks.",
        ) from exc

    delivery_path = request.url_for(
        "deliver_incoming_webhook_endpoint",
        webhook_id=str(created.webhook.id),
    ).path
    return CreatedIncomingWebhookResponse(
        webhook=IncomingWebhookResponse.model_validate(created.webhook),
        secret=created.secret,
        delivery_url=delivery_path,
    )


@app_router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys_endpoint(
    app_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[ApiKeyResponse]:
    try:
        api_keys = await list_api_keys(session, user=current_user, app_id=app_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found.") from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage API keys.",
        ) from exc

    return [ApiKeyResponse.model_validate(api_key) for api_key in api_keys]


@app_router.get("/incoming-webhooks", response_model=list[IncomingWebhookResponse])
async def list_incoming_webhooks_endpoint(
    app_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[IncomingWebhookResponse]:
    try:
        webhooks = await list_incoming_webhooks(session, user=current_user, app_id=app_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found.") from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage incoming webhooks.",
        ) from exc

    return [IncomingWebhookResponse.model_validate(webhook) for webhook in webhooks]


@app_router.post("/api-keys/{api_key_id}/revoke", response_model=ApiKeyResponse)
async def revoke_api_key_endpoint(
    app_id: UUID,
    api_key_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> ApiKeyResponse:
    try:
        api_key = await revoke_api_key(
            session,
            user=current_user,
            app_id=app_id,
            api_key_id=api_key_id,
        )
    except (AppNotFoundError, ApiKeyNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found.",
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage API keys.",
        ) from exc

    return ApiKeyResponse.model_validate(api_key)


@app_router.post(
    "/incoming-webhooks/{webhook_id}/revoke",
    response_model=IncomingWebhookResponse,
)
async def revoke_incoming_webhook_endpoint(
    app_id: UUID,
    webhook_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> IncomingWebhookResponse:
    try:
        webhook = await revoke_incoming_webhook(
            session,
            user=current_user,
            app_id=app_id,
            webhook_id=webhook_id,
        )
    except (AppNotFoundError, IncomingWebhookNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incoming webhook not found.",
        ) from exc
    except WorkspaceOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners can manage incoming webhooks.",
        ) from exc

    return IncomingWebhookResponse.model_validate(webhook)


async def app_response(session: DbSessionDep, app) -> AppResponse:
    try:
        bot = await get_bot_for_app(session, app_id=app.id)
    except BotNotFoundError:
        bot = None

    return AppResponse(
        id=app.id,
        workspace_id=app.workspace_id,
        created_by_id=app.created_by_id,
        name=app.name,
        slug=app.slug,
        created_at=app.created_at,
        bot=BotResponse.model_validate(bot) if bot is not None else None,
    )
