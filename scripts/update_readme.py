#!/usr/bin/env python3
"""Rewrite the 'Currently working on' block of README.md with recently pushed public repos.

Standard library only. Configure with environment variables:
  GH_USER      GitHub username (default: the profile repo owner, or back2sqr1)
  GITHUB_TOKEN token for the API (set automatically in GitHub Actions)
  RECENT_COUNT number of repositories to list (default 3)
  EXCLUDE      comma-separated repository names to skip
  REPOS_JSON   path to a saved API response (for offline testing)
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone

USER = os.environ.get("GH_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "back2sqr1"
COUNT = int(os.environ.get("RECENT_COUNT", "3"))
EXCLUDE = {n.strip().lower() for n in os.environ.get("EXCLUDE", "").split(",") if n.strip()}
EXCLUDE.add(USER.lower())  # never list the profile repo itself
START, END = "<!-- RECENT:START -->", "<!-- RECENT:END -->"


def fetch_repos():
    if os.environ.get("REPOS_JSON"):
        with open(os.environ["REPOS_JSON"]) as f:
            return json.load(f)
    url = f"https://api.github.com/users/{USER}/repos?type=owner&sort=pushed&per_page=100"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-readme"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def ago(iso):
    days = (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return f"{months} month{'s' if months > 1 else ''} ago"


def render(repos):
    keep = [r for r in repos
            if not r.get("fork") and not r.get("archived") and not r.get("private")
            and r["name"].lower() not in EXCLUDE]
    keep.sort(key=lambda r: r["pushed_at"], reverse=True)
    lines = []
    for r in keep[:COUNT]:
        desc = (r.get("description") or "").strip()
        lang = r.get("language")
        meta = " · ".join(x for x in (lang, f"updated {ago(r['pushed_at'])}") if x)
        line = f"- **[{r['name']}]({r['html_url']})**"
        if desc:
            line += f": {desc}"
        lines.append(f"{line} _({meta})_")
    if not lines:
        lines = ["_Nothing public yet. Check back soon._"]
    return "\n".join(lines)


def main():
    path = "README.md"
    text = open(path, encoding="utf-8").read()
    if START not in text or END not in text:
        sys.exit(f"README.md must contain {START} and {END}")
    block = f"{START}\n{render(fetch_repos())}\n{END}"
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    if new != text:
        open(path, "w", encoding="utf-8").write(new)
        print("README.md updated")
    else:
        print("README.md unchanged")


if __name__ == "__main__":
    main()
