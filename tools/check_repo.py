"""Validate public-repository hygiene without importing hardware modules."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "README.md",
    "README_EN.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "CITATION.cff",
)
FORBIDDEN_TRACKED_PREFIXES = (
    ".cache/",
    ".cursor/",
    "2026E/output/",
    "2026E/runs/",
    "backup/",
    "logs/",
    "output/",
    "pintu/",
    "reports/",
    "tmp/",
)
FORBIDDEN_TRACKED_PARTS = {"__pycache__", "build"}
FORBIDDEN_TRACKED_FILES = {".cursorignore", "AGENTS.md", "typescript"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def public_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines()]


def check_required(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required public file: {relative}")


def check_tracked_paths(files: list[str], errors: list[str]) -> None:
    for path in files:
        if path in FORBIDDEN_TRACKED_FILES:
            errors.append(f"local-only file is tracked: {path}")
        if path.startswith(FORBIDDEN_TRACKED_PREFIXES):
            errors.append(f"generated/private path is tracked: {path}")
        parts = set(Path(path).parts)
        if parts & FORBIDDEN_TRACKED_PARTS:
            errors.append(f"generated path component is tracked: {path}")


def check_markdown_links(files: list[str], errors: list[str]) -> None:
    for relative in files:
        if not relative.lower().endswith(".md"):
            continue
        document = ROOT / relative
        if not document.is_file():
            continue
        content = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(content):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            local_part = unquote(target.split("#", 1)[0])
            if not local_part:
                continue
            resolved = (document.parent / local_part).resolve()
            if not resolved.exists():
                relative_doc = document.relative_to(ROOT).as_posix()
                errors.append(f"broken local link: {relative_doc} -> {target}")


def main() -> int:
    errors: list[str] = []
    files = public_files()
    check_required(errors)
    check_tracked_paths(files, errors)
    check_markdown_links(files, errors)
    if errors:
        print("Repository hygiene check failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
