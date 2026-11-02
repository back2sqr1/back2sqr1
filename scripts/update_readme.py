#!/usr/bin/env python3
"""Update README.md with recently pushed repositories.

Includes personal and organization repositories accessible to the
authenticated GitHub user.

Environment variables:
  GH_USER       GitHub username (informational)
  GITHUB_TOKEN  GitHub API token
  RECENT_COUNT  Number of repositories to list (default 3)
  EXCLUDE       Comma-separated repository names to skip
  REPOS_JSON    Path to saved repository API response for offline testing
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

COUNT = int(os.environ.get("RECENT_COUNT", "3"))

EXCLUDE = {
    n.strip().lower()
    for n in os.environ.get("EXCLUDE", "").split(",")
    if n.strip()
}

START = "<!-- RECENT:START -->"
END = "<!-- RECENT:END -->"

API = "https://api.github.com"


def api_get(endpoint):
    """Fetch GitHub API endpoint."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-readme",
    }

    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{API}{endpoint}"

    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def fetch_repos():
    """Fetch personal and organization repositories."""

    if os.environ.get("REPOS_JSON"):
        with open(os.environ["REPOS_JSON"], encoding="utf-8") as f:
            return json.load(f)

    repos = {}

    # Personal repositories, including private ones when authorized.
    page = 1

    while True:
        results = api_get(
            f"/user/repos?affiliation=owner,collaborator,organization_member"
            f"&sort=pushed&direction=desc&per_page=100&page={page}"
        )

        if not results:
            break

        for repo in results:
            repos[repo["full_name"].lower()] = repo

        page += 1

    # Organizations the authenticated user belongs to.
    organizations = api_get("/user/orgs?per_page=100")

    for org in organizations:
        org_name = org["login"]
        page = 1

        while True:
            results = api_get(
                f"/orgs/{org_name}/repos?"
                f"type=all&sort=pushed&direction=desc"
                f"&per_page=100&page={page}"
            )

            if not results:
                break

            for repo in results:
                repos[repo["full_name"].lower()] = repo

            page += 1

    return list(repos.values())


def ago(iso):
    days = (
        datetime.now(timezone.utc)
        - datetime.fromisoformat(iso.replace("Z", "+00:00"))
    ).days

    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"

    months = days // 30
    return f"{months} month{'s' if months > 1 else ''} ago"


def render(repos):
    keep = [
        r for r in repos
        if not r.get("fork")
        and not r.get("archived")
        and r["name"].lower() not in EXCLUDE
    ]

    keep.sort(
        key=lambda r: r.get("pushed_at") or "",
        reverse=True
    )

    lines = []

    for r in keep[:COUNT]:
        desc = (r.get("description") or "").strip()
        lang = r.get("language")

        meta = " · ".join(
            x for x in (
                lang,
                f"updated {ago(r['pushed_at'])}"
                if r.get("pushed_at") else None
            )
            if x
        )

        line = f"- **[{r['name']}]({r['html_url']})**"

        if desc:
            line += f": {desc}"

        if meta:
            line += f" _({meta})_"

        lines.append(line)

    if not lines:
        lines = ["_Nothing public yet. Check back soon._"]

    return "\n".join(lines)


def main():
    path = "README.md"

    with open(path, encoding="utf-8") as f:
        text = f.read()

    if START not in text or END not in text:
        sys.exit(
            f"README.md must contain {START} and {END}"
        )

    block = f"{START}\n{render(fetch_repos())}\n{END}"

    new = re.sub(
        re.escape(START) + r".*?" + re.escape(END),
        lambda _: block,
        text,
        flags=re.S
    )

    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)

        print("README.md updated")
    else:
        print("README.md unchanged")


if __name__ == "__main__":
    main()
