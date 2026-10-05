"""
APScheduler-backed automation runner. Each enabled Automation gets a cron
trigger; when it fires, the saved prompt is replayed through the same
`app.agent.orchestrator.handle_message` pipeline used for live chat, so
scheduled work gets identical validation/risk/approval treatment.
"""
from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal
from app.core.logging_config import get_logger

logger = get_logger("automations.scheduler")
scheduler = BackgroundScheduler()


def _run_automation(automation_id: str) -> None:
    from app.agent.orchestrator import handle_message
    from app.automations.models import Automation

    db = SessionLocal()
    try:
        automation = db.get(Automation, automation_id)
        if not automation or not automation.enabled:
            return
        result = handle_message(
            db, user_id=automation.user_id, conversation_id=f"automation:{automation.id}",
            text=automation.prompt, selected_server_ids=automation.target_server_ids or None,
        )
        automation.last_run_at = datetime.now(timezone.utc)
        automation.last_job_id = result.job_id
        db.commit()
        logger.info(f"Automation '{automation.name}' executed -> job {result.job_id}")
    except Exception:  # noqa: BLE001
        logger.exception(f"Automation {automation_id} failed to run")
    finally:
        db.close()


def schedule_automation(automation_id: str, cron_expression: str) -> None:
    fields = cron_expression.split()
    if len(fields) != 5:
        raise ValueError("cron_expression must have 5 fields: minute hour day month day_of_week")
    minute, hour, day, month, day_of_week = fields
    trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
    scheduler.add_job(_run_automation, trigger=trigger, args=[automation_id], id=automation_id, replace_existing=True)


def unschedule_automation(automation_id: str) -> None:
    if scheduler.get_job(automation_id):
        scheduler.remove_job(automation_id)


def start_scheduler() -> None:
    from app.automations.models import Automation

    db = SessionLocal()
    try:
        for automation in db.query(Automation).filter(Automation.enabled == True).all():  # noqa: E712
            try:
                schedule_automation(automation.id, automation.cron_expression)
            except Exception:  # noqa: BLE001
                logger.exception(f"Failed to schedule automation {automation.id}")
    finally:
        db.close()
    if not scheduler.running:
        scheduler.start()
