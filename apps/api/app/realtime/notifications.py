from app.models import Notification
from app.realtime.manager import manager
from app.realtime.serializers import notification_payload
from app.realtime.signal_bus import RealtimeSignalBus


async def publish_notifications(
    notifications: list[Notification],
    *,
    signal_bus: RealtimeSignalBus,
) -> None:
    for notification in notifications:
        payload = notification_payload(notification)
        await manager.send_user(notification.user_id, payload)
        await signal_bus.publish_user(user_id=notification.user_id, payload=payload)
