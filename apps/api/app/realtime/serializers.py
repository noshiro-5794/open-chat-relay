from app.models import Event, Notification
from app.realtime.policies import SIGNAL_DELIVERY


def event_to_realtime_payload(event: Event) -> dict:
    return {
        "type": event.event_type,
        "event_id": str(event.id),
        "workspace_id": str(event.workspace_id),
        "room_id": str(event.room_id) if event.room_id else None,
        "actor_type": event.actor_type,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "actor_bot_id": str(event.actor_bot_id) if event.actor_bot_id else None,
        "room_event_seq": event.room_event_seq,
        "workspace_event_seq": event.workspace_event_seq,
        "created_at": event.created_at.isoformat(),
        "delivery": {
            "lane": event.lane,
            "reliability": event.reliability,
            "ordering": event.ordering,
            "priority": event.priority,
            "ttl_ms": event.ttl_ms,
        },
        "data": event.payload,
    }


def presence_payload(*, room_id: str, user_id: str, status: str) -> dict:
    return {
        "type": "presence.updated",
        "room_id": room_id,
        "actor_id": user_id,
        "delivery": {
            "lane": SIGNAL_DELIVERY.lane.value,
            "reliability": SIGNAL_DELIVERY.reliability.value,
            "ordering": SIGNAL_DELIVERY.ordering.value,
            "priority": SIGNAL_DELIVERY.priority.value,
            "ttl_ms": SIGNAL_DELIVERY.ttl_ms,
        },
        "data": {
            "user_id": user_id,
            "status": status,
        },
    }


def typing_payload(*, room_id: str, user_id: str, status: str) -> dict:
    return {
        "type": "typing.updated",
        "room_id": room_id,
        "actor_id": user_id,
        "delivery": {
            "lane": SIGNAL_DELIVERY.lane.value,
            "reliability": SIGNAL_DELIVERY.reliability.value,
            "ordering": SIGNAL_DELIVERY.ordering.value,
            "priority": SIGNAL_DELIVERY.priority.value,
            "ttl_ms": SIGNAL_DELIVERY.ttl_ms,
        },
        "data": {
            "room_id": room_id,
            "user_id": user_id,
            "status": status,
        },
    }


def notification_payload(notification: Notification) -> dict:
    return {
        "type": "notification.created",
        "notification_id": str(notification.id),
        "user_id": str(notification.user_id),
        "workspace_id": str(notification.workspace_id),
        "room_id": str(notification.room_id) if notification.room_id else None,
        "event_id": str(notification.event_id),
        "created_at": notification.created_at.isoformat(),
        "data": {
            "notification_type": notification.notification_type,
            "title": notification.title,
            "body": notification.body,
            "payload": notification.payload,
        },
    }


def ack_payload(*, request_id: str | None, event_id: str | None = None) -> dict:
    return {
        "type": "ack",
        "request_id": request_id,
        "status": "ok",
        "event_id": event_id,
    }


def error_payload(*, request_id: str | None, code: str, message: str) -> dict:
    return {
        "type": "error",
        "request_id": request_id,
        "code": code,
        "message": message,
    }
