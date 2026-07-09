from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
from app.schemas.attachment import (
    AttachmentCreateRequest,
    AttachmentDownloadIntentResponse,
    AttachmentResponse,
    AttachmentUploadIntentResponse,
)
from app.services.attachment import (
    AttachmentAlreadyAttachedError,
    AttachmentNotFoundError,
    AttachmentUploadMismatchError,
    AttachmentUploadNotFoundError,
    confirm_attachment_upload,
    create_attachment_intent,
    get_downloadable_attachment,
)
from app.services.message import RoomMembershipRequiredError
from app.services.workspace import RoomNotFoundError
from app.storage.service import StorageService

router = APIRouter(prefix="/rooms/{room_id}/attachments", tags=["attachments"])


@router.post("", response_model=AttachmentUploadIntentResponse, status_code=status.HTTP_201_CREATED)
async def create_attachment_endpoint(
    room_id: UUID,
    payload: AttachmentCreateRequest,
    session: DbSessionDep,
    settings: SettingsDep,
    current_user: CurrentUserDep,
) -> AttachmentUploadIntentResponse:
    try:
        attachment = await create_attachment_intent(
            session,
            user=current_user,
            room_id=room_id,
            filename=payload.filename,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before creating attachments.",
        ) from exc

    return AttachmentUploadIntentResponse(
        attachment=AttachmentResponse.model_validate(attachment),
        upload_url=StorageService(settings).create_presigned_upload_url(
            storage_key=attachment.storage_key,
            content_type=attachment.content_type,
        ),
    )


@router.post("/{attachment_id}/confirm", response_model=AttachmentResponse)
async def confirm_attachment_endpoint(
    room_id: UUID,
    attachment_id: UUID,
    session: DbSessionDep,
    settings: SettingsDep,
    current_user: CurrentUserDep,
) -> AttachmentResponse:
    try:
        attachment = await confirm_attachment_upload(
            session,
            user=current_user,
            room_id=room_id,
            attachment_id=attachment_id,
            storage_service=StorageService(settings),
            verify_upload=settings.effective_verify_attachment_uploads(),
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        ) from exc
    except AttachmentAlreadyAttachedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attachment is already attached to a message.",
        ) from exc
    except AttachmentUploadNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attachment object has not been uploaded.",
        ) from exc
    except AttachmentUploadMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Attachment object metadata does not match the upload intent.",
        ) from exc

    return AttachmentResponse.model_validate(attachment)


@router.get("/{attachment_id}/download", response_model=AttachmentDownloadIntentResponse)
async def create_attachment_download_endpoint(
    room_id: UUID,
    attachment_id: UUID,
    session: DbSessionDep,
    settings: SettingsDep,
    current_user: CurrentUserDep,
) -> AttachmentDownloadIntentResponse:
    try:
        attachment = await get_downloadable_attachment(
            session,
            user=current_user,
            room_id=room_id,
            attachment_id=attachment_id,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before downloading attachments.",
        ) from exc
    except AttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        ) from exc

    return AttachmentDownloadIntentResponse(
        attachment=AttachmentResponse.model_validate(attachment),
        download_url=StorageService(settings).create_presigned_download_url(
            storage_key=attachment.storage_key,
            filename=attachment.filename,
            content_type=attachment.content_type,
        ),
        expires_in_seconds=settings.s3_presigned_download_expire_seconds,
    )
