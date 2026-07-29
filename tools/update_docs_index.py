#!/usr/bin/env python3
"""Build a disposable, static-search index for this project.

The script never imports project modules, runs demos, or accesses hardware.
It reads ZIP members in memory and never modifies source archives.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "docs_index"
MANIFEST_PATH = CACHE / "file_manifest.json"
INDEX_PATH = CACHE / "index.json"
REPORT_PATH = CACHE / "INDEX_REPORT.md"

EXCLUDED_TOP = {".cache", ".git", ".idea", ".vscode", "__pycache__"}
CODE_EXTENSIONS = {".py", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".ino"}
C_EXTENSIONS = {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".ino"}
FIRMWARE_EXTENSIONS = {".hex", ".bin", ".uf2", ".elf", ".axf", ".fw"}
TEXT_EXTENSIONS = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".ini", ".cfg", ".toml",
    ".py", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".ino", ".s",
    ".ld", ".icf", ".sct", ".uvprojx", ".xml", ".html", ".htm",
}
ZIP_INTERESTING = TEXT_EXTENSIONS | {".pdf", ".hex", ".bin", ".elf", ".axf"}
MAX_TEXT_BYTES = 2_000_000
VERSION_RE = re.compile(
    r"(?:(?i:version|ver|版本|firmware|sdk|jetpack|l4t)"
    r"[\s_\-:：]*(v?\d+(?:\.\d+){1,3}(?:[-_a-z0-9.]*)?)"
    r"|(?<![A-Za-z0-9])(V\d+(?:\.\d+){1,3}(?:[-_a-z0-9.]*)?)\b)"
)
KEYWORDS = [
    "Jetson", "Jetson Orin Nano", "Orin Super", "JetPack", "L4T", "Ubuntu",
    "GPIO", "BOARD", "BCM", "SOC GPIO", "PADCTL", "busybox devmem", "设备树",
    "DTS", "DTBO", "Jetson-IO", "USB", "UART", "摄像头", "V4L2", "GStreamer",
    "OpenCV", "NexArm", "NexArmClient", "UART_Control", "WiFi_Control",
    "set_pose", "get_current_coords", "get_firmware_version",
    "get_battery_voltage", "request", "read_packet", "Global.h", "CommProtocol",
    "CMD", "checksum", "Pitch", "Roll", "Claw", "action group", "servo",
    "inverse kinematics", "forward kinematics", "STM32", "STM32F103C8T6",
    "PA9", "PA10", "USART1", "SWDIO", "SWCLK", "BOOT0", "BOOT1", "USB CDC",
    "MOSFET", "继电器", "电磁铁", "续流二极管", "TVS", "看门狗", "心跳",
    "超时关闭", "独立供电",
]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_project_files() -> Iterable[Path]:
    for current, dirs, files in os.walk(ROOT):
        current_path = Path(current)
        if current_path == ROOT:
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_TOP)
        else:
            dirs[:] = sorted(d for d in dirs if d not in {"__pycache__"})
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                continue
            yield path


def classify(path_string: str, suffix: str) -> dict[str, Any]:
    lower = path_string.lower()
    if "nexarm" in lower or "幻尔" in lower or "hiwonder" in lower:
        vendor, device = "幻尔科技 Hiwonder", "NexArm / 配套舵机或控制器"
    elif "板端/" in lower or "板端\\" in lower or "jetson" in lower or "亚博" in lower:
        vendor, device = "亚博智能 Yahboom（部分内容可能引用 NVIDIA）", "Jetson 平台/亚博载板"
    elif "stm32" in lower:
        vendor, device = "ST 或核心板销售方", "STM32F103C8T6 核心板"
    elif "mosfet" in lower or "电磁铁" in lower:
        vendor, device = "器件/模块销售方", "电磁铁与驱动模块"
    elif "tasksuite" in lower or "e题" in lower or "拼图" in lower:
        vendor, device = "用户项目/赛题资料", "2026 电赛 E 题工程"
    else:
        vendor, device = "未自动识别", "未自动识别"

    historical = any(term in lower for term in ("旧", "历史", "整理", "summary", "archive"))
    if suffix == ".pdf":
        category = "PDF 文档"
    elif suffix == ".zip":
        category = "ZIP 资料包"
    elif suffix in FIRMWARE_EXTENSIONS:
        category = "固件/可执行映像"
    elif suffix == ".py":
        category = "Python 源码"
    elif suffix in C_EXTENSIONS:
        category = "C/C++/Arduino 源码"
    elif suffix in {".md", ".txt", ".doc", ".docx"}:
        category = "说明文档"
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".dwg", ".dxf", ".step", ".stp"}:
        category = "图像/图纸"
    else:
        category = "其他项目文件"

    official_hints = (
        "数据手册", "datasheet", "_ds_", "原理图", "使用手册", "通信协议",
        "主板介绍", "技术参数&图纸",
    )
    original = path_string.startswith("docs/") and (
        suffix in {".pdf", ".zip", ".doc", ".docx"}
        or any(hint in lower for hint in official_hints)
    ) and not historical
    visual = suffix == ".pdf" and any(
        term in lower
        for term in ("原理图", "尺寸图", "接线", "引脚", "gpio", "图纸", "卡片")
    )
    return {
        "vendor_or_source": vendor,
        "applicable_device": device,
        "file_category": category,
        "is_historical_summary": historical,
        "is_original_material": original,
        "needs_visual_inspection": visual,
    }


def extract_versions(text: str) -> list[str]:
    values = set()
    for match in VERSION_RE.finditer(text):
        value = next(group for group in match.groups() if group).strip("._-")
        value = re.sub(r"(?i)\.(?:pdf|zip|bin|apk|exe)$", "", value)
        values.add(value)
    return sorted(v for v in values if 3 <= len(v) <= 32)[:30]


def keyword_hits(text: str) -> list[str]:
    folded = text.casefold()
    return [keyword for keyword in KEYWORDS if keyword.casefold() in folded]


def decode_text(raw: bytes) -> str:
    if b"\x00" in raw[:4096]:
        return ""
    for encoding in ("utf-8-sig", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def skip_zip_member_content(member: str) -> bool:
    """Keep the tree/hash but do not full-text index vendored environments/caches."""
    normalized = "/" + member.replace("\\", "/").casefold().strip("/") + "/"
    blocked = (
        "/.venv/", "/venv/", "/site-packages/", "/node_modules/",
        "/.mypy_cache/", "/.pytest_cache/", "/__pycache__/", "/.git/",
        "/.tox/", "/dist-info/", "/egg-info/",
    )
    return any(part in normalized for part in blocked)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def signature_from_ast(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args = ast.unparse(node.args)
    except Exception:
        args = "..."
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}{node.name}({args})"


def python_symbols(text: str, source: str) -> dict[str, Any]:
    result: dict[str, Any] = {"source": source, "language": "python", "symbols": []}
    hardware_terms = sorted(
        term for term in ("serial", "socket", "GPIO", "/dev/tty", "Jetson.GPIO")
        if term.casefold() in text.casefold()
    )
    result["hardware_call_indicators"] = hardware_terms
    try:
        tree = ast.parse(text)
    except (SyntaxError, RecursionError, MemoryError) as exc:
        if isinstance(exc, SyntaxError):
            result["parse_error"] = f"line {exc.lineno}: {exc.msg}"
        else:
            result["parse_error"] = f"{type(exc).__name__}: {exc}"
        return result

    parents: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            result["symbols"].append({
                "kind": "class", "name": ".".join(parents + [node.name]),
                "signature": node.name, "line": node.lineno,
            })
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            result["symbols"].append({
                "kind": "method" if parents else "function",
                "name": ".".join(parents + [node.name]),
                "signature": signature_from_ast(node), "line": node.lineno,
            })
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        visit_FunctionDef = _function
        visit_AsyncFunctionDef = _function

    Visitor().visit(tree)
    return result


def c_symbols(text: str, source: str) -> dict[str, Any]:
    result: dict[str, Any] = {"source": source, "language": "c_cpp", "symbols": []}
    lines = text.splitlines()
    macro_re = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\s*(.*)$")
    type_re = re.compile(r"^\s*(?:typedef\s+)?(enum|struct)\s+([A-Za-z_]\w*)?")
    function_re = re.compile(
        r"^\s*(?!if\b|for\b|while\b|switch\b)"
        r"([A-Za-z_][\w\s:*&<>,\[\]]*?)\s+([A-Za-z_]\w*)\s*"
        r"\(([^;{}]*)\)\s*([;{])"
    )
    for line_no, line in enumerate(lines, 1):
        macro = macro_re.match(line)
        if macro:
            name, value = macro.groups()
            if (
                name.upper().startswith(("CMD", "UART", "GPIO", "USART", "VERSION"))
                or any(term in value.upper() for term in ("CMD", "UART", "GPIO", "VERSION"))
            ):
                result["symbols"].append({
                    "kind": "macro", "name": name,
                    "signature": f"#define {name} {value}".strip(), "line": line_no,
                })
            continue
        typed = type_re.match(line)
        if typed:
            kind, name = typed.groups()
            result["symbols"].append({
                "kind": kind, "name": name or f"anonymous@{line_no}",
                "signature": line.strip(), "line": line_no,
            })
        function = function_re.match(line)
        if function:
            return_type, name, args, terminator = function.groups()
            result["symbols"].append({
                "kind": "declaration" if terminator == ";" else "definition",
                "name": name,
                "signature": f"{return_type.strip()} {name}({args.strip()})",
                "line": line_no,
            })
    result["hardware_call_indicators"] = sorted(
        term for term in ("UART", "USART", "GPIO", "HAL_GPIO", "Serial", "Wire")
        if term.casefold() in text.casefold()
    )
    return result


def symbol_cache_path(source: str) -> Path:
    return CACHE / "code_symbols" / f"{stable_id(source)}.json"


def index_code_text(text: str, source: str, suffix: str, entries: list[dict[str, Any]]) -> None:
    analysis = python_symbols(text, source) if suffix == ".py" else c_symbols(text, source)
    write_json(symbol_cache_path(source), analysis)
    for symbol in analysis.get("symbols", []):
        entries.append({
            "kind": "code_symbol",
            "path": source,
            "location": f"line {symbol['line']}",
            "title": symbol["name"],
            "text": symbol["signature"],
            "source_type": "源码静态分析",
            "needs_visual_inspection": False,
        })
    if analysis.get("parse_error"):
        entries.append({
            "kind": "parse_error", "path": source, "location": "",
            "title": "源码解析失败", "text": analysis["parse_error"],
            "source_type": "源码静态分析", "needs_visual_inspection": False,
        })


def read_small_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return ""
        return decode_text(path.read_bytes())
    except OSError:
        return ""


def extract_pdf(path: Path, source: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    cache_path = CACHE / "pdf_text" / f"{stable_id(source)}.json"
    info: dict[str, Any] = {
        "source_pdf": source, "pages": [], "parse_error": None,
        "needs_visual_inspection": False,
    }
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path), strict=False)
        visual_by_name = classify(source, ".pdf")["needs_visual_inspection"]
        low_text_pages = 0
        for page_no, page in enumerate(reader.pages, 1):
            try:
                text = clean_text(page.extract_text() or "")
            except Exception as exc:
                text = ""
                page_error = f"{type(exc).__name__}: {exc}"
            else:
                page_error = None
            sparse = len(text) < 60
            low_text_pages += int(sparse)
            info["pages"].append({
                "page": page_no, "text": text, "character_count": len(text),
                "needs_visual_inspection": sparse, "error": page_error,
            })
            entries.append({
                "kind": "pdf_page", "path": source, "location": f"page {page_no}",
                "title": path.name, "text": text[:10000],
                "source_type": "PDF 逐页文本缓存",
                "needs_visual_inspection": sparse or visual_by_name,
            })
        page_count = len(info["pages"])
        visual_by_content = bool(page_count and low_text_pages / page_count >= 0.25)
        info["needs_visual_inspection"] = visual_by_content or visual_by_name
    except Exception as exc:
        info["parse_error"] = f"{type(exc).__name__}: {exc}"
        info["needs_visual_inspection"] = True
    write_json(cache_path, info)
    return info


def inspect_zip(
    path: Path,
    source: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_zip": source, "members": [], "versions": [], "error": None,
        "duplicate_member_names": [], "same_name_different_hash": [],
    }
    seen_names: Counter[str] = Counter()
    hashes_by_name: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    versions: set[str] = set(extract_versions(source))
    try:
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                member = item.filename.replace("\\", "/")
                seen_names[Path(member).name.casefold()] += int(not item.is_dir())
                member_info: dict[str, Any] = {
                    "path": member, "size": item.file_size,
                    "compressed_size": item.compress_size, "crc32": f"{item.CRC:08x}",
                    "is_dir": item.is_dir(),
                }
                result["members"].append(member_info)
                versions.update(extract_versions(member))
                if item.is_dir() or item.file_size > MAX_TEXT_BYTES:
                    continue
                suffix = Path(member).suffix.lower()
                if suffix not in ZIP_INTERESTING:
                    continue
                inner_source = f"{source}!/{member}"
                try:
                    member_digest = hashlib.sha256()
                    raw_parts = []
                    with archive.open(item) as member_stream:
                        for chunk in iter(lambda: member_stream.read(1024 * 1024), b""):
                            member_digest.update(chunk)
                            if item.file_size <= MAX_TEXT_BYTES:
                                raw_parts.append(chunk)
                    member_info["sha256"] = member_digest.hexdigest()
                    hashes_by_name[Path(member).name.casefold()][
                        member_info["sha256"]
                    ].append(member)
                    raw = b"".join(raw_parts)
                except Exception as exc:
                    member_info["hash_error"] = f"{type(exc).__name__}: {exc}"
                    continue
                if skip_zip_member_content(member):
                    member_info["content_index_skipped"] = True
                    continue
                if suffix in TEXT_EXTENSIONS:
                    text = decode_text(raw)
                    entries.append({
                        "kind": "zip_member_text", "path": inner_source, "location": "",
                        "title": Path(member).name, "text": clean_text(text)[:10000],
                        "source_type": "ZIP 内部文件静态读取",
                        "needs_visual_inspection": False,
                    })
                    versions.update(extract_versions(text[:20000]))
                    if suffix in CODE_EXTENSIONS:
                        try:
                            index_code_text(text, inner_source, suffix, entries)
                        except (RecursionError, MemoryError) as exc:
                            entries.append({
                                "kind": "parse_error", "path": inner_source,
                                "location": "", "title": "源码解析失败",
                                "text": f"{type(exc).__name__}: {exc}",
                                "source_type": "ZIP 内部文件静态读取",
                                "needs_visual_inspection": False,
                            })
            result["duplicate_member_names"] = sorted(
                name for name, count in seen_names.items() if count > 1 and name
            )
            result["same_name_different_hash"] = [
                {
                    "filename": name,
                    "variants": [
                        {"sha256": digest, "paths": paths}
                        for digest, paths in sorted(variants.items())
                    ],
                }
                for name, variants in sorted(hashes_by_name.items())
                if len(variants) > 1
            ]
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["versions"] = sorted(versions)
    tree_path = CACHE / "zip_tree" / f"{stable_id(source)}.json"
    write_json(tree_path, result)
    return result


def markdown_link_errors(files: list[Path]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    link_re = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        text = read_small_text(path)
        for target in link_re.findall(text):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z]+://", target, re.I) or target.startswith("mailto:"):
                continue
            candidate = (path.parent / target.replace("/", os.sep)).resolve()
            if not candidate.exists():
                errors.append({"source": rel(path), "target": target})
    return errors


def report_list(values: Iterable[str], empty: str = "未识别") -> str:
    unique = sorted({value for value in values if value})
    return "\n".join(f"- {value}" for value in unique) if unique else f"- {empty}"


def build_report(
    manifest: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    pdf_infos: dict[str, dict[str, Any]],
    zip_infos: dict[str, dict[str, Any]],
    link_errors: list[dict[str, str]],
    parse_errors: list[str],
) -> str:
    counts = Counter(item["extension"] for item in manifest)
    previous_by_path = {item["relative_path"]: item for item in previous}
    current_by_path = {item["relative_path"]: item for item in manifest}
    new_files = sorted(set(current_by_path) - set(previous_by_path))
    removed_files = sorted(set(previous_by_path) - set(current_by_path))
    moved = []
    removed_by_hash: dict[str, list[str]] = defaultdict(list)
    for path, item in previous_by_path.items():
        if path not in current_by_path:
            removed_by_hash[item.get("sha256", "")].append(path)
    for path in new_files:
        digest = current_by_path[path]["sha256"]
        for old_path in removed_by_hash.get(digest, []):
            moved.append(f"{old_path} -> {path}")

    by_hash: dict[str, list[str]] = defaultdict(list)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in manifest:
        by_hash[item["sha256"]].append(item["relative_path"])
        by_name[item["filename"].casefold()].append(item)
    duplicates = [paths for paths in by_hash.values() if len(paths) > 1]
    same_name_diff_hash = [
        [item["relative_path"] for item in items]
        for items in by_name.values()
        if len({item["sha256"] for item in items}) > 1
    ]

    vendors = {
        item["vendor_or_source"] for item in manifest
        if item["vendor_or_source"] != "未自动识别"
    }
    devices = {
        item["applicable_device"] for item in manifest
        if item["applicable_device"] != "未自动识别"
    }
    versions = sorted({
        f"{version} — {item['relative_path']}"
        for item in manifest
        if re.search(
            r"(?i)(?:version|ver|版本|firmware|sdk|jetpack|l4t|(?:^|[_ -])v)\d",
            item["filename"],
        )
        for version in item.get("discovered_versions", [])
    })
    sdk_hits = sorted({
        term for item in manifest for term in item.get("keywords", [])
        if term in {"NexArm", "NexArmClient", "UART_Control", "WiFi_Control", "OpenCV"}
    })
    firmware = [
        item["relative_path"] for item in manifest
        if item["extension"] in FIRMWARE_EXTENSIONS
    ]
    searchable = [
        source for source, info in pdf_infos.items()
        if not info.get("parse_error") and not info.get("needs_visual_inspection")
    ]
    visual = [
        source for source, info in pdf_infos.items()
        if info.get("needs_visual_inspection") and not info.get("parse_error")
    ]
    failed_pdf = [
        source for source, info in pdf_infos.items() if info.get("parse_error")
    ]
    zip_failures = [
        f"{source}: {info['error']}" for source, info in zip_infos.items() if info.get("error")
    ]
    zip_name_conflicts = [
        f"{source}!/{conflict['filename']}"
        for source, info in zip_infos.items()
        for conflict in info.get("same_name_different_hash", [])
    ]
    todo_path = ROOT / "docs" / "TODO_VERIFY.md"
    verified_missing = []
    if todo_path.exists():
        verified_missing = re.findall(
            r"^##\s+V-\d+\s+(.+)$",
            todo_path.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )

    def bullets(values: Iterable[str], empty: str = "无", limit: int = 100) -> str:
        values = list(values)
        if not values:
            return f"- {empty}"
        shown = values[:limit]
        result = "\n".join(f"- `{value}`" for value in shown)
        if len(values) > limit:
            result += f"\n- ……另有 {len(values) - limit} 项，完整信息见 JSON 清单。"
        return result

    firmware_ext_count = sum(counts[ext] for ext in FIRMWARE_EXTENSIONS)
    c_count = sum(counts[ext] for ext in C_EXTENSIONS)
    docs_count = sum(item["relative_path"].startswith("docs/") for item in manifest)
    report = f"""# INDEX_REPORT

