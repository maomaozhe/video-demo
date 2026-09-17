from dataclasses import dataclass, field


@dataclass(frozen=True)
class Evidence:
    timestamp_ms: int
    frame_id: str


@dataclass(frozen=True)
class Event:
    start_ms: int
    end_ms: int
    action: str
    person_id: str | None = None
    status: str = "观察到"
    evidence: list[Evidence] = field(default_factory=list)


def validate_event(event: Event, duration_ms: int) -> None:
    if event.start_ms < 0 or event.end_ms <= event.start_ms:
        raise ValueError("invalid event time range")
    if event.end_ms > duration_ms:
        raise ValueError("event exceeds video duration")
    if event.status == "已完成" and not event.evidence:
        raise ValueError("completed action requires evidence")
    for evidence in event.evidence:
        if not event.start_ms <= evidence.timestamp_ms <= event.end_ms:
            raise ValueError("evidence timestamp is outside event")
