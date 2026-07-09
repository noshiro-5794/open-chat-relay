from collections import OrderedDict, defaultdict
from uuid import UUID

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class RealtimeConnectionManager:
    def __init__(self) -> None:
        self._room_connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._user_connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._connection_rooms: dict[WebSocket, set[UUID]] = defaultdict(set)
        self._connection_users: dict[WebSocket, UUID] = {}
        self._room_user_counts: dict[UUID, dict[UUID, int]] = defaultdict(lambda: defaultdict(int))
        self._recent_event_ids: OrderedDict[str, None] = OrderedDict()
        self._recent_event_capacity = 10_000

    def reset(self) -> None:
        self._room_connections.clear()
        self._user_connections.clear()
        self._connection_rooms.clear()
        self._connection_users.clear()
        self._room_user_counts.clear()
        self._recent_event_ids.clear()

    async def connect(self, websocket: WebSocket, user_id: UUID) -> None:
        self._connection_users[websocket] = user_id
        self._user_connections[user_id].add(websocket)

    def connection_user_id(self, websocket: WebSocket) -> UUID:
        return self._connection_users[websocket]

    async def subscribe(self, websocket: WebSocket, room_id: UUID) -> bool:
        user_id = self._connection_users[websocket]
        was_offline = self._room_user_counts[room_id][user_id] == 0
        self._room_connections[room_id].add(websocket)
        self._connection_rooms[websocket].add(room_id)
        self._room_user_counts[room_id][user_id] += 1
        return was_offline

    async def unsubscribe(self, websocket: WebSocket, room_id: UUID) -> bool:
        user_id = self._connection_users.get(websocket)
        if room_id not in self._connection_rooms.get(websocket, set()):
            return False

        self._room_connections[room_id].discard(websocket)
        self._connection_rooms[websocket].discard(room_id)
        if not self._room_connections[room_id]:
            del self._room_connections[room_id]
        if user_id is None:
            return False

        self._room_user_counts[room_id][user_id] -= 1
        if self._room_user_counts[room_id][user_id] > 0:
            return False

        del self._room_user_counts[room_id][user_id]
        if not self._room_user_counts[room_id]:
            del self._room_user_counts[room_id]
        return True

    async def disconnect(self, websocket: WebSocket) -> list[tuple[UUID, UUID]]:
        offline: list[tuple[UUID, UUID]] = []
        user_id = self._connection_users.get(websocket)
        room_ids = list(self._connection_rooms.get(websocket, set()))
        for room_id in room_ids:
            became_offline = await self.unsubscribe(websocket, room_id)
            if became_offline and user_id is not None:
                offline.append((room_id, user_id))
        self._connection_rooms.pop(websocket, None)
        removed_user_id = self._connection_users.pop(websocket, None)
        if removed_user_id is not None:
            self._user_connections[removed_user_id].discard(websocket)
            if not self._user_connections[removed_user_id]:
                del self._user_connections[removed_user_id]
        return offline

    def room_presence(self, room_id: UUID) -> list[UUID]:
        return sorted(self._room_user_counts.get(room_id, {}))

    def stats(self) -> dict[str, int]:
        return {
            "active_connections": len(self._connection_users),
            "active_users": len(self._user_connections),
            "subscribed_rooms": len(self._room_connections),
            "room_subscriptions": sum(
                len(connections) for connections in self._room_connections.values()
            ),
        }

    def has_seen_event(self, event_id: str) -> bool:
        return event_id in self._recent_event_ids

    async def broadcast_room(
        self,
        room_id: UUID,
        payload: dict,
        *,
        exclude: WebSocket | None = None,
        remember_event: bool = True,
    ) -> None:
        if remember_event:
            self._remember_event(payload)

        stale_connections: list[WebSocket] = []
        for websocket in list(self._room_connections.get(room_id, set())):
            if websocket == exclude:
                continue
            try:
                await websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                stale_connections.append(websocket)

        for websocket in stale_connections:
            await self.disconnect(websocket)

    async def send_user(self, user_id: UUID, payload: dict) -> None:
        stale_connections: list[WebSocket] = []
        for websocket in list(self._user_connections.get(user_id, set())):
            try:
                await websocket.send_json(payload)
            except (RuntimeError, WebSocketDisconnect):
                stale_connections.append(websocket)

        for websocket in stale_connections:
            await self.disconnect(websocket)

    def _remember_event(self, payload: dict) -> None:
        event_id = payload.get("event_id")
        if not isinstance(event_id, str):
            return

        self._recent_event_ids[event_id] = None
        self._recent_event_ids.move_to_end(event_id)
        while len(self._recent_event_ids) > self._recent_event_capacity:
            self._recent_event_ids.popitem(last=False)


manager = RealtimeConnectionManager()
