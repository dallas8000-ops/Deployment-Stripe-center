from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable


@dataclass
class PipelineEvent:
    step: str
    status: str  # running | ok | failed | detail
    message: str
    detail: bool = False
    score: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


EventEmitter = Callable[[PipelineEvent], None]


def emit(on_event: EventEmitter | None, event: PipelineEvent) -> None:
    if on_event:
        on_event(event)
