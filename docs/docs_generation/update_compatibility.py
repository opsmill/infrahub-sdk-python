#!/usr/bin/env python3
"""Fetch Infrahub/SDK version mappings from GitHub and update compatibility.py.

Queries the GitHub API to discover Infrahub release tags, resolve the SDK
version pinned via the python_sdk submodule for each release, and rewrite
the RELEASE_MAPPINGS and VERSION_RANGES lists in compatibility.py.

Usage:
    uv run python docs/docs_generation/update_compatibility.py

Set GITHUB_TOKEN in the environment to avoid rate limiting (unauthenticated
requests are limited to 60/hour).
"""

from __future__ import annotations

import operator
import os
import re
import sys
from calendar import month_name
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

INFRAHUB_REPO = "opsmill/infrahub"
SDK_REPO = "opsmill/infrahub-sdk-python"
API_BASE = "https://api.github.com"
TAG_PATTERN = re.compile(r"^infrahub-v(\d+\.\d+\.\d+)$")
SDK_TAG_PATTERN = re.compile(r"^v(\d+\.\d+\.\d+)$")

COMPATIBILITY_FILE = Path(__file__).parent / "compatibility.py"


def _github_headers() -> dict[str, str]:
    """Build HTTP headers, including auth token if available."""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _paginated_get(client: httpx.Client, url: str) -> list[dict]:
    """Fetch all pages from a paginated GitHub API endpoint.

    Args:
        client: httpx client with auth headers configured.
        url: Initial API URL to fetch.

    Returns:
        Combined list of JSON objects from all pages.
    """
    results: list[dict] = []
    while url:
        resp = client.get(url)
        resp.raise_for_status()
        results.extend(resp.json())
        url = resp.headers.get("link", "")
        next_match = re.search(r'<([^>]+)>;\s*rel="next"', url)
        url = next_match.group(1) if next_match else ""
    return results


def _fetch_infrahub_tags(client: httpx.Client) -> dict[str, str]:
    """Fetch all infrahub-v* tags and return {version: commit_sha}.

    Args:
        client: httpx client with auth headers configured.

    Returns:
        Dict mapping version strings (e.g. "1.8.4") to commit SHAs.
    """
    tags = _paginated_get(client, f"{API_BASE}/repos/{INFRAHUB_REPO}/tags?per_page=100")
    result = {}
    for tag in tags:
        match = TAG_PATTERN.match(tag["name"])
        if match:
            result[match.group(1)] = tag["commit"]["sha"]
    return result


def _fetch_sdk_tags(client: httpx.Client) -> dict[str, str]:
    """Fetch all SDK v* tags and return {commit_sha: version}.

    Args:
        client: httpx client with auth headers configured.

    Returns:
        Dict mapping commit SHAs to version strings (e.g. "1.19.0").
    """
    tags = _paginated_get(client, f"{API_BASE}/repos/{SDK_REPO}/tags?per_page=100")
    result = {}
    for tag in tags:
        match = SDK_TAG_PATTERN.match(tag["name"])
        if match:
            result[tag["commit"]["sha"]] = match.group(1)
    return result


def _get_submodule_sha(client: httpx.Client, commit_sha: str) -> str | None:
    """Get the python_sdk submodule commit SHA for an Infrahub commit.

    Args:
        client: httpx client with auth headers configured.
        commit_sha: The Infrahub commit SHA to inspect.

    Returns:
        The submodule commit SHA, or None if not found.
    """
    resp = client.get(f"{API_BASE}/repos/{INFRAHUB_REPO}/git/trees/{commit_sha}")
    resp.raise_for_status()
    for entry in resp.json().get("tree", []):
        if entry["path"] == "python_sdk" and entry["mode"] == "160000":
            return entry["sha"]
    return None


def _get_commit_date(client: httpx.Client, repo: str, sha: str) -> str:
    """Get the commit date for a SHA.

    Args:
        client: httpx client with auth headers configured.
        repo: GitHub repo in "owner/repo" format.
        sha: Commit SHA.

    Returns:
        Date string in YYYY-MM-DD format.
    """
    resp = client.get(f"{API_BASE}/repos/{repo}/git/commits/{sha}")
    resp.raise_for_status()
    date_str = resp.json()["committer"]["date"]
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d")


def _find_nearest_sdk_version(
    client: httpx.Client,
    submodule_sha: str,
    sdk_tag_map: dict[str, str],
) -> str | None:
    """Find the SDK version for a submodule commit.

    Checks if the commit is directly tagged. If not, walks backwards through
    ancestors to find the nearest tagged version.

    Args:
        client: httpx client with auth headers configured.
        submodule_sha: The SDK commit SHA from the submodule.
        sdk_tag_map: Mapping of commit SHAs to SDK version strings.

    Returns:
        SDK version string, or None if no version could be resolved.
    """
    if submodule_sha in sdk_tag_map:
        return sdk_tag_map[submodule_sha]

    # Walk up to 50 ancestors to find a tagged commit
    current = submodule_sha
    for _ in range(50):
        resp = client.get(f"{API_BASE}/repos/{SDK_REPO}/git/commits/{current}")
        if resp.status_code != 200:
            break
        parents = resp.json().get("parents", [])
        if not parents:
            break
        current = parents[0]["sha"]
        if current in sdk_tag_map:
            return sdk_tag_map[current]

    return None


def _version_sort_key(version: str) -> tuple[int, ...]:
    """Parse a version string into a tuple for sorting.

    Args:
        version: Dot-separated version string (e.g. "1.8.4").

    Returns:
        Tuple of integers for comparison.
    """
    return tuple(int(x) for x in version.split("."))