> 本文件由 `tools/update_docs_index.py` 自动生成。缓存不是项目事实来源，结论必须回到原 PDF、源码或 ZIP 核查。

## 扫描概况

- 扫描范围：项目根目录（排除 `.cache/`、`.git/`、IDE 缓存）
- 生成时间：{time.strftime("%Y-%m-%d %H:%M:%S %z")}
- 文件总数：{len(manifest)}
- docs 文件数：{docs_count}
- PDF 数量：{counts[".pdf"]}
- ZIP 数量：{counts[".zip"]}
- Python 文件数：{counts[".py"]}
- C/C++/Arduino 文件数：{c_count}
- 固件文件数：{firmware_ext_count}

## PDF 状态

- 可直接检索的 PDF：{len(searchable)}
- 需要视觉检查的 PDF：{len(visual)}
- 无法解析的 PDF：{len(failed_pdf)}

### 需要视觉检查

{bullets(visual)}

### 无法解析

{bullets(failed_pdf)}

## 识别结果

### 主要厂商或来源

{report_list(vendors)}

### 主要硬件

{report_list(devices)}

### SDK/软件主题

{report_list(sdk_hits)}

### 固件

{bullets(firmware)}

### 版本候选

{report_list(versions[:100], "未从路径或小型文本中识别")}

## 增量变化

### 新增文件

{bullets(new_files)}

### 删除文件

{bullets(removed_files)}

### 疑似移动

{bullets(moved)}

## 重复与冲突

- 重复内容组数：{len(duplicates)}
- 同名不同哈希组数：{len(same_name_diff_hash)}

### 重复文件

{bullets([" | ".join(group) for group in duplicates])}

### 同名不同哈希文件

{bullets([" | ".join(group) for group in same_name_diff_hash])}

### ZIP 内同名不同哈希文件

{bullets(zip_name_conflicts)}

## Markdown 链接

- 失效链接数：{len(link_errors)}

{bullets([f"{item['source']} -> {item['target']}" for item in link_errors])}

## 无法解析的文件

{bullets(parse_errors + zip_failures)}

## 确实缺失的资料

以下项目已完成人工资料核查，但仍需要实物、系统只读查询或测量；详情见 `docs/TODO_VERIFY.md`：

{report_list(verified_missing, "无")}
"""
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore prior metadata and rebuild")
    args = parser.parse_args()

    for folder in ("pdf_text", "pdf_pages", "zip_tree", "code_symbols", "manifests"):
        (CACHE / folder).mkdir(parents=True, exist_ok=True)

    previous = read_json(MANIFEST_PATH, [])
    previous_by_path = {item.get("relative_path"): item for item in previous}
    previous_index = read_json(INDEX_PATH, {"entries": []})
    previous_entries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for old_entry in previous_index.get("entries", []):
        physical_source = old_entry.get("path", "").split("!/", 1)[0]
        previous_entries[physical_source].append(old_entry)
    files = list(iter_project_files())
    manifest: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    pdf_infos: dict[str, dict[str, Any]] = {}
    zip_infos: dict[str, dict[str, Any]] = {}
    parse_errors: list[str] = []

    for number, path in enumerate(files, 1):
        source = rel(path)
        stat = path.stat()
        old = previous_by_path.get(source, {})
        unchanged = (
            not args.force
            and old.get("size") == stat.st_size
            and old.get("mtime_ns") == stat.st_mtime_ns
            and old.get("sha256")
        )
        digest = old["sha256"] if unchanged else sha256_file(path)
        suffix = path.suffix.lower()
        metadata = classify(source, suffix)
        seed_text = source
        if suffix in TEXT_EXTENSIONS and stat.st_size <= MAX_TEXT_BYTES:
            seed_text += "\n" + read_small_text(path)[:20000]
        versions = extract_versions(seed_text)
        keywords = keyword_hits(seed_text)
        item = {
            "relative_path": source,
            "filename": path.name,
            "extension": suffix,
            "size": stat.st_size,
            "modified_time": time.strftime(
                "%Y-%m-%dT%H:%M:%S%z", time.localtime(stat.st_mtime)
            ),
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest,
            **metadata,
            "discovered_versions": versions,
            "keywords": keywords,
        }

        entries.append({
            "kind": "file", "path": source, "location": "",
            "title": path.name, "text": f"{source}\n{' '.join(keywords)}",
            "source_type": metadata["file_category"],
            "needs_visual_inspection": metadata["needs_visual_inspection"],
        })

        reusable_entries = [
            entry for entry in previous_entries.get(source, [])
            if entry.get("kind") != "file"
        ]
        pdf_cache = CACHE / "pdf_text" / f"{stable_id(source)}.json"
        zip_cache = CACHE / "zip_tree" / f"{stable_id(source)}.json"
        reusable = unchanged and bool(reusable_entries)

        if suffix == ".pdf" and reusable and pdf_cache.exists():
            pdf_info = read_json(pdf_cache, {})
            entries.extend(reusable_entries)
            pdf_infos[source] = pdf_info
            item["needs_visual_inspection"] = pdf_info.get("needs_visual_inspection", True)
            item["pdf_page_count"] = len(pdf_info.get("pages", []))
            item["pdf_parse_error"] = pdf_info.get("parse_error")
            page_text = "\n".join(
                page.get("text", "")[:3000] for page in pdf_info.get("pages", [])
            )
            item["keywords"] = sorted(set(item["keywords"]) | set(keyword_hits(page_text)))
            item["discovered_versions"] = sorted(
                set(item["discovered_versions"]) | set(extract_versions(page_text[:50000]))
            )
            if pdf_info.get("parse_error"):
                parse_errors.append(f"{source}: {pdf_info['parse_error']}")
        elif suffix == ".pdf":
            pdf_info = extract_pdf(path, source, entries)
            pdf_infos[source] = pdf_info
            item["needs_visual_inspection"] = pdf_info["needs_visual_inspection"]
            item["pdf_page_count"] = len(pdf_info["pages"])
            item["pdf_parse_error"] = pdf_info["parse_error"]
            page_text = "\n".join(page["text"][:3000] for page in pdf_info["pages"])
            item["keywords"] = sorted(set(item["keywords"]) | set(keyword_hits(page_text)))
            item["discovered_versions"] = sorted(
                set(item["discovered_versions"]) | set(extract_versions(page_text[:50000]))
            )
            if pdf_info["parse_error"]:
                parse_errors.append(f"{source}: {pdf_info['parse_error']}")
        elif suffix == ".zip" and reusable and zip_cache.exists():
            zip_info = read_json(zip_cache, {})
            entries.extend(reusable_entries)
            zip_infos[source] = zip_info
            item["zip_member_count"] = len(zip_info.get("members", []))
            item["zip_parse_error"] = zip_info.get("error")
            item["discovered_versions"] = sorted(
                set(item["discovered_versions"]) | set(zip_info.get("versions", []))
            )
        elif suffix == ".zip":
            zip_info = inspect_zip(path, source, entries)
            zip_infos[source] = zip_info
            item["zip_member_count"] = len(zip_info["members"])
            item["zip_parse_error"] = zip_info["error"]
            item["discovered_versions"] = sorted(
                set(item["discovered_versions"]) | set(zip_info["versions"])
            )
        elif suffix in CODE_EXTENSIONS and reusable:
            entries.extend(reusable_entries)
        elif suffix in CODE_EXTENSIONS:
            text = read_small_text(path)
            if text:
                index_code_text(text, source, suffix, entries)
        elif suffix in TEXT_EXTENSIONS and reusable:
            entries.extend(reusable_entries)
        elif suffix in TEXT_EXTENSIONS:
            text = read_small_text(path)
            if text:
                entries.append({
                    "kind": "text", "path": source, "location": "",
                    "title": path.name, "text": clean_text(text)[:20000],
                    "source_type": metadata["file_category"],
                    "needs_visual_inspection": False,
                })
        manifest.append(item)
        if number % 100 == 0:
            print(f"Indexed {number}/{len(files)}", file=sys.stderr)

    link_errors = markdown_link_errors(files)
    write_json(MANIFEST_PATH, manifest)
    write_json(INDEX_PATH, {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": ".",
        "entries": entries,
    })
    expected_symbol_files = {
        f"{stable_id(entry['path'])}.json"
        for entry in entries
        if entry.get("kind") in {"code_symbol", "parse_error"}
        and entry.get("path")
    }
    for stale in (CACHE / "code_symbols").glob("*.json"):
        if stale.name not in expected_symbol_files:
            stale.unlink()
    write_json(CACHE / "manifests" / "markdown_link_errors.json", link_errors)
    REPORT_PATH.write_text(
        build_report(
            manifest, previous, pdf_infos, zip_infos, link_errors, parse_errors
        ),
        encoding="utf-8",
    )
    print(f"Indexed {len(manifest)} files; wrote {rel(REPORT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
