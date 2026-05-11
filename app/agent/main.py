import time
from datetime import datetime, timezone

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()

    print(
        {
            "service": "aoaoanalyzer-agent",
            "status": "started",
            "app_name": settings.app_name,
            "environment": settings.app_env,
            "database_host": settings.postgres_host,
            "redis_host": settings.redis_host,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
        flush=True,
    )

    while True:
        print(
            {
                "service": "aoaoanalyzer-agent",
                "status": "running",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            flush=True,
        )
        time.sleep(60)


if __name__ == "__main__":
    main()