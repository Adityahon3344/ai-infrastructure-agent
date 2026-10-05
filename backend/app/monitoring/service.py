"""
Pull-based monitoring: connects over SSH and gathers CPU/RAM/disk/load/uptime.
No agent needs to be installed on target servers. A scheduled job (see
automations/scheduler.py) calls `sample_server` periodically for every
registered server; results are also available on-demand via the API.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.connections.models import Connection
from app.connections.service import resolve_ssh_spec
from app.servers.models import Server, ServerMetricSample, ServerStatus
from app.tools.ssh_tool import SSHTool

_CMD = (
    "echo CPU:$(top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}') "
    "MEM:$(free | grep Mem | awk '{print ($3/$2)*100}') "
    "DISK:$(df -P / | tail -1 | awk '{print $5}' | tr -d '%') "
    "LOAD:$(cut -d' ' -f1 /proc/loadavg) "
    "UPTIME:$(cut -d'.' -f1 /proc/uptime)"
)


def sample_server(db: Session, server: Server, connection: Connection) -> ServerMetricSample | None:
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        result = tool.run(_CMD, timeout=20)
        if not result.success:
            server.status = ServerStatus.WARNING
            db.commit()
            return None
        values = dict(part.split(":", 1) for part in result.stdout.split() if ":" in part)
        cpu = float(values.get("CPU", 0) or 0)
        mem = float(values.get("MEM", 0) or 0)
        disk = float(values.get("DISK", 0) or 0)
        load = float(values.get("LOAD", 0) or 0)
        uptime = int(float(values.get("UPTIME", 0) or 0))

        sample = ServerMetricSample(server_id=server.id, cpu_percent=cpu, ram_percent=mem, disk_percent=disk,
                                     load_avg_1m=load, uptime_seconds=uptime, raw=values)
        db.add(sample)

        server.last_seen = datetime.now(timezone.utc)
        if disk > 90 or cpu > 95 or mem > 95:
            server.status = ServerStatus.CRITICAL
        elif disk > 75 or cpu > 80 or mem > 80:
            server.status = ServerStatus.WARNING
        else:
            server.status = ServerStatus.ONLINE
        db.commit()
        return sample
    except Exception:  # noqa: BLE001
        server.status = ServerStatus.OFFLINE
        db.commit()
        return None
    finally:
        tool.close()


def latest_metrics(db: Session, server_id: str) -> ServerMetricSample | None:
    return (
        db.query(ServerMetricSample)
        .filter(ServerMetricSample.server_id == server_id)
        .order_by(ServerMetricSample.timestamp.desc())
        .first()
    )


def history(db: Session, server_id: str, limit: int = 100) -> list[ServerMetricSample]:
    return (
        db.query(ServerMetricSample)
        .filter(ServerMetricSample.server_id == server_id)
        .order_by(ServerMetricSample.timestamp.desc())
        .limit(limit)
        .all()
    )
