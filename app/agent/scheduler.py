from apscheduler.schedulers.background import BackgroundScheduler

from app.agent.scan_schedule_manager import scan_schedule_manager
from app.agent.scheduled_job_registry import scheduled_job_registry


class AgentScheduler:
    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()
        self._registered = False

    def register_jobs(self) -> None:
        if self._registered:
            return

        schedule = scan_schedule_manager.get_default_schedule()

        if schedule.automatic_scans_enabled:
            self._registered = True

    def start(self) -> None:
        self.register_jobs()

        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown()

    def is_running(self) -> bool:
        return self._scheduler.running

    def list_registered_jobs(self) -> list[dict]:
        return [
            {
                "job_name": job.job_name,
                "job_type": job.job_type,
                "description": job.description,
                "default_trigger": job.default_trigger,
            }
            for job in scheduled_job_registry.list_jobs()
        ]


agent_scheduler = AgentScheduler()