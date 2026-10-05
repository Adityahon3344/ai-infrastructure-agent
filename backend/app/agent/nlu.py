"""
Natural-language understanding. Two layers:

1. Deterministic rule-based parser (`parse_intent_rule_based`) — always
   available, fully offline, and used as-is when ANTHROPIC_API_KEY is unset.
   It recognizes the example command shapes from the product spec directly.

2. LLM-assisted parser (`parse_intent_llm`) — when an API key is configured,
   asks Claude to extract the same structured IntentResult JSON. The LLM is
   ONLY ever used to produce this structured intent (never raw shell/boto3
   code), and its output still goes through the full PlanSpec -> Catalog ->
   Validator pipeline afterward — the LLM's output is never trusted directly.

Both paths return the same `IntentResult` shape so the orchestrator does not
care which one produced it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("agent.nlu")


@dataclass
class IntentResult:
    intent: str                       # install_package | manage_service | create_path | inspect | provision_ec2 | list_aws_resource | deploy | unknown
    package_name: str | None = None
    service_name: str | None = None
    service_action: str | None = None  # start|stop|restart|enable
    path: str | None = None
    target_phrase: str | None = None   # raw phrase describing target servers, e.g. "all production web servers"
    aws_resource: str | None = None    # ec2 | vpc | s3 | ...
    inspect_kind: str | None = None    # cpu | ram | disk | services | facts
    repo_url: str | None = None
    raw_text: str = ""
    confidence: float = 0.6
    missing_info: list[str] = field(default_factory=list)


_PACKAGE_ALIASES = {
    "nginx": "nginx", "docker": "docker", "apache": "apache2", "apache2": "apache2",
    "python": "python3", "python3": "python3", "git": "git", "mysql": "mysql-server",
    "postgres": "postgresql", "postgresql": "postgresql", "node": "nodejs", "nodejs": "nodejs",
    "redis": "redis-server", "java": "default-jdk",
}


def _extract_package(text: str) -> str | None:
    for alias, real in _PACKAGE_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            version_match = re.search(rf"\b{re.escape(alias)}\s*(\d+(\.\d+)*)", text)
            if version_match and alias == "python":
                return f"python{version_match.group(1)}"
            return real
    return None


def _extract_service_action(text: str) -> str | None:
    if re.search(r"\brestart\b", text):
        return "restarted"
    if re.search(r"\bstop\b", text):
        return "stopped"
    if re.search(r"\b(start|run)\b", text):
        return "started"
    if re.search(r"\benable\b", text):
        return "started"  # combined with enabled=True upstream
    return None


def _extract_path(text: str) -> str | None:
    match = re.search(r"(/[\w\-./]+)", text)
    if match:
        return match.group(1)
    match = re.search(r"(?:folder|directory)\s+(?:called\s+)?([\w\-]+)", text)
    if match:
        return f"/opt/{match.group(1)}"
    return None


def _extract_target_phrase(text: str) -> str | None:
    match = re.search(r"on\s+(all\s+[\w\- ]+servers?|[\w\-]+)", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"\bserver\s+([\w\-\.]+)", text)
    if match:
        return match.group(1).strip()
    return None


def parse_intent_rule_based(text: str) -> IntentResult:
    t = text.lower().strip()
    target_phrase = _extract_target_phrase(t)

    if re.search(r"\bcreate\s+(an?\s+)?ec2\b", t) or re.search(r"\bprovision\b.*\binstance\b", t) or re.search(r"\blaunch\b.*\binstance\b", t):
        return IntentResult(intent="provision_ec2", raw_text=text, confidence=0.75)

    if re.search(r"\bshow\b.*\b(instance types|ec2 types)\b", t) or re.search(r"\bavailable\b.*\binstance types\b", t):
        return IntentResult(intent="list_aws_resource", aws_resource="instance_types", raw_text=text, confidence=0.8)

    if re.search(r"\bcreate\b.*\bvpc\b", t):
        return IntentResult(intent="provision_vpc", raw_text=text, confidence=0.75)

    if re.search(r"\bshow\b.*\bservers?\b", t) or re.search(r"\blist\b.*\bservers?\b", t):
        return IntentResult(intent="list_servers", raw_text=text, confidence=0.85)

    if re.search(r"\bdeploy\b", t):
        path = _extract_path(t)
        return IntentResult(intent="deploy", path=path, target_phrase=target_phrase, raw_text=text, confidence=0.6,
                             missing_info=[] if target_phrase else ["target_server"])

    if re.search(r"\bcheck\b.*\b(disk|storage)\b", t) or re.search(r"\bdisk usage\b", t):
        return IntentResult(intent="inspect", inspect_kind="disk", target_phrase=target_phrase, raw_text=text, confidence=0.85)

    if re.search(r"\bcpu\b", t) and re.search(r"\b(check|usage|show)\b", t):
        return IntentResult(intent="inspect", inspect_kind="cpu", target_phrase=target_phrase, raw_text=text, confidence=0.85)

    if re.search(r"\bwhich servers\b.*\brunning\b", t) or (re.search(r"\bcheck\b", t) and re.search(r"\brunning\b", t)):
        service_match = re.search(r"\b(\w+)\s+(?:is\s+)?running\b", t)
        return IntentResult(intent="inspect", inspect_kind="service_status",
                             service_name=service_match.group(1) if service_match else None,
                             target_phrase=target_phrase, raw_text=text, confidence=0.7)

    if re.search(r"\brestart\b", t) or re.search(r"\bstop\b", t) or (re.search(r"\b(start|enable)\b", t) and not re.search(r"install", t)):
        service = None
        for alias in _PACKAGE_ALIASES.values():
            if alias.split("-")[0] in t:
                service = alias if alias != "mysql-server" else "mysql"
                break
        return IntentResult(intent="manage_service", service_name=service, service_action=_extract_service_action(t),
                             target_phrase=target_phrase, raw_text=text, confidence=0.65 if service else 0.4,
                             missing_info=[] if service else ["service_name"])

    if re.search(r"\bcreate\b.*\b(folder|directory)\b", t) or re.search(r"\bmkdir\b", t):
        path = _extract_path(t)
        return IntentResult(intent="create_path", path=path, target_phrase=target_phrase, raw_text=text, confidence=0.75,
                             missing_info=[] if path else ["path"])

    if re.search(r"\bcreate\b", t) and _extract_path(t) and not re.search(r"\b(ec2|instance|vpc|security group)\b", t):
        # "create /opt/myapp on web-01" — a bare path after "create" with no
        # "folder"/"directory" wording, exactly like the spec's own example
        # ("Create /opt/myapp and deploy my application.") before the word
        # "deploy" is checked. Handled here as a plain directory-creation intent.
        path = _extract_path(t)
        return IntentResult(intent="create_path", path=path, target_phrase=target_phrase, raw_text=text, confidence=0.7)

    if re.search(r"\binstall\b", t):
        pkg = _extract_package(t)
        return IntentResult(intent="install_package", package_name=pkg, target_phrase=target_phrase, raw_text=text,
                             confidence=0.8 if pkg else 0.3, missing_info=[] if pkg else ["package_name"])

    return IntentResult(intent="unknown", target_phrase=target_phrase, raw_text=text, confidence=0.1,
                         missing_info=["intent"])


_LLM_SYSTEM_PROMPT = """You convert a natural-language infrastructure request into a strict JSON object with this shape:
{"intent": "install_package|manage_service|create_path|inspect|provision_ec2|provision_vpc|list_aws_resource|list_servers|deploy|unknown",
 "package_name": string|null, "service_name": string|null, "service_action": "started|stopped|restarted"|null,
 "path": string|null, "target_phrase": string|null, "aws_resource": string|null, "inspect_kind": "cpu|ram|disk|service_status|facts"|null,
 "repo_url": string|null, "confidence": number, "missing_info": string[]}
