"""Entity resolution — correlate identifiers across plugin results.

Each plugin returns its own differently-shaped data. This layer walks all of
them generically and pulls out the identity signals — emails, usernames, real
names, phone numbers, profile URLs, domains — deduped and tagged with which
plugins reported each one. Because a run is about a single target, every
identifier found is an implicit link to that target; the ``sources`` list is the
provenance, and agreement across plugins raises confidence.

The result is attached to the report (and fed to the LLM) so cross-referencing
starts from correlated identifiers instead of raw per-plugin blobs.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Set
from urllib.parse import urlparse

from aseye.models import Report

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")

_USERNAME_KEYS = {"username", "login", "handle", "preferred_username", "screen_name"}
# Deliberately excludes bare "name" — it's used for breach names, site names,
# etc. across plugins and produces false positives. Use full_name/display_name.
_NAME_KEYS = {"full_name", "display_name", "real_name"}
_PHONE_KEYS = {"phone", "public_phone", "phone_number", "obfuscated_phone", "public_phone_number"}
_URL_KEYS = {"url", "profile_url", "html_url", "uri", "link", "value"}

# Store = identifier value -> set of plugin names that reported it.
Store = Dict[str, Set[str]]


def _walk(obj: Any, key: str, sink: Callable[[str, Any], None]) -> None:
    """Depth-first walk yielding (parent_key, scalar) for every leaf value."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, k, sink)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _walk(item, key, sink)
    else:
        sink(key, obj)


def _host(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return netloc[4:] if netloc.startswith("www.") else netloc


def _confidence(sources: Set[str]) -> str:
    real = sources - {"target"}
    if len(real) >= 2:
        return "high"
    if real:
        return "medium"
    return "low"


def _format(store: Store) -> List[Dict[str, Any]]:
    items = []
    for value, sources in store.items():
        items.append({"value": value, "sources": sorted(sources), "confidence": _confidence(sources)})
    # Most-corroborated first, then alphabetical.
    items.sort(key=lambda it: (-len(it["sources"]), it["value"].lower()))
    return items


def resolve_identities(report: Report) -> Dict[str, Any]:
    """Correlate identifiers across the report's plugin results."""
    emails: Store = defaultdict(set)
    usernames: Store = defaultdict(set)
    names: Store = defaultdict(set)
    phones: Store = defaultdict(set)
    profiles: Store = defaultdict(set)

    def add(store: Store, value: Any, source: str) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            store[text].add(source)

    # Seed with the target itself.
    if report.target.kind == "email":
        add(emails, report.target.value.lower(), "target")
    elif report.target.kind == "username":
        add(usernames, report.target.value, "target")

    for result in report.results:
        source = result.plugin

        def sink(key: str, value: Any) -> None:
            if not isinstance(value, str):
                return
            k = (key or "").lower()
            for match in _EMAIL_RE.findall(value):
                add(emails, match.lower(), source)
            for url in _URL_RE.findall(value):
                add(profiles, url, source)
            if k in _USERNAME_KEYS:
                add(usernames, value, source)
            elif k in _NAME_KEYS:
                add(names, value, source)
            elif k in _PHONE_KEYS:
                add(phones, value, source)
            elif "email" in k and "@" not in value:
                add(emails, value, source)  # obfuscated emails (e.g. "h***@g***")

        _walk(result.data, "", sink)

    # Domains derived from emails and profile URLs.
    domains: Store = defaultdict(set)
    for email, srcs in emails.items():
        if "@" in email:
            domains[email.rsplit("@", 1)[-1]].update(srcs)
    for url, srcs in profiles.items():
        host = _host(url)
        if host:
            domains[host].update(srcs)

    return {
        "emails": _format(emails),
        "usernames": _format(usernames),
        "names": _format(names),
        "phones": _format(phones),
        "profiles": _format(profiles),
        "domains": _format(domains),
    }
