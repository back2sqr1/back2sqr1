#!/usr/bin/env python3
"""Update README.md with recently pushed GitHub repositories.

Fetches repositories accessible to the authenticated user,
including personal and organization repositories.

Environment variables:
  GITHUB_TOKEN     GitHub personal access token
  GH_USER          GitHub username (optional)
  RECENT_COUNT     Number of repositories to display (default 3)
  EXCLUDE          Comma-separated repository names to skip
  INCLUDE_PRIVATE  Include private repos (default false)
  INCLUDE_FORKS    Include forks (default false)
  INCLUDE_ARCHIVED Include archived repos (default false)
  REPOS_JSON       Offline JSON file for testing
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from datetime import datetime, timezone

API = "https://api.github.com"

COUNT = int(os.environ.get("RECENT_COUNT", "3"))

INCLUDE_PRIVATE = os.environ.get("INCLUDE_PRIVATE", "false").lower() == "true"

INCLUDE_FORKS = os.environ.get("INCLUDE_FORKS", "false").lower() == "true"

INCLUDE_ARCHIVED = os.environ.get("INCLUDE_ARCHIVED", "false").lower() == "true"

EXCLUDE = {
    name.strip().lower()
    for name in os.environ.get("EXCLUDE", "").split(",")
    if name.strip()
}

START = "<!-- RECENT:START -->"
END = "<!-- RECENT:END -->"


def api_get(endpoint):
    """Fetch GitHub API endpoint with useful error reporting."""

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")

    if not token:
        raise RuntimeError("Missing GitHub token. Configure GITHUB_TOKEN or GH_PAT.")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    req = urllib.request.Request(f"{API}{endpoint}", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        print(f"\nGitHub API returned HTTP {error.code}", file=sys.stderr)

        print(f"Endpoint: {endpoint}", file=sys.stderr)
        print(f"Response: {body}", file=sys.stderr)

        if error.code == 403:
            print(
                "\nCheck token permissions, organization access, "
                "SSO authorization, and API rate limits.",
                file=sys.stderr,
            )

            print(
                "Rate limit remaining:",
                error.headers.get("X-RateLimit-Remaining"),
                file=sys.stderr,
            )

        raise


def fetch_repos():
    """Fetch all repositories accessible to the authenticated user."""

    # Offline testing
    if os.environ.get("REPOS_JSON"):
        with open(os.environ["REPOS_JSON"], encoding="utf-8") as file:
            return json.load(file)

    # Identify authenticated user
    user = api_get("/user")

    username = (os.environ.get("GH_USER") or user["login"]).lower()

    print(f"Fetching repositories for {username}...")

    repos = {}
    page = 1

    # Fetch personal and organization repositories.
    # This endpoint includes repositories where the user is:
    # owner, collaborator, or organization member.
    while True:
        params = urllib.parse.urlencode(
            {
                "visibility": "all",
                "affiliation": ("owner,collaborator,organization_member"),
                "sort": "pushed",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            }
        )

        results = api_get(f"/user/repos?{params}")

        if not results:
            break

        for repo in results:
            repos[repo["full_name"].lower()] = repo

        print(f"Fetched page {page}: {len(results)} repositories")

        if len(results) < 100:
            break

        page += 1

    print(f"Total repositories found: {len(repos)}")

    # Exclude the profile repository itself.
    profile_repo = f"{username}/{username}"

    repos.pop(profile_repo, None)

    return list(repos.values())


def ago(iso):
    """Convert ISO timestamp into a human-readable age."""

    if not iso:
        return "unknown"

    timestamp = datetime.fromisoformat(iso.replace("Z", "+00:00"))

    days = (datetime.now(timezone.utc) - timestamp).days

    if days <= 0:
        return "today"

    if days == 1:
        return "yesterday"

    if days < 30:
        return f"{days} days ago"

    months = days // 30

    return f"{months} month{'s' if months != 1 else ''} ago"


def render(repos):
    """Filter, sort, and format repositories."""

    keep = []

    for repo in repos:
        name = repo["name"].lower()
        full_name = repo.get("full_name", name).lower()

        # Exclusions
        if name in EXCLUDE or full_name in EXCLUDE:
            continue

        if repo.get("private") and not INCLUDE_PRIVATE:
            continue

        if repo.get("fork") and not INCLUDE_FORKS:
            continue

        if repo.get("archived") and not INCLUDE_ARCHIVED:
            continue

        keep.append(repo)

    # Most recently pushed first
    keep.sort(key=lambda repo: repo.get("pushed_at") or "", reverse=True)

    lines = []

    for repo in keep[:COUNT]:
        name = repo["name"]
        owner = repo.get("owner", {}).get("login", "")
        description = (repo.get("description") or "").strip()

        language = repo.get("language")

        updated = repo.get("pushed_at")

        metadata = [
            value
            for value in (
                language,
                f"updated {ago(updated)}" if updated else None,
                "private" if repo.get("private") else None,
            )
            if value
        ]

        # Use full_name to distinguish organization repositories.
        display_name = f"{owner}/{name}" if owner else name

        line = f"- **[{display_name}]({repo['html_url']})**"

        if description:
            line += f": {description}"

        if metadata:
            line += f" _({' · '.join(metadata)})_"

        lines.append(line)

    if not lines:
        lines = ["_Nothing to display yet. Check back soon._"]

    return "\n".join(lines)


def main():

    path = "README.md"

    if not os.path.exists(path):
        sys.exit("README.md not found.")

    with open(path, encoding="utf-8") as file:
        text = file.read()

    if START not in text or END not in text:
        sys.exit(f"README.md must contain {START} and {END}")

    if text.count(START) != 1 or text.count(END) != 1:
        sys.exit("README.md must contain exactly one pair of RECENT markers.")

    repos = fetch_repos()

    block = f"{START}\n{render(repos)}\n{END}"

    new_text = re.sub(
        re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S
    )

    if new_text != text:
        with open(path, "w", encoding="utf-8") as file:
            file.write(new_text)

        print("README.md updated successfully.")

    else:
        print("README.md unchanged.")


if __name__ == "__main__":
    main()