Only output the JSON object, nothing else. Never output shell commands, code, or API calls — only this structured intent."""


def parse_intent_llm(text: str) -> IntentResult | None:
    if settings.anthropic_api_key:
        result = _parse_intent_anthropic(text)
        if result is not None:
            return result
    if settings.groq_api_key:
        result = _parse_intent_groq(text)
        if result is not None:
            return result
    return None


def _parse_intent_anthropic(text: str) -> IntentResult | None:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            system=_LLM_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        data = json.loads(raw)
        return IntentResult(raw_text=text, **{k: v for k, v in data.items() if k in IntentResult.__dataclass_fields__})
    except Exception:  # noqa: BLE001
        logger.exception("Anthropic intent parsing failed, trying next backend")
        return None


def _parse_intent_groq(text: str) -> IntentResult | None:
    """Groq exposes an OpenAI-compatible chat completions API. We call it
    directly over HTTPS (no extra SDK dependency needed) and request strict
    JSON output via response_format. Like the Anthropic path, this ONLY ever
    produces a structured IntentResult — never shell/API code — and its
    output still goes through the full PlanSpec -> Catalog -> Validator
    pipeline afterward."""
    try:
        import httpx

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.groq_model,
                "messages": [
                    {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 500,
            },
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(raw)
        return IntentResult(raw_text=text, **{k: v for k, v in data.items() if k in IntentResult.__dataclass_fields__})
    except Exception:  # noqa: BLE001
        logger.exception("Groq intent parsing failed, falling back to rule-based parser")
        return None


def parse_intent(text: str) -> IntentResult:
    llm_result = parse_intent_llm(text)
    if llm_result is not None and llm_result.intent != "unknown":
        return llm_result
    return parse_intent_rule_based(text)
