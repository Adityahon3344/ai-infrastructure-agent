"""
The Execution Engine: takes an approved, compiled plan and actually runs it —
one target at a time (or in a small thread pool for multi-server jobs),
emitting a live event stream, persisting JobEvents, running verification after
each step, and attempting controlled self-healing on retryable failures.

This module is intentionally the only place that turns a CompiledPlan into
real side effects. Everything upstream (agent, planner, validator, risk,
approval) only ever produces/approves data structures.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import functools
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.compiler.compiler import CompiledPlan, compile_plan
from app.connections.models import Connection
from app.core.config import settings
from app.core.logging_config import LogContext, get_logger
from app.diagnostics.diagnoser import diagnose
from app.jobs.models import Job, JobEvent, JobStatus, TargetStatus
from app.planner.planspec import PlanSpec
from app.self_healing.healer import maybe_self_heal
from app.servers.models import Server
from app.streaming.manager import next_sequence, stream_manager
from app.tools.router import ExecutionContext, dispatch
from app.verification.verifier import verify_step

logger = get_logger("execution")


def _persist_event(db: Session, job_id: str, event_type: str, message: str = "", server_id: str | None = None,
                    tool: str | None = None, data: dict | None = None) -> dict:
    ev = JobEvent(job_id=job_id, sequence=next_sequence(), event_type=event_type, server_id=server_id,
                  tool=tool, message=message, data=data or {})
    db.add(ev)
    db.commit()
    return {
        "type": event_type, "job_id": job_id, "server_id": server_id, "tool": tool,
        "message": message, "data": data or {}, "timestamp": ev.timestamp.isoformat(),
    }


def _emit(loop: asyncio.AbstractEventLoop, db: Session, job_id: str, event_type: str, message: str = "",
          server_id: str | None = None, tool: str | None = None, data: dict | None = None) -> None:
    payload = _persist_event(db, job_id, event_type, message, server_id, tool, data)
    stream_manager.publish_threadsafe(loop, job_id, payload)


def _run_one_target(
    loop: asyncio.AbstractEventLoop,
    db_factory,
    job_id: str,
    plan: PlanSpec,
    compiled: CompiledPlan,
    server: Server | None,
    server_connection: Connection | None,
    cloud_connection: Connection | None,
) -> TargetStatus:
    db = db_factory()
    target_label = server.name if server else (cloud_connection.name if cloud_connection else "cloud")
    try:
        with LogContext(logger, job_id=job_id, server_id=(server.id if server else None)):
            if server:
                _emit(loop, db, job_id, "connecting", f"Connecting to {target_label}", server_id=server.id)

            ctx = ExecutionContext(server=server, server_connection=server_connection, cloud_connection=cloud_connection)
            overall_ok = True

            for task in compiled.tasks:
                _emit(loop, db, job_id, "task_started", task.description, server_id=(server.id if server else None), tool=task.kind)

                def on_output(stream: str, line: str, _server_id=(server.id if server else None), _tool=task.kind):
                    _emit(loop, db, job_id, "task_output", line, server_id=_server_id, tool=_tool, data={"stream": stream})

                result = dispatch(task, ctx, on_output=on_output)

                if not result.success:
                    def _retry():
                        return dispatch(task, ctx, on_output=on_output)

                    def _on_heal_event(evt_type: str, msg: str):
                        _emit(loop, db, job_id, evt_type, msg, server_id=(server.id if server else None), tool=task.kind)

                    outcome, retried_result = maybe_self_heal(_retry, result.stdout, result.stderr or (result.error or ""), _on_heal_event)
                    if retried_result is not None and getattr(retried_result, "success", False):
                        result = retried_result
                    else:
                        diagnosis = diagnose(result.stdout, result.stderr or (result.error or ""))
                        _emit(loop, db, job_id, "task_failed", diagnosis.human_explanation,
                              server_id=(server.id if server else None), tool=task.kind,
                              data={"category": diagnosis.category, "raw_error": result.error or result.stderr})
                        overall_ok = False
                        break

                _emit(loop, db, job_id, "task_completed", f"Completed: {task.description}", server_id=(server.id if server else None), tool=task.kind, data=result.data or {})

                if task.verify and server and server_connection:
                    v_results = verify_step(task.action, task.payload if isinstance(task.payload, dict) else {}, server, server_connection)
                    for v in v_results:
                        _emit(loop, db, job_id, "verification", v.message, server_id=server.id, data={"verified": v.verified})
                        if not v.verified:
                            overall_ok = False

            if server:
                _emit(loop, db, job_id, "connecting", f"Finished with {target_label}", server_id=server.id)
            return TargetStatus.SUCCESS if overall_ok else TargetStatus.FAILED
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Unhandled error executing target {target_label}")
        _emit(loop, db, job_id, "task_failed", f"Unhandled error: {exc}", server_id=(server.id if server else None))
        return TargetStatus.FAILED
    finally:
        db.close()


def execute_job(job_id: str, db_factory, loop: asyncio.AbstractEventLoop) -> None:
    """Entry point run in a background thread. Loads the job + validated plan,
    resolves targets, compiles, and executes with bounded parallelism across
    servers (MAX_PARALLEL_SERVER_EXECUTIONS, not a server-count cap)."""
    db = db_factory()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        plan = PlanSpec.model_validate(job.plan)
        compiled = compile_plan(plan)

        servers: list[Server] = []
        cloud_connection: Connection | None = None
        server_connections: dict[str, Connection] = {}

        if plan.target.kind == "servers":
            servers = db.query(Server).filter(Server.id.in_(plan.target.server_ids)).all()
            for s in servers:
                if s.connection_id:
                    conn = db.get(Connection, s.connection_id)
                    if conn:
                        server_connections[s.id] = conn
        else:
            cloud_connection = db.get(Connection, plan.target.connection_id) if plan.target.connection_id else None

        per_target_status: dict[str, str] = {}

        if servers:
            max_workers = min(len(servers), settings.max_parallel_server_executions)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(
                        _run_one_target, loop, db_factory, job_id, plan, compiled, s,
                        server_connections.get(s.id), None,
                    ): s
                    for s in servers
                }
                for future in concurrent.futures.as_completed(futures):
                    s = futures[future]
                    status = future.result()
                    per_target_status[s.id] = status.value
        else:
            status = _run_one_target(loop, db_factory, job_id, plan, compiled, None, None, cloud_connection)
            per_target_status[cloud_connection.id if cloud_connection else "cloud"] = status.value

        job = db.get(Job, job_id)
        job.per_target_status = per_target_status
        statuses = list(per_target_status.values())
        if all(s == TargetStatus.SUCCESS.value for s in statuses):
            job.status = JobStatus.SUCCESS
        elif any(s == TargetStatus.SUCCESS.value for s in statuses):
            job.status = JobStatus.PARTIAL_SUCCESS
        else:
            job.status = JobStatus.FAILED
        job.finished_at = datetime.now(timezone.utc)
        db.commit()

        _emit(loop, db, job_id, "job_completed" if job.status == JobStatus.SUCCESS else "job_failed",
              f"Job finished with status {job.status.value}", data={"per_target_status": per_target_status})

        # Update long-term memory with a successful outcome (non-secret only).
        if job.status in (JobStatus.SUCCESS, JobStatus.PARTIAL_SUCCESS):
            from app.memory.service import remember_successful_job
            remember_successful_job(db, job)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Job execution crashed")
        job = db.get(Job, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            _emit(loop, db, job_id, "job_failed", f"Job crashed: {exc}")
    finally:
        db.close()
