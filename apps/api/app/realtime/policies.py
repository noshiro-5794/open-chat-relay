from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Lane(StrEnum):
    DURABLE = "durable"
    COMMAND = "command"
    EVENT = "event"
    SIGNAL = "signal"
    TELEMETRY = "telemetry"


class Reliability(StrEnum):
    RELIABLE = "reliable"
    BEST_EFFORT = "best_effort"


class Ordering(StrEnum):
    ORDERED = "ordered"
    UNORDERED = "unordered"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class DeliveryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane: Lane
    reliability: Reliability
    ordering: Ordering
    priority: Priority = Priority.NORMAL
    ttl_ms: int | None = None
    ack: bool = False


DURABLE_DELIVERY = DeliveryPolicy(
    lane=Lane.DURABLE,
    reliability=Reliability.RELIABLE,
    ordering=Ordering.ORDERED,
    priority=Priority.NORMAL,
    ttl_ms=None,
    ack=True,
)

SIGNAL_DELIVERY = DeliveryPolicy(
    lane=Lane.SIGNAL,
    reliability=Reliability.BEST_EFFORT,
    ordering=Ordering.UNORDERED,
    priority=Priority.LOW,
    ttl_ms=5000,
    ack=False,
)
