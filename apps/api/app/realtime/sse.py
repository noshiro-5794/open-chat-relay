import json

from app.models import Event
from app.realtime.serializers import event_to_realtime_payload


def format_sse_event(event: Event) -> str:
    event_id = event.room_event_seq or event.workspace_event_seq
    data = json.dumps(event_to_realtime_payload(event), separators=(",", ":"), default=str)
    return f"id: {event_id}\nevent: {event.event_type}\ndata: {data}\n\n"


def sse_heartbeat() -> str:
    return ": heartbeat\n\n"