def _derive_version_ranges(
    release_mappings: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Derive VERSION_RANGES from RELEASE_MAPPINGS.

    Groups releases by minor version and finds the minimum SDK version
    and earliest release date for each group.

    Args:
        release_mappings: List of (infrahub_version, sdk_version, date) tuples.

    Returns:
        List of (infrahub_pattern, min_sdk, month_year) tuples, sorted by
        version descending.
    """
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for infrahub_ver, sdk_ver, date in release_mappings:
        parts = infrahub_ver.split(".")
        minor_key = f"{parts[0]}.{parts[1]}"
        groups[minor_key].append((sdk_ver, date))

    ranges = []
    for minor_key, entries in groups.items():
        # Find the minimum SDK version (lowest version number)
        min_sdk = min(entries, key=lambda e: _version_sort_key(e[0]))[0]
        # Find the earliest date for the month label
        earliest_date = min(entries, key=operator.itemgetter(1))[1]
        dt = datetime.strptime(earliest_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        month_year = f"{month_name[dt.month]} {dt.year}"
        ranges.append((f"{minor_key}.x", min_sdk, month_year))

    ranges.sort(key=lambda r: _version_sort_key(r[0].replace(".x", ".0")), reverse=True)
    return ranges


def _format_release_mappings(mappings: list[tuple[str, str, str]]) -> str:
    """Format RELEASE_MAPPINGS list as Python source code.

    Args:
        mappings: List of (infrahub_version, sdk_version, date) tuples.

    Returns:
        Python source for the RELEASE_MAPPINGS list assignment.
    """
    lines = [
        "# Detailed mapping of every Infrahub release to its pinned SDK version.",
        "# Auto-updated by update_compatibility.py.",
        "RELEASE_MAPPINGS: list[ReleaseMapping] = [",
    ]
    for infrahub_ver, sdk_ver, date in mappings:
        lines.append(f'    ReleaseMapping(infrahub="{infrahub_ver}", sdk="{sdk_ver}", date="{date}"),')
    lines.append("]")
    return "\n".join(lines)


def _format_version_ranges(ranges: list[tuple[str, str, str]]) -> str:
    """Format VERSION_RANGES list as Python source code.

    Args:
        ranges: List of (infrahub_pattern, min_sdk, month_year) tuples.

    Returns:
        Python source for the VERSION_RANGES list assignment.
    """
    lines = [
        "# Mapping of Infrahub minor version series to minimum SDK versions.",
        "# Auto-updated by update_compatibility.py.",
        "VERSION_RANGES: list[VersionRange] = [",
    ]
    for pattern, min_sdk, month_year in ranges:
        lines.append(f'    VersionRange(infrahub="{pattern}", min_sdk="{min_sdk}", date="{month_year}"),')
    lines.append("]")
    return "\n".join(lines)


def _update_file(release_mappings: list[tuple[str, str, str]]) -> None:
    """Rewrite the VERSION_RANGES and RELEASE_MAPPINGS in compatibility.py.

    Args:
        release_mappings: List of (infrahub_version, sdk_version, date) tuples,
            sorted by version descending.
    """
    content = COMPATIBILITY_FILE.read_text()

    version_ranges = _derive_version_ranges(release_mappings)

    # Replace VERSION_RANGES block
    content = re.sub(
        r"# Mapping of Infrahub minor version series.*?^]",
        _format_version_ranges(version_ranges),
        content,
        flags=re.DOTALL | re.MULTILINE,
    )

    # Replace RELEASE_MAPPINGS block
    content = re.sub(
        r"# Detailed mapping of every Infrahub release.*?^]",
        _format_release_mappings(release_mappings),
        content,
        flags=re.DOTALL | re.MULTILINE,
    )

    COMPATIBILITY_FILE.write_text(content)


def main() -> None:
    """Fetch version data from GitHub and update compatibility.py."""
    headers = _github_headers()
    if "Authorization" not in headers:
        print("Warning: GITHUB_TOKEN not set. API rate limit is 60 requests/hour.", file=sys.stderr)

    with httpx.Client(headers=headers, timeout=30) as client:
        print("Fetching Infrahub release tags...")
        infrahub_tags = _fetch_infrahub_tags(client)
        print(f"  Found {len(infrahub_tags)} releases")

        print("Fetching SDK version tags...")
        sdk_tag_map = _fetch_sdk_tags(client)
        print(f"  Found {len(sdk_tag_map)} SDK versions")

        release_mappings: list[tuple[str, str, str]] = []

        sorted_versions = sorted(infrahub_tags.keys(), key=_version_sort_key, reverse=True)
        for version in sorted_versions:
            commit_sha = infrahub_tags[version]
            print(f"  Resolving Infrahub {version}...", end=" ", flush=True)

            submodule_sha = _get_submodule_sha(client, commit_sha)
            if not submodule_sha:
                print("no python_sdk submodule found, skipping")
                continue

            sdk_version = _find_nearest_sdk_version(client, submodule_sha, sdk_tag_map)
            if not sdk_version:
                print("could not resolve SDK version, skipping")
                continue

            date = _get_commit_date(client, INFRAHUB_REPO, commit_sha)
            release_mappings.append((version, sdk_version, date))
            print(f"SDK {sdk_version} ({date})")

        if not release_mappings:
            print("No release mappings found. Check your network or GITHUB_TOKEN.", file=sys.stderr)
            sys.exit(1)

        release_mappings.sort(key=lambda r: _version_sort_key(r[0]), reverse=True)

        print(f"\nUpdating {COMPATIBILITY_FILE}...")
        _update_file(release_mappings)
        print("Done. Run 'uv run invoke docs-generate' to regenerate the docs page.")


if __name__ == "__main__":
    main()
