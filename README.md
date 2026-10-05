# AI Infrastructure Agent

A natural-language **AI Infrastructure / DevOps Control Plane**. You describe what you want
("install nginx on my server", "check disk usage on all production servers", "create an EC2
instance"), and the system understands the request, resolves the target server/cloud
connection, builds a structured execution plan, validates it against an allowlisted catalog,
classifies its risk, asks for approval when required, executes it with the correct tool
(Ansible / SSH / AWS / Docker / Git / Kubernetes), streams live output to the UI,
verifies the result, and records everything in job history.

**Core principle:** *the AI proposes; only validated, catalog-checked actions execute.* The
language model (or the offline rule-based fallback) never emits raw shell commands or cloud
API calls directly — it only ever produces a structured `PlanSpec`, which is validated against
an explicit allowlist (`app/catalog/catalog.py`) before anything is compiled into real Ansible
tasks / boto3 calls.

```
USER PROMPT
  -> CHAT MEMORY / CONTEXT
  -> INTENT + REQUIREMENT ANALYSIS        (app/agent/nlu.py)
  -> TARGET / SERVER / CONNECTION RESOLUTION (app/servers/tag_resolver.py)
  -> ASK USER FOR MISSING INFORMATION
  -> PLAN GENERATION                      (app/agent/orchestrator.py -> PlanSpec)
  -> PLAN VALIDATION                      (app/validation/validator.py)
  -> RISK / POLICY CHECK                  (app/risk/classifier.py)
  -> APPROVAL WHEN REQUIRED               (app/approval/*)
  -> TOOL ROUTER                          (app/tools/router.py)
  -> ANSIBLE / SSH / AWS / DOCKER / GIT / KUBERNETES
  -> LIVE STREAMING                       (WebSocket /ws/jobs/{id})
  -> VERIFICATION                         (app/verification/verifier.py)
  -> RESULT + JOB HISTORY                 (app/jobs/*)
  -> NON-SECRET MEMORY UPDATE             (app/memory/*)
```

---

## 1. What's actually implemented (and what isn't)

This is a real, runnable full-stack application — not a mockup. Every module listed below
contains working code that calls a real library (paramiko, boto3, subprocess to
`ansible-playbook`, SQLAlchemy, APScheduler). Please read this section honestly before
relying on it in production:

| Area | Status |
|---|---|
| Chat-driven agent, intent parsing, target resolution, memory | **Fully implemented.** Rule-based NLU works fully offline; optional Claude-based NLU activates automatically if `ANTHROPIC_API_KEY` is set, with the rule-based parser as a safety-net fallback. |
| PlanSpec → Catalog → Validator → Risk → Approval → Compiler pipeline | **Fully implemented and unit-tested.** |
| SSH execution, file management (SFTP), controlled terminal | **Fully implemented** via paramiko. Terminal is single-command-per-request (not a full interactive PTY) by design, for auditability. |
| Ansible integration | **Fully implemented**, but requires `ansible-playbook` installed on the machine running the backend (control node), **and passwordless sudo (or password-based sudo) for the connecting SSH user** on every target — nearly all real state-changing actions (installing packages, managing services, writing files) automatically run with `become: true`. If either requirement isn't met, the action fails with a clear, honest error instead of a fake success. See §10. |
| AWS integration (EC2, VPC, subnets, security groups, S3, RDS, instance-type/AMI discovery, provisioning) | **Fully implemented** via boto3, tested against `moto` (a real AWS API simulator). Instance types/AMIs/regions are always fetched live — nothing is hard-coded. |
| Kubernetes | **Basic read/apply implemented** via the official `kubernetes` python client. Scope is intentionally small (list pods, apply a manifest) — this is not a full K8s control plane. |
| Docker | Implemented as SSH-executed `docker` CLI commands (list/run/stop/remove). Requires Docker installed on the target host. |
| Live streaming | **Fully implemented** via WebSocket (`/ws/jobs/{id}`) with event replay for reconnecting clients. |
| Approval / risk engine | **Fully implemented**, unit-tested with 39 passing tests covering risk escalation rules. |
| Self-healing / retry | **Fully implemented** but intentionally conservative: only failures matching known retryable patterns (e.g. "apt lock") are retried, up to 2 attempts, and never for destructive actions. |
| Monitoring | **Fully implemented**, pull-based over SSH (no agent required on targets). |
| Cost estimation | **Implemented**, tries the live AWS Pricing API first, falls back to a small reference table, and is always labeled as an estimate — never a guaranteed bill. |
| Rollback | **Implemented honestly and partially**: config file changes are always restorable (backup-before-write); application deployments can redeploy a previous git ref. Cloud resources provisioned directly via AWS (e.g. a terminated EC2 instance) are **not** recoverable once destroyed — the code does not claim otherwise. |
| Automations/scheduling | **Fully implemented** via APScheduler cron triggers, replaying the same validated agent pipeline. |
| Auth / RBAC | **Fully implemented**: JWT auth, three roles (admin/operator/viewer), server-level permission table, audit log. |
| Frontend | **Fully implemented** React + TypeScript + Tailwind, white/minimal, builds cleanly (`npm run build` verified). |

Nothing in the UI links to a feature with no backend behind it.

---

## 2. No artificial limits

There is no `MAX_SERVERS`, no hard-coded EC2 instance-type list, and no cap on how many
servers/jobs/automations can exist. Server counts are bounded only by your database.
AWS instance types, AMIs, VPCs, subnets, and security groups are always discovered live from
the AWS API (`app/tools/aws_tool.py`). The only "allowlists" in the codebase are safety
allowlists — which Ansible modules and AWS *actions* the AI is permitted to propose
(`app/catalog/catalog.py`) — not limits on scale.

---

## 3. Architecture

```
backend/
  app/
    agent/          natural-language understanding + orchestration (the "brain")
    planner/         PlanSpec — the structured, validated representation of an action
    catalog/         allowlist of Ansible modules / AWS actions / generic tool actions
    validation/       rejects anything not in the catalog or missing required params
    risk/            LOW / MEDIUM / HIGH risk classification + blast-radius rules
    approval/        approval request lifecycle
    compiler/        PlanSpec -> Ansible playbook YAML / boto3 calls
    tools/            SSHTool, AnsibleTool, AWSTool, KubernetesTool, router
    execution/        the executor: runs compiled plans, streams events, self-heals
    streaming/        WebSocket pub/sub with event replay
    verification/     post-action checks (service active, port open, HTTP health, path exists)
    diagnostics/       failure classification + human explanation
    self_healing/      controlled, logged, non-destructive auto-retry
    servers/          server registry + tag resolver + SSH-based discovery
    connections/       encrypted credential storage (SSH / AWS / Kubernetes)
    files/             SFTP browse/view/write with backup-before-write + diff/restore
    terminal/          audited single-command execution over WebSocket
    monitoring/        pull-based CPU/RAM/disk/load sampling over SSH
    cost/              AWS cost estimation (clearly labeled as an estimate)
    rollback/          config restore + deployment version rollback
    automations/       APScheduler-backed scheduled prompts
    jobs/              job + job-event persistence (full history)
    chat/              conversations + messages
    memory/            short-term (per-conversation) + long-term (per-user) memory
    auth/              JWT auth, RBAC roles, server-level permissions
    audit/             append-only audit log
    aws/               dynamic AWS discovery REST endpoints
    core/              config, database, security (encryption/hashing/JWT), logging
  tests/               39 tests: unit + integration (real SQLite DB, moto-simulated AWS)
  alembic/             migration scaffold (SQLAlchemy models are the source of truth)
frontend/
  src/
    pages/             Chat, Servers, Connections, Automations, Jobs, Monitoring, Settings
    components/        Sidebar, PlanPreviewCard, ApprovalCard, ServerPicker, LiveExecutionPanel
    lib/                typed API client + WebSocket helper
```

---

## 4. Requirements

- Python 3.11+ (3.12 used in development)
- Node.js 20+ (for the frontend)
- SQLite (bundled with Python — zero extra install; works out of the box on Windows)
- Optional, only if you want the corresponding feature:
  - `ansible-core` / Ansible, with `ansible-playbook` on PATH — for Ansible-based automation
  - AWS credentials — for AWS features
  - `kubernetes` python package (already in requirements.txt) + a kubeconfig — for Kubernetes

## 5. Installation

### Windows (local development)

```powershell
git clone <this repo>
cd ai-infrastructure-agent
.\scripts\setup.ps1
```

This creates a Python virtualenv in `backend\.venv`, installs backend dependencies, copies
`.env.example` to `.env`, and runs `npm install` in `frontend`.

Then, in two terminals:

```powershell
# Terminal 1 — backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open http://localhost:5173. The first account you register becomes an admin automatically.

> Ansible on Windows: `ansible-playbook` does not run natively on Windows. Either run the
> backend inside WSL2, or install Ansible in a WSL2 environment and point
> `ANSIBLE_PLAYBOOK_BINARY` at it, or run the backend in the provided Docker container. SSH,
> AWS, monitoring, files, and terminal features all work fine natively on Windows regardless.

### Linux / macOS

```bash
git clone <this repo>
cd ai-infrastructure-agent
./scripts/setup.sh

# Terminal 1
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2
cd frontend && npm run dev
```

### Docker (backend has Ansible + SSH client preinstalled)

```bash
cp backend/.env.example backend/.env   # edit as needed
docker compose up --build
```

Frontend: http://localhost:5173 · Backend API: http://localhost:8000/api/health

---

## 6. Environment variables

See `backend/.env.example` for the full, commented list. Key ones:

| Variable | Purpose |
|---|---|
| `APP_SECRET_KEY` | JWT signing + credential-encryption fallback. **Change this in production.** |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for encrypting stored SSH/AWS secrets at rest. Generate with the command in `.env.example`. |
| `DATABASE_URL` | Defaults to a local SQLite file; point at Postgres/MySQL for production. |
| `ANTHROPIC_API_KEY` / `GROQ_API_KEY` | Optional. Either enables LLM-assisted intent parsing (Anthropic is tried first if both are set). Works fully without either via the rule-based parser. Groq uses its OpenAI-compatible API directly over HTTPS — no extra SDK needed. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Optional default AWS credentials (per-connection credentials take precedence). Prefer configuring per-connection IAM-based access instead. |
| `ANSIBLE_PLAYBOOK_BINARY` | Path to the ansible-playbook binary if not on PATH. |

---

## 7. Database

SQLite by default (zero setup, a single file under `backend/data/agent.db`). All tables are
created automatically on first startup (`init_db()` in `app/core/database.py`). An Alembic
scaffold is included under `backend/alembic/` for teams that want versioned migrations against
Postgres/MySQL in production — point `DATABASE_URL` at your production database and run
`alembic revision --autogenerate -m "..."` / `alembic upgrade head`.

---

## 8. AWS configuration

1. In the UI: **Connections → Add Connection → AWS**, enter a name, default region, and either
   an access key pair or leave them blank to fall back to the environment/instance role.
2. Prefer IAM roles or short-lived credentials (e.g. an EC2 instance profile, or STS
   `AssumeRole` session tokens) over long-lived static keys where possible — the connection
   model supports an optional session token for exactly this.
3. Test the connection — this calls `sts:get-caller-identity` for real.
4. Ask the agent things like "show available EC2 instance types" or "create an EC2 instance
   for my application" — instance types, AMIs, VPCs, and subnets are discovered live.

Required IAM permissions depend on which features you use; at minimum, read-only EC2/S3/RDS
`Describe*`/`List*` actions for discovery, plus `ec2:RunInstances`/`ec2:TerminateInstances`/etc.
for provisioning actions (all of which route through the approval engine when risky).

## 9. SSH configuration

**Connections → Add Connection → SSH**, then either paste a private key (PEM) or a password.
Credentials are encrypted at rest with Fernet and never returned by any API response. Add a
**Server** and attach the connection; use **Test** to verify connectivity and **Discover** to
pull OS/CPU/RAM/disk/capabilities.

## 10. Ansible setup

Install Ansible on the machine running the backend:

```bash
pip install ansible-core
# or: apt install ansible / brew install ansible
```

No playbooks need to be written by hand — the compiler generates a minimal, single-task
playbook per plan step from the allowlisted module catalog. If `ansible-playbook` isn't found,
Ansible-backed actions fail clearly rather than silently no-opping.

**Sudo / privilege escalation:** every state-changing Ansible action (installing packages,
managing services, writing files/directories, etc.) automatically runs with `become: true`
(sudo), because almost all real infrastructure changes require root and the SSH user is
rarely literally `root`. For this to work, **the SSH user needs passwordless sudo** (or a sudo
password — if your SSH connection uses password auth, that same password is also used as the
sudo password automatically; key-based auth requires `NOPASSWD` sudo configured on the target).
The **file management** feature (SFTP browse/view/write) has the same requirement: a direct
SFTP operation is tried first, and if that hits Permission denied (e.g. writing under `/opt`
or `/etc`), it automatically falls back to a sudo-based read/write/list, so admin-owned paths
work the same way they do for Ansible actions.

Example one-time setup on a target Ubuntu server (as an existing admin):
```bash
sudo usermod -aG sudo deployuser
echo "deployuser ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/deployuser
```

## 11. Testing

```bash
cd backend
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows
pytest -q
```

39 tests, all passing, covering: registration/RBAC, unlimited server creation, tag-based
server resolution, PlanSpec validation (rejects unknown actions / missing params / empty
targets), risk classification (low/medium/high, destructive-state escalation, blast-radius
escalation), the compiler (Ansible YAML / AWS calls / Docker commands), rule-based NLU parsing
against the exact example prompts from the product spec, end-to-end orchestrator behavior
("offer to add a server" / "ask for missing package" / low-risk auto-run / high-risk requires
approval), dynamic AWS discovery against a real simulated AWS API (`moto`) proving instance
types/VPCs/subnets are fetched live rather than hard-coded, credential encryption round-trips,
password hashing, secret redaction in logs, and the memory system's refusal to store
secret-shaped values.

Frontend:

```bash
cd frontend
npm run build   # type-checks with tsc and produces a production build
```

---

## 12. Development

- Backend: FastAPI + SQLAlchemy 2.0 + Pydantic v2. Run with `--reload` for hot reload.
- Frontend: Vite + React + TypeScript + Tailwind. `npm run dev` proxies `/api` and `/ws` to
  `localhost:8000` (see `frontend/vite.config.ts`).
- Structured JSON logs (`app/core/logging_config.py`) carry `request_id`/`job_id`/`server_id`/
  `tool`/`task`/`status` and defensively redact common secret patterns.

## 13. Production deployment notes

- Set a strong, unique `APP_SECRET_KEY` and `CREDENTIAL_ENCRYPTION_KEY`.
- Point `DATABASE_URL` at Postgres/MySQL and use Alembic migrations instead of `init_db()`'s
  `create_all`.
- Run the backend behind TLS; the WebSocket endpoints (`/ws/...`) should be proxied as `wss://`.
- Restrict `CORS_ORIGINS` to your real frontend origin.
- Consider replacing paramiko's `AutoAddPolicy` host-key handling with a pinned known_hosts
  policy for production SSH targets.
- Review `app/catalog/catalog.py` and tighten the allowlist / risk levels to match your org's
  policy before exposing this to a broad user base.

## 14. Security notes

- Passwords are hashed with bcrypt; JWTs sign session tokens; all credentials (SSH keys/
  passwords, AWS keys, kubeconfigs) are encrypted at rest with Fernet and are never returned by
  any API response or written to logs (defensive regex redaction is applied to all log output
  as a second layer).
- The chat/agent memory system actively refuses to persist any value that looks like a secret
  (password/key/token patterns).
- Every mutating action passes through catalog validation and risk classification; HIGH-risk
  and large-blast-radius actions require explicit human approval before the Tool Router is ever
  invoked.
- All server/connection/job/approval/automation mutations are recorded in an append-only audit
  log (`app/audit/`), viewable by admins under Settings.
- RBAC: `viewer` (read-only), `operator` (can run/approve most things), `admin` (full control,
  including connection management and audit log access).
- The terminal endpoint blocks a small set of catastrophically destructive command patterns
  outright (e.g. `rm -rf /`, fork bombs) in addition to normal auth/audit/timeout controls.

## 15. API documentation

Interactive OpenAPI docs are auto-generated by FastAPI at **http://localhost:8000/docs** once
the backend is running. Key endpoints:

```
POST   /api/auth/register            POST /api/auth/login          GET /api/auth/me
POST   /api/chat                     GET  /api/chat/conversations  GET /api/chat/conversations/{id}/messages
GET    /api/servers                  POST /api/servers              GET/PATCH/DELETE /api/servers/{id}
POST   /api/servers/{id}/test        POST /api/servers/{id}/discover
GET    /api/connections              POST /api/connections          POST /api/connections/{id}/test
GET    /api/jobs                     GET  /api/jobs/{id}            GET /api/jobs/{id}/events
GET    /api/approvals                POST /api/approvals/{id}/approve | /reject
GET    /api/memory                   DELETE /api/memory/{id}
GET    /api/audit
GET    /api/aws/regions|instance-types|amis|vpcs|subnets|security-groups|instances|s3-buckets|rds-instances
GET    /api/cost/ec2
GET/POST /api/automations            POST /api/automations/{id}/toggle
GET    /api/servers/{id}/files       GET  /api/servers/{id}/files/view   POST /api/servers/{id}/files/write
GET    /api/servers/{id}/files/backups   POST .../backups/{id}/restore
WS     /ws/jobs/{job_id}             WS   /api/servers/{id}/terminal/ws
```

## 16. Example prompts

```
Install nginx on my Ubuntu server.
Create /opt/myapp and deploy my application.
Install Docker on all production servers.
Check which servers have nginx running.
Restart nginx on web-server-02.
Check disk usage on all production servers.
Install Python 3.12 on all Ubuntu servers.
Show all my servers.
Show available EC2 instance types.
Create an EC2 instance for my application.
```
