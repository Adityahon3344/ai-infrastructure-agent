"""Server discovery: connects over SSH and gathers real facts (OS, CPU, RAM,
disk, architecture, installed capabilities). Uses the SSHTool so behaviour is
identical to normal task execution (same timeouts, same audit trail)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.ssh_tool import SSHTool, SSHConnectionSpec, CommandResult


DISCOVERY_COMMANDS = {
    "os_release": "cat /etc/os-release 2>/dev/null || true",
    "kernel": "uname -srm",
    "cpu_count": "nproc",
    "ram_kb": "grep MemTotal /proc/meminfo | awk '{print $2}'",
    "disk_root": "df -Pk / | tail -1 | awk '{print $2, $3, $4}'",
    "hostname": "hostname",
    "docker": "command -v docker >/dev/null 2>&1 && docker --version || echo 'not-installed'",
    "python": "command -v python3 >/dev/null 2>&1 && python3 --version || echo 'not-installed'",
    "node": "command -v node >/dev/null 2>&1 && node --version || echo 'not-installed'",
    "java": "command -v java >/dev/null 2>&1 && java -version 2>&1 | head -1 || echo 'not-installed'",
    "systemd": "command -v systemctl >/dev/null 2>&1 && echo 'present' || echo 'absent'",
    "package_manager": (
        "if command -v apt-get >/dev/null 2>&1; then echo apt; "
        "elif command -v dnf >/dev/null 2>&1; then echo dnf; "
        "elif command -v yum >/dev/null 2>&1; then echo yum; "
        "else echo unknown; fi"
    ),
}


@dataclass
class DiscoveryResult:
    reachable: bool
    os_family: str = "linux"
    os_distribution: str = ""
    os_version: str = ""
    architecture: str = ""
    cpu_cores: int | None = None
    ram_mb: int | None = None
    disk_gb: float | None = None
    hostname: str = ""
    capabilities: dict = field(default_factory=dict)
    package_manager: str = "unknown"
    error: str | None = None
    raw: dict = field(default_factory=dict)


def _parse_os_release(text: str) -> tuple[str, str]:
    distro, version = "", ""
    for line in text.splitlines():
        if line.startswith("ID="):
            distro = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("VERSION_ID="):
            version = line.split("=", 1)[1].strip().strip('"')
    return distro, version


def discover_server(spec: SSHConnectionSpec) -> DiscoveryResult:
    tool = SSHTool(spec)
    try:
        tool.connect()
    except Exception as exc:  # noqa: BLE001
        return DiscoveryResult(reachable=False, error=str(exc))

    raw: dict[str, CommandResult] = {}
    try:
        for key, cmd in DISCOVERY_COMMANDS.items():
            raw[key] = tool.run(cmd, timeout=20)
    finally:
        tool.close()

    os_release_out = raw["os_release"].stdout
    distro, version = _parse_os_release(os_release_out)
    kernel_parts = raw["kernel"].stdout.split()
    arch = kernel_parts[-1] if kernel_parts else ""

    try:
        cpu_cores = int(raw["cpu_count"].stdout.strip() or 0) or None
    except ValueError:
        cpu_cores = None

    try:
        ram_mb = int(int(raw["ram_kb"].stdout.strip() or 0) / 1024) or None
    except ValueError:
        ram_mb = None

    disk_gb = None
    disk_parts = raw["disk_root"].stdout.split()
    if len(disk_parts) >= 1:
        try:
            disk_gb = round(int(disk_parts[0]) / (1024 * 1024), 2)
        except (ValueError, IndexError):
            disk_gb = None

    capabilities = {
        "docker": "not-installed" not in raw["docker"].stdout,
        "python3": "not-installed" not in raw["python"].stdout,
        "node": "not-installed" not in raw["node"].stdout,
        "java": "not-installed" not in raw["java"].stdout,
        "systemd": "present" in raw["systemd"].stdout,
        "docker_version": raw["docker"].stdout.strip(),
        "python_version": raw["python"].stdout.strip(),
        "node_version": raw["node"].stdout.strip(),
    }

    return DiscoveryResult(
        reachable=True,
        os_family="linux",
        os_distribution=distro,
        os_version=version,
        architecture=arch,
        cpu_cores=cpu_cores,
        ram_mb=ram_mb,
        disk_gb=disk_gb,
        hostname=raw["hostname"].stdout.strip(),
        capabilities=capabilities,
        package_manager=raw["package_manager"].stdout.strip() or "unknown",
        raw={k: v.stdout for k, v in raw.items()},
    )
