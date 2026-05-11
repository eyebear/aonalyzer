from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AgentRun


class AgentStatusReporter:
    def get_latest_run(self, session: Session) -> AgentRun | None:
        statement = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(1)
        return session.scalars(statement).first()

    def list_recent_runs(self, session: Session, limit: int = 25) -> list[AgentRun]:
        statement = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
        return list(session.scalars(statement).all())

    def get_status_summary(self, session: Session) -> dict:
        latest_run = self.get_latest_run(session)

        if latest_run is None:
            return {
                "status": "no_runs_recorded",
                "latest_run_id": None,
                "latest_job_name": None,
                "latest_job_status": None,
                "latest_started_at": None,
                "latest_finished_at": None,
            }

        return {
            "status": "has_runs",
            "latest_run_id": latest_run.id,
            "latest_job_name": latest_run.job_name,
            "latest_job_status": latest_run.status,
            "latest_started_at": latest_run.started_at,
            "latest_finished_at": latest_run.finished_at,
        }

    def run_to_dict(self, agent_run: AgentRun) -> dict:
        duration_seconds = agent_run.duration_seconds

        if isinstance(duration_seconds, Decimal):
            duration_seconds = float(duration_seconds)

        return {
            "id": agent_run.id,
            "job_name": agent_run.job_name,
            "job_type": agent_run.job_type,
            "status": agent_run.status,
            "started_at": agent_run.started_at,
            "finished_at": agent_run.finished_at,
            "duration_seconds": duration_seconds,
            "triggered_by": agent_run.triggered_by,
            "trigger_source": agent_run.trigger_source,
            "symbols_processed": agent_run.symbols_processed,
            "records_created": agent_run.records_created,
            "records_updated": agent_run.records_updated,
            "records_failed": agent_run.records_failed,
            "error_message": agent_run.error_message,
        }


agent_status_reporter = AgentStatusReporter()