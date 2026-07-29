#!/usr/bin/env python3
"""Search the disposable project-document index without external services."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / ".cache" / "docs_index" / "index.json"


def terms(query: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', query)
    remainder = re.sub(r'"[^"]+"', " ", query)
    return [item.casefold() for item in quoted + remainder.split() if item.strip()]


def snippet(text: str, needles: list[str], width: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    folded = compact.casefold()
    positions = [folded.find(term) for term in needles if folded.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 60)
    end = min(len(compact), start + width)
    result = compact[start:end]
    if start:
        result = "…" + result
    if end < len(compact):
        result += "…"
    return result


def score(entry: dict, needles: list[str]) -> int:
    path = entry.get("path", "").casefold()
    title = entry.get("title", "").casefold()
    text = entry.get("text", "").casefold()
    total = 0
    matched = 0
    for term in needles:
        found = term in path or term in title or term in text
        if not found:
            continue
        matched += 1
        total += 12 if term in path else 0
        total += 8 if term in title else 0
        total += min(8, text.count(term) * 2)
    if matched == len(needles):
        total += 25
    else:
        total -= (len(needles) - matched) * 5
    if entry.get("kind") == "code_symbol":
        total += 8
    if entry.get("kind") == "pdf_page":
        total += 4
    secondary = {
        "docs/readme.md", "docs/project_facts.md",
        "docs/decisions.md", "docs/todo_verify.md",
    }
    if path in secondary or path.startswith("tools/") or path == "agents.md":
        total -= 30
    return total if matched else 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="space-separated terms; quote phrases")
    parser.add_argument("-n", "--limit", type=int, default=20)
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        print(
            "索引不存在。请先运行: python tools/update_docs_index.py",
            file=sys.stderr,
        )
        return 2
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"索引无法读取: {exc}", file=sys.stderr)
        return 2

    needles = terms(args.query)
    if not needles:
        parser.error("query must not be empty")
    ranked = []
    for entry in data.get("entries", []):
        value = score(entry, needles)
        if value > 0:
            ranked.append((value, entry))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].get("path", ""), pair[1].get("location", "")))

    if not ranked:
        print("未找到匹配项。请尝试减少关键词或改用原始术语。")
        return 1
    for index, (value, entry) in enumerate(ranked[: max(1, args.limit)], 1):
        visual = "是" if entry.get("needs_visual_inspection") else "否"
        location = entry.get("location") or "文件级"
        print(f"[{index}] {entry.get('path')}")
        print(f"    位置: {location}")
        print(f"    类型: {entry.get('source_type', '未知')} | 需视觉检查: {visual} | 匹配分: {value}")
        excerpt = snippet(entry.get("text", ""), needles)
        if excerpt:
            print(f"    片段: {excerpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
