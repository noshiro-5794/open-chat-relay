from typing import Protocol

from app.realtime.envelopes import CommandEnvelope, EventEnvelope


class TransportAdapter(Protocol):
    name: str

    async def receive_command(self) -> CommandEnvelope:
        """Receive one command from the connected client."""
        ...

    async def send_event(self, event: EventEnvelope) -> None:
        """Send one event to the connected client."""
        ...

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the transport session."""
        ...
