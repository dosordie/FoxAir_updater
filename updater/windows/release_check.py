"""Small standard-library GitHub release checker for the Windows GUI.

Kept independent from PySide so version parsing and HTTP response handling can
be unit-tested without importing the GUI toolkit.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


UPDATE_REPO = "dosordie/FoxAir_updater"
UPDATE_API_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_RELEASES_URL = f"https://github.com/{UPDATE_REPO}/releases/latest"


def parse_version_tuple(text: str) -> tuple[int, ...]:
    """Extract a comparable tuple from tags such as windows-v0.1.6."""
    match = re.search(r"(\d+(?:\.\d+){0,4})", str(text or ""))
    if not match:
        return (0, 0, 0)
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_release(current_version: str, release_tag: str) -> bool:
    return parse_version_tuple(release_tag) > parse_version_tuple(current_version)


def fetch_latest_release(
    app_version: str,
    *,
    timeout: float = 12,
    urlopen=urllib.request.urlopen,
) -> dict:
    """Read GitHub's latest-release metadata. No download or installation occurs."""
    request = urllib.request.Request(
        UPDATE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"FoxAir-Updater/{app_version}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub HTTP-Fehler {exc.code}: {exc.reason}") from exc

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("GitHub-Antwort war kein Objekt")

    tag = str(data.get("tag_name", "")).strip()
    if not tag:
        raise RuntimeError("GitHub-Release enthält keinen Versions-Tag")

    return {
        "tag": tag,
        "name": str(data.get("name", "")).strip(),
        "html_url": str(data.get("html_url", UPDATE_RELEASES_URL)).strip()
        or UPDATE_RELEASES_URL,
        "newer": is_newer_release(app_version, tag),
    }
