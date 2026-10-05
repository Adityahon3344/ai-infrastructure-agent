"""Resolves natural-language target descriptions ("all production web servers")
into concrete Server rows using tag/environment matching. No hard-coded server
count limits anywhere in this path."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.servers.models import Server


def resolve_servers(
    db: Session,
    *,
    server_names: list[str] | None = None,
    environment: str | None = None,
    tags: dict[str, str] | None = None,
) -> list[Server]:
    query = db.query(Server)
    if server_names:
        lowered = [n.lower() for n in server_names]
        candidates = query.all()
        matched = [s for s in candidates if s.name.lower() in lowered or s.hostname.lower() in lowered]
        return matched

    if environment:
        query = query.filter(Server.environment == environment)

    results = query.all()
    if tags:
        def matches(server: Server) -> bool:
            server_tags = server.tags or {}
            return all(server_tags.get(k) == v for k, v in tags.items())

        results = [s for s in results if matches(s)]

    return results


def parse_target_phrase(phrase: str) -> dict:
    """Small deterministic parser for phrases like:
    'all production web servers' -> {environment: production, tags: {role: web}}
    'web-server-02' -> {server_names: ['web-server-02']}

    IMPORTANT: a single-token phrase (no spaces, not starting with "all") is
    treated as a literal server name/alias FIRST, unless it exactly equals a
    known environment/role keyword. This avoids a substring-matching trap
    where a real hostname like 'real-web-01' or 'web-server-02' would
    otherwise be misread as the role tag 'web' (because "web" appears inside
    the name) and silently fail to resolve to the actual server. Descriptive
    multi-word phrases ("all production web servers") still use substring
    keyword matching, which is what we want there.
    """
    phrase_l = phrase.lower().strip()
    result: dict = {"server_names": None, "environment": None, "tags": {}}

    known_envs = ["production", "prod", "staging", "stage", "dev", "development", "test"]
    env_map = {"prod": "production", "stage": "staging", "dev": "development"}
    known_roles = ["web", "database", "db", "worker", "cache", "app", "backend", "frontend", "load balancer", "lb"]
    role_map = {"db": "database", "lb": "load balancer"}

    is_descriptive = len(phrase_l.split()) > 1 or phrase_l.startswith("all")

    if not is_descriptive:
        if phrase_l in known_envs:
            result["environment"] = env_map.get(phrase_l, phrase_l)
            return result
        if phrase_l in known_roles:
            result["tags"]["role"] = role_map.get(phrase_l, phrase_l)
            return result
        # Single token that isn't an exact env/role keyword -> treat as a
        # literal server name/alias, e.g. "web-server-02", "real-web-01".
        result["server_names"] = [phrase.strip()]
        return result

    for env in known_envs:
        if env in phrase_l:
            result["environment"] = env_map.get(env, env)
            break

    for role in known_roles:
        if role in phrase_l:
            result["tags"]["role"] = role_map.get(role, role)
            break

    if not result["environment"] and not result["tags"]:
        result["server_names"] = [phrase.strip()]

    return result
