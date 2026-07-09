from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROTOCOL_VERSION = "ocr.realtime.v1"
COMMAND_ROOM_SUBSCRIBE = "room.subscribe"
COMMAND_ROOM_UNSUBSCRIBE = "room.unsubscribe"
COMMAND_MESSAGE_SEND = "message.send"
COMMAND_PRESENCE_UPDATE = "presence.update"
COMMAND_TYPING_UPDATE = "typing.update"

SUPPORTED_COMMANDS = [
    COMMAND_ROOM_SUBSCRIBE,
    COMMAND_ROOM_UNSUBSCRIBE,
    COMMAND_MESSAGE_SEND,
    COMMAND_PRESENCE_UPDATE,
    COMMAND_TYPING_UPDATE,
]

SUPPORTED_EVENT_TYPES = [
    "message.created",
    "message.updated",
    "message.deleted",
    "message.reaction_added",
    "message.reaction_removed",
    "notification.created",
    "presence.updated",
    "room.read_state_updated",
    "typing.updated",
]


class ProtocolError(Exception):
    def __init__(self, *, code: str, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = request_id


class InboundCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    request_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class RoomCommandData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: UUID


class RoomSubscribeData(RoomCommandData):
    last_event_seq: int | None = Field(default=None, ge=0)


class MessageSendData(RoomCommandData):
    content: str = Field(min_length=1, max_length=8000)
    reply_to_id: UUID | None = None


class PresenceUpdateData(RoomCommandData):
    status: Literal["online", "away", "busy"]


class TypingUpdateData(RoomCommandData):
    status: Literal["started", "stopped"]


def parse_inbound_command(raw: Any) -> InboundCommand:
    if not isinstance(raw, dict):
        raise ProtocolError(code="invalid_command", message="Command must be an object.")

    command_type = raw.get("type")
    if not isinstance(command_type, str) or not command_type:
        raise ProtocolError(code="invalid_command", message="Command type is required.")

    request_id = raw.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise ProtocolError(code="invalid_command", message="request_id must be a string.")

    data = raw.get("data", {})
    if not isinstance(data, dict):
        raise ProtocolError(
            code="invalid_command",
            message="Command data must be an object.",
            request_id=request_id,
        )

    return InboundCommand(type=command_type, request_id=request_id, data=data)


def parse_command_data[DataModel: BaseModel](
    command: InboundCommand,
    model: type[DataModel],
    *,
    code: str,
    message: str,
) -> DataModel:
    try:
        return model.model_validate(command.data)
    except ValidationError as exc:
        raise ProtocolError(code=code, message=message, request_id=command.request_id) from exc
