"""GitHub integration (username <-> email).

Uses the public GitHub REST API to bridge usernames and emails:

- **username** -> public profile, plus emails harvested from public push events
  (and, in deep mode, from recent repositories' commits).
- **email** -> usernames, via commit-author search and public-email user search.

Works with no key (60 requests/hour). For 5000/hour, set a token via the
``GITHUB_TOKEN`` environment variable or ``plugins.settings.github.token``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

_API = "https://api.github.com"
_UA = "all-seeing-eye-osint-tool"
_NOREPLY = "users.noreply.github.com"


class GithubPlugin(BasePlugin):
    name = "github"
    version = "1.0.0"
    description = "Link GitHub usernames and emails via the public API."
    author = "all-seeing-eye"
    supported_targets = {"username", "email"}
    # Optional token (higher rate limit) — the plugin works without one.
    requires_key_env = None
    requires_key_setting = None

    default_settings = {
        "token": "",         # falls back to $GITHUB_TOKEN
        "timeout": 20,
        "rate_limit": 1.0,   # seconds between GitHub requests
        "scan_repos": 0,     # NORMAL: don't scan repo commits
        "max_commits": 30,
    }
    deep_settings = {"scan_repos": 5}

    def run(self, target: Target, mode: RunMode, settings: Dict[str, Any]) -> Dict[str, Any]:
        token = os.environ.get("GITHUB_TOKEN") or settings.get("token") or ""
        timeout = float(settings.get("timeout", 20))
        self._rate_limit = float(settings.get("rate_limit", 1.0))

        headers = {"Accept": "application/vnd.github+json", "User-Agent": _UA}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
            if target.kind == "email":
                return self._by_email(client, target.value)
            return self._by_username(client, target.value, settings)

    # ---- username -> profile + emails ----------------------------------------

    def _by_username(self, client, username: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {"username": username, "kind": "username", "found": False}
        profile = self._get(client, f"/users/{quote(username, safe='')}")
        if profile is None:
            return result

        result["found"] = True
        result["profile"] = {
            "full_name": profile.get("name"),
            "company": profile.get("company"),
            "blog": profile.get("blog") or None,
            "location": profile.get("location"),
            "bio": profile.get("bio"),
            "twitter": profile.get("twitter_username"),
            "public_email": profile.get("email"),
            "public_repos": profile.get("public_repos"),
            "followers": profile.get("followers"),
            "created_at": profile.get("created_at"),
            "html_url": profile.get("html_url"),
        }

        emails: Dict[str, str] = {}
        if profile.get("email"):
            emails[profile["email"]] = "profile"
        for commit_email in self._emails_from_events(client, username):
            emails.setdefault(commit_email, "push_event")
        scan_repos = int(settings.get("scan_repos", 0))
        if scan_repos:
            for commit_email in self._emails_from_repos(
                client, username, scan_repos, int(settings.get("max_commits", 30))
            ):
                emails.setdefault(commit_email, "repo_commit")

        result["emails"] = [
            {"email": e, "source": src, "noreply": _NOREPLY in e} for e, src in emails.items()
        ]
        return result

    def _emails_from_events(self, client, username: str) -> List[str]:
        events = self._get(client, f"/users/{quote(username, safe='')}/events/public",
                           params={"per_page": 100}) or []
        found = []
        for event in events:
            if event.get("type") != "PushEvent":
                continue
            for commit in (event.get("payload") or {}).get("commits") or []:
                email = (commit.get("author") or {}).get("email")
                if email:
                    found.append(email)
        return found

    def _emails_from_repos(self, client, username: str, max_repos: int, max_commits: int) -> List[str]:
        repos = self._get(client, f"/users/{quote(username, safe='')}/repos",
                          params={"per_page": max_repos, "sort": "pushed", "type": "owner"}) or []
        found = []
        for repo in repos[:max_repos]:
            full = repo.get("full_name")
            if not full:
                continue
            commits = self._get(client, f"/repos/{full}/commits",
                                params={"author": username, "per_page": max_commits}) or []
            for commit in commits:
                email = ((commit.get("commit") or {}).get("author") or {}).get("email")
                if email:
                    found.append(email)
        return found

    # ---- email -> usernames --------------------------------------------------

    def _by_email(self, client, email: str) -> Dict[str, Any]:
        linked: Dict[str, Dict[str, Any]] = {}

        commits = self._get(client, "/search/commits",
                            params={"q": f"author-email:{email}", "per_page": 30})
        for item in (commits or {}).get("items", []) if isinstance(commits, dict) else []:
            login = (item.get("author") or {}).get("login")
            if login:
                entry = linked.setdefault(login, {"login": login, "via": "commit", "repos": []})
                repo = (item.get("repository") or {}).get("full_name")
                if repo and repo not in entry["repos"]:
                    entry["repos"].append(repo)

        users = self._get(client, "/search/users", params={"q": f"{email} in:email"})
        for item in (users or {}).get("items", []) if isinstance(users, dict) else []:
            login = item.get("login")
            if login:
                linked.setdefault(login, {"login": login, "via": "public_email", "repos": []})

        return {
            "email": email,
            "kind": "email",
            "linked_usernames": list(linked.values()),
            "found": bool(linked),
        }

    # ---- HTTP ----------------------------------------------------------------

    def _get(self, client, path: str, params: Optional[Dict[str, Any]] = None):
        """GET a GitHub endpoint. Returns parsed JSON, or None for 404."""
        self.throttle("github", getattr(self, "_rate_limit", 1.0))
        try:
            resp = client.get(f"{_API}{path}", params=params)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"GitHub request failed: {exc}") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            raise RuntimeError(
                "GitHub rate limit reached. Set a token via GITHUB_TOKEN (or "
                "plugins.settings.github.token) for a higher limit."
            )
        if resp.status_code == 401:
            raise RuntimeError("GitHub rejected the token (401). Check GITHUB_TOKEN.")
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub returned unexpected status {resp.status_code}.")
        return resp.json()
