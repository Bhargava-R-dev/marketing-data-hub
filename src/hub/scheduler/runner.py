from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from hub.core.config import HubConfig
from hub.core.storage import Storage


def _sync_job(config: HubConfig, storage: Storage, source: str) -> None:
    from hub.connectors.catalog import build_connector
    from hub.core.sync import run_sync
    from hub.destinations.csv_export import run_export

    try:
        connector = build_connector(source, config)
        run_sync(storage, connector,
                 window_days=config.connectors[source].window_days)
        for exp in config.exports:
            if exp.sources is None or source in exp.sources:
                run_export(storage, exp, config.exports_dir)
    except Exception as exc:  # noqa: BLE001 - scheduler must never crash the process
        print(f"[scheduler] sync {source} failed: {exc}")


def build_scheduler(config: HubConfig, storage: Storage) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    for source, settings in config.connectors.items():
        scheduler.add_job(
            _sync_job,
            CronTrigger.from_crontab(settings.schedule),
            args=[config, storage, source],
            id=f"sync_{source}",
            max_instances=1,
            coalesce=True,
        )
    return scheduler
