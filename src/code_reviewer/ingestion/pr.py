"""Load a GitHub PR into a normalized ReviewTarget."""
from __future__ import annotations
import os
import re
import subprocess
import tempfile
from pathlib import Path

from github import Github, Auth
from unidiff import PatchSet

from .types import ReviewTarget, ReviewFile, ChangedRange
from .language import detect_language


_PR_URL_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<num>\d+)")
_PR_SHORT_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^/]+)#(?P<num>\d+)$")


def parse_pr_ref(ref: str) -> tuple[str, str, int]:
    """Parse a PR URL or 'owner/repo#N' shorthand. Returns (owner, repo, number)."""
    m = _PR_URL_RE.search(ref) or _PR_SHORT_RE.match(ref)
    if not m:
        raise ValueError(f"Unrecognized PR ref: {ref!r}")
    return m["owner"], m["repo"], int(m["num"])


def from_pr(ref: str) -> ReviewTarget:
    """Clone the PR head locally, extract changed files, return ReviewTarget."""
    owner, repo, number = parse_pr_ref(ref)

    # Auth is optional for public PRs. Higher rate limits if a token is set.
    token = os.environ.get("GITHUB_TOKEN")
    gh = Github(auth=Auth.Token(token)) if token else Github()

    pr = gh.get_repo(f"{owner}/{repo}").get_pull(number)

    # Shallow-clone the head ref into a tempdir. Static tools need a real filesystem.
    workdir = Path(tempfile.mkdtemp(prefix="review-pr-"))
    clone_url = f"https://github.com/{owner}/{repo}.git"
    _run(["git", "clone", "--depth=1", clone_url, str(workdir)])
    _run([
        "git", "-C", str(workdir), "fetch", "origin",
        f"pull/{number}/head:pr-{number}", "--depth=1",
    ])
    _run(["git", "-C", str(workdir), "checkout", pr.head.sha])

    files: list[ReviewFile] = []
    for f in pr.get_files():
        if f.status == "removed":
            continue
        full_path = workdir / f.filename
        if not full_path.exists() or _is_binary(full_path):
            continue
        lang = detect_language(full_path)
        if lang == "unknown":
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(ReviewFile(
            path=f.filename,
            content=content,
            language=lang,
            changed_ranges=_parse_hunks(f.patch) if f.patch else [],
        ))

    return ReviewTarget(
        source="pr",
        workdir=workdir,
        files=files,
        metadata={
            "title": pr.title,
            "description": pr.body or "",
            "base_sha": pr.base.sha,
            "head_sha": pr.head.sha,
            "pr_url": pr.html_url,
            "owner": owner,
            "repo": repo,
            "number": number,
        },
    )


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _is_binary(path: Path, sniff_bytes: int = 8192) -> bool:
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(sniff_bytes)
        return b"\x00" in chunk
    except OSError:
        return True


def _parse_hunks(patch: str) -> list[ChangedRange]:
    """Convert a GitHub patch fragment into a list of ChangedRange."""
    # GH's patch field omits the file headers unidiff needs
    full = f"--- a/file\n+++ b/file\n{patch}"
    ranges: list[ChangedRange] = []
    try:
        patched = PatchSet(full)
    except Exception:
        return ranges

    for patched_file in patched:
        for hunk in patched_file:
            added = [line for line in hunk if line.is_added]
            if added:
                ranges.append(ChangedRange(
                    line_start=added[0].target_line_no,
                    line_end=added[-1].target_line_no,
                    change_type="added",
                ))
    return ranges
