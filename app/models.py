import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobState(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, name="jobstate"), nullable=False, default=JobState.queued
    )
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=_utcnow,
    )

    def transition_to(self, new_state: JobState) -> None:
        """Apply a state transition. Raises ValueError on invalid transitions."""
        valid: dict[JobState, set[JobState]] = {
            JobState.queued: {JobState.running},
            JobState.running: {JobState.done, JobState.failed, JobState.queued},
            JobState.done: set(),
            JobState.failed: set(),
        }
        allowed = valid.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"Cannot transition from {self.state!r} to {new_state!r}")
        self.state = new_state

    def __repr__(self) -> str:
        return f"<Job id={self.id!r} state={self.state!r}>"
