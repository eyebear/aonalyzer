from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import AgentRun


class JobRunLogger:
    def start_job(
        self,
        session: Session,
        job_name: str,
        job_type: str,
        triggered_by: str,
        trigger_source: str,
    ) -> AgentRun:
        agent_run = AgentRun(
            job_name=job_name,
            job_type=job_type,
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            duration_seconds=None,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            symbols_processed=0,
            records_created=0,
            records_updated=0,
            records_failed=0,
            error_message=None,
        )

        session.add(agent_run)
        session.commit()
        session.refresh(agent_run)

        return agent_run

    def finish_job_success(
        self,
        session: Session,
        agent_run: AgentRun,
        symbols_processed: int = 0,
        records_created: int = 0,
        records_updated: int = 0,
        records_failed: int = 0,
    ) -> AgentRun:
        finished_at = datetime.now(timezone.utc)

        agent_run.status = "SUCCESS"
        agent_run.finished_at = finished_at
        agent_run.duration_seconds = self._duration_seconds(agent_run.started_at, finished_at)
        agent_run.symbols_processed = symbols_processed
        agent_run.records_created = records_created
        agent_run.records_updated = records_updated
        agent_run.records_failed = records_failed

        session.add(agent_run)
        session.commit()
        session.refresh(agent_run)

        return agent_run

    def finish_job_failure(
        self,
        session: Session,
        agent_run: AgentRun,
        error_message: str,
        symbols_processed: int = 0,
        records_created: int = 0,
        records_updated: int = 0,
        records_failed: int = 1,
    ) -> AgentRun:
        finished_at = datetime.now(timezone.utc)

        agent_run.status = "FAILED"
        agent_run.finished_at = finished_at
        agent_run.duration_seconds = self._duration_seconds(agent_run.started_at, finished_at)
        agent_run.symbols_processed = symbols_processed
        agent_run.records_created = records_created
        agent_run.records_updated = records_updated
        agent_run.records_failed = records_failed
        agent_run.error_message = error_message

        session.add(agent_run)
        session.commit()
        session.refresh(agent_run)

        return agent_run

    def run_logged_job(
        self,
        session: Session,
        job_name: str,
        job_type: str,
        triggered_by: str,
        trigger_source: str,
        job_function: Callable[[], dict[str, Any]],
    ) -> AgentRun:
        agent_run = self.start_job(
            session=session,
            job_name=job_name,
            job_type=job_type,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
        )

        try:
            result = job_function()

            return self.finish_job_success(
                session=session,
                agent_run=agent_run,
                symbols_processed=int(result.get("symbols_processed", 0)),
                records_created=int(result.get("records_created", 0)),
                records_updated=int(result.get("records_updated", 0)),
                records_failed=int(result.get("records_failed", 0)),
            )
        except Exception as exc:
            return self.finish_job_failure(
                session=session,
                agent_run=agent_run,
                error_message=str(exc),
            )

    def _duration_seconds(self, started_at: datetime, finished_at: datetime) -> float:
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=timezone.utc)

        return round((finished_at - started_at).total_seconds(), 3)


job_run_logger = JobRunLogger()