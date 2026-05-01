from dataclasses import dataclass


@dataclass(frozen=True)
class EventDelta:
    views_delta: int
    likes_delta: int
    skips_delta: int
    use_completion_rate: bool
    interest_delta: float


EVENT_DELTA_MAP: dict[str, EventDelta] = {
    "watch":    EventDelta(views_delta=0, likes_delta=0, skips_delta=0, use_completion_rate=False, interest_delta=0.02),
    "like":     EventDelta(views_delta=0, likes_delta=1, skips_delta=0, use_completion_rate=False, interest_delta=0.10),
    "skip":     EventDelta(views_delta=0, likes_delta=0, skips_delta=1, use_completion_rate=False, interest_delta=-0.08),
    "complete": EventDelta(views_delta=1, likes_delta=0, skips_delta=0, use_completion_rate=True,  interest_delta=0.06),
    "share":    EventDelta(views_delta=0, likes_delta=0, skips_delta=0, use_completion_rate=False, interest_delta=0.08),
    "comment":  EventDelta(views_delta=0, likes_delta=0, skips_delta=0, use_completion_rate=False, interest_delta=0.04),
}
