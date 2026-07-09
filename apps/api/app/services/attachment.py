import re
from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attachment, AttachmentStatus, User
from app.services.message import RoomMembershipRequiredError
from app.services.workspace import get_room_for_user
from app.storage.service import StorageService

_filename_pattern = re.compile(r"[^a-zA-Z0-9._-]+")


class AttachmentNotFoundError(Exception):
    """Raised when an attachment cannot be found or cannot be used by the user."""


class AttachmentAlreadyAttachedError(Exception):
    """Raised when an attachment is already bound to a message."""


class AttachmentUploadNotFoundError(Exception):
    """Raised when object storage does not contain the uploaded attachment."""


class AttachmentUploadMismatchError(Exception):
    """Raised when object storage metadata does not match the attachment intent."""


async def create_attachment_intent(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    filename: str,
    content_type: str,
    size_bytes: int,
) -> Attachment:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomMembershipRequiredError

    attachment = Attachment(
        workspace_id=room_with_role.room.workspace_id,
        room_id=room_with_role.room.id,
        uploader_id=user.id,
        filename=filename.strip(),
        content_type=content_type.strip().lower(),
        size_bytes=size_bytes,
        storage_key=create_storage_key(
            workspace_id=room_with_role.room.workspace_id,
            room_id=room_with_role.room.id,
            filename=filename,
        ),
        status=AttachmentStatus.PENDING_UPLOAD.value,
    )
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)
    return attachment


async def confirm_attachment_upload(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    attachment_id: UUID,
    storage_service: StorageService,
    verify_upload: bool,
) -> Attachment:
    attachment = await get_owned_room_attachment(
        session,
        user=user,
        room_id=room_id,
        attachment_id=attachment_id,
    )
    if attachment.message_id is not None:
        raise AttachmentAlreadyAttachedError

    if verify_upload:
        uploaded_object = storage_service.head_object(storage_key=attachment.storage_key)
        if uploaded_object is None:
            raise AttachmentUploadNotFoundError
        if uploaded_object.size_bytes != attachment.size_bytes:
            raise AttachmentUploadMismatchError
        if (
            uploaded_object.content_type is not None
            and uploaded_object.content_type.lower() != attachment.content_type
        ):
            raise AttachmentUploadMismatchError

    attachment.status = AttachmentStatus.UPLOADED.value
    await session.commit()
    await session.refresh(attachment)
    return attachment


async def get_downloadable_attachment(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    attachment_id: UUID,
) -> Attachment:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomMembershipRequiredError

    statement = select(Attachment).where(
        Attachment.id == attachment_id,
        Attachment.room_id == room_with_role.room.id,
        Attachment.status.in_(
            [
                AttachmentStatus.UPLOADED.value,
                AttachmentStatus.ATTACHED.value,
            ]
        ),
    )
    result = await session.execute(statement)
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise AttachmentNotFoundError
    return attachment


async def get_owned_room_attachment(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    attachment_id: UUID,
) -> Attachment:
    statement = select(Attachment).where(
        Attachment.id == attachment_id,
        Attachment.room_id == room_id,
        Attachment.uploader_id == user.id,
    )
    result = await session.execute(statement)
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise AttachmentNotFoundError
    return attachment


async def get_attachable_attachments(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    attachment_ids: Sequence[UUID],
) -> list[Attachment]:
    if not attachment_ids:
        return []

    statement = select(Attachment).where(
        Attachment.id.in_(attachment_ids),
        Attachment.room_id == room_id,
        Attachment.uploader_id == user.id,
        Attachment.message_id.is_(None),
        Attachment.status == AttachmentStatus.UPLOADED.value,
    )
    result = await session.execute(statement)
    attachments = list(result.scalars().all())
    if len(attachments) != len(set(attachment_ids)):
        raise AttachmentNotFoundError
    return attachments


async def list_attachments_for_messages(
    session: AsyncSession,
    *,
    message_ids: Sequence[UUID],
) -> dict[UUID, list[Attachment]]:
    if not message_ids:
        return {}

    statement = (
        select(Attachment)
        .where(Attachment.message_id.in_(message_ids))
        .order_by(Attachment.created_at)
    )
    result = await session.execute(statement)
    attachments_by_message: dict[UUID, list[Attachment]] = {}
    for attachment in result.scalars().all():
        if attachment.message_id is None:
            continue
        attachments_by_message.setdefault(attachment.message_id, []).append(attachment)
    return attachments_by_message


def attachment_payload(attachment: Attachment) -> dict:
    return {
        "id": str(attachment.id),
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "storage_key": attachment.storage_key,
        "status": attachment.status,
    }


def create_storage_key(*, workspace_id: UUID, room_id: UUID, filename: str) -> str:
    safe_filename = _filename_pattern.sub("-", filename.strip()).strip("-") or "file"
    return f"workspaces/{workspace_id}/rooms/{room_id}/attachments/{uuid4()}-{safe_filename}"
