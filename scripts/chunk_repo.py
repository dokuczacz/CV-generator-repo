"""Chunk repository text files into Markdown bundles for Custom GPT ingestion.

Usage (from repo root):
    python scripts/chunk_repo.py --root . --output "C:\\Users\\Mariusz\\OneDrive\\Pulpit\\Architecture-Analysis\\cv-generator-handoff" --chunk-bytes 8388608 --with-index

Outputs:
- chunk_###.md: concatenated text files with delimiters.
- manifest.json: machine-readable map of chunks and file offsets.
- index.md (optional): human-readable mapping of chunks to files.

The script skips binary files and common build/output directories.
Always overwrites existing output files in the target directory without prompting.
Adds priority ordering for chunks (P0, P1, P2) and index entries with short descriptions.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from pathlib import Path
from typing import Iterable, List, Dict, Any

# Default configuration
INCLUDE_EXTS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".py",
    ".css",
    ".scss",
    ".html",
    ".htm",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".ps1",
    ".psm1",
    ".sh",
    ".mjs",
    ".cjs",
    ".lock",
}

ALWAYS_INCLUDE_FILENAMES = {
    "LICENSE",
    "Dockerfile",
    "Makefile",
    "Procfile",
    "README",
}

EXCLUDE_DIR_NAMES = {
    ".git",
    ".github",
    ".next",
    ".vscode",
    "node_modules",
    "artifacts",
    "playwright-report",
    "test-results",
    "__pycache__",
    "__blobstorage__",
    "__queuestorage__",
    "__azurite_db_blob__",
    "__azurite_db_blob_extent__",
    "__azurite_db_queue__",
    "__azurite_db_queue_extent__",
    "__azurite_db_table__",
    ".venv",
    "env",
    "venv",
}

EXCLUDE_FILE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".xz",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".db",
    ".mp4",
    ".webm",
    ".ico",
}

EXCLUDE_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

DELIMITER_TEMPLATE = "\n\n===== FILE: {rel_path} =====\n"

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}

PRIORITY_RULES = [
    ("function_app.py", "P0"),
    ("src/", "P0"),
    ("SYSTEM_PROMPT.md", "P0"),
    ("PROMPT_INSTRUCTIONS.md", "P0"),
    ("TOOLS_CONFIG.md", "P0"),
    ("ORCHESTRATION.md", "P0"),
    ("STRUCTURED_OUTPUT", "P0"),
    ("ui/app/api", "P0"),
    ("ui/lib/prompts", "P0"),
    ("ui/lib/tools", "P0"),
    ("ui/app/page.tsx", "P1"),
    ("ui/app/layout.tsx", "P1"),
    ("ui/app", "P1"),
    ("templates/", "P1"),
    ("schemas/", "P1"),
    ("tests/", "P1"),
    ("playwright.config.ts", "P1"),
]

DESCRIPTION_RULES = [
    ("function_app.py", "Azure Functions router"),
    ("src/validate-cv", "Validate CV structure function (Python)"),
    ("src/generate-cv-action", "Generate 2-page PDF function (Python)"),
    ("src/extract-photo", "Extract photo from DOCX (Python)"),
    ("SYSTEM_PROMPT.md", "System prompt reference"),
    ("PROMPT_INSTRUCTIONS.md", "Prompt workflow guide"),
    ("TOOLS_CONFIG.md", "Tool schema definitions"),
    ("ORCHESTRATION.md", "Workflow orchestration notes"),
    ("STRUCTURED_OUTPUT", "Structured output schema/prompt"),
    ("AGENTS.md", "Agent operating rules"),
    ("ui/app/api/process-cv", "Next.js API orchestrator"),
    ("ui/app/page.tsx", "Chat UI entry"),
    ("ui/lib/prompts.ts", "Prompt templates"),
    ("ui/lib/tools.ts", "Tool definitions"),
    ("templates/html", "CV HTML templates"),
    ("templates/", "CV template assets"),
    ("schemas/", "Schema definitions"),
    ("tests/", "Playwright tests"),
    ("requirements.txt", "Python dependencies"),
    ("ui/package.json", "UI dependencies"),
    ("package.json", "Root dependencies"),
    ("playwright.config.ts", "Playwright configuration"),
]


def classify_priority(rel_path: str) -> str:
    lowered = rel_path.lower()
    for needle, priority in PRIORITY_RULES:
        if needle.lower() in lowered:
            return priority
    return "P2"


def describe_path(rel_path: str) -> str:
    lowered = rel_path.lower()
    for needle, desc in DESCRIPTION_RULES:
        if needle.lower() in lowered:
            return desc
    parent = rel_path.rsplit("/", 1)[0] if "/" in rel_path else "root"
    return f"File under {parent}"


def is_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data:
        return True
    sample = data[:4096]
    text_chars = bytes({7, 8, 9, 10, 12, 13, 27} | set(range(32, 127)))
    nontext = sum(1 for b in sample if b not in text_chars)
    return (nontext / max(1, len(sample))) > 0.30


def should_include(file_path: Path) -> bool:
    name = file_path.name
    suffix = file_path.suffix.lower()
    if name in EXCLUDE_FILE_NAMES:
        return False
    if suffix in EXCLUDE_FILE_EXTS:
        return False
    if suffix in INCLUDE_EXTS:
        return True
    if name in ALWAYS_INCLUDE_FILENAMES:
        return True
    return False


def iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
        for filename in filenames:
            yield Path(dirpath) / filename


def load_text(file_path: Path) -> bytes | None:
    try:
        data = file_path.read_bytes()
    except Exception:
        return None
    if is_binary(data):
        return None
    return data


def chunk_files(file_entries: List[Dict[str, Any]], root: Path, output: Path, chunk_bytes: int) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    # Derive repo key for prefixed filenames
    repo_key = Path(root).name.replace(' ', '_')
    # Clean old outputs (always overwrite)
    cleaned = 0
    for old in output.glob(f"{repo_key}_chunk_*.md"):
        old.unlink()
        cleaned += 1
    # remove prefixed manifest/index as well
    for name in (f"{repo_key}_manifest.json", f"{repo_key}_index.md"):
        existing = output / name
        if existing.exists():
            existing.unlink()
            cleaned += 1
    if cleaned > 0:
        print(f"Cleaned {cleaned} old files from {output}")

    chunks: List[Dict[str, Any]] = []
    current = bytearray()
    current_files: List[Dict[str, Any]] = []
    chunk_idx = 1

    def flush_chunk() -> None:
        nonlocal chunk_idx, current, current_files
        if not current:
            return
        # Prefix chunk filenames with repo key to avoid collisions when merging outputs
        repo_key = Path(root).name.replace(' ', '_')
        chunk_name = f"{repo_key}_chunk_{chunk_idx:03d}.md"
        chunk_path = output / chunk_name
        chunk_path.write_bytes(current)
        chunks.append({
            "chunk_file": chunk_name,
            "size_bytes": len(current),
            "files": current_files,
        })
        chunk_idx += 1
        current = bytearray()
        current_files = []

    def add_entries(entries: List[Dict[str, Any]]) -> None:
        nonlocal current, current_files
        for entry in entries:
            rel_path = entry["rel_path"]
            data = entry["data"]
            priority = entry["priority"]
            description = entry["description"]
            header = DELIMITER_TEMPLATE.format(rel_path=rel_path).encode("utf-8", "replace")

            # If file is larger than chunk budget, split it across multiple chunks.
            available_payload = max(1, chunk_bytes - len(header))
            parts = [data[i:i + available_payload] for i in range(0, len(data), available_payload)]

            for part_index, part in enumerate(parts):
                entry_label = rel_path if len(parts) == 1 else f"{rel_path} (part {part_index + 1}/{len(parts)})"
                entry_header = DELIMITER_TEMPLATE.format(rel_path=entry_label).encode("utf-8", "replace")
                entry_size = len(entry_header) + len(part)

                if current and (len(current) + entry_size) > chunk_bytes:
                    flush_chunk()

                # Edge case: single part larger than chunk budget (should not happen after split)
                if entry_size > chunk_bytes:
                    raise ValueError(f"Entry size still exceeds chunk budget for {entry_label}")

                start = len(current)
                current.extend(entry_header)
                current.extend(part)
                end = len(current)
                current_files.append({
                    "path": rel_path,
                    "label": entry_label,
                    "start": start,
                    "end": end,
                    "size_bytes": end - start,
                    "priority": priority,
                    "description": description,
                })

    high_priority = [e for e in file_entries if e["priority"] in {"P0", "P1"}]
    low_priority = [e for e in file_entries if e["priority"] not in {"P0", "P1"}]

    add_entries(high_priority)
    flush_chunk()
    add_entries(low_priority)

    flush_chunk()

    manifest = {
        "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
        "root": str(root),
        "output": str(output),
        "chunk_bytes": chunk_bytes,
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    return manifest


def write_manifest(manifest: Dict[str, Any], output: Path) -> None:
    repo_key = Path(manifest.get("root", "")).name.replace(' ', '_')
    (output / f"{repo_key}_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_index(manifest: Dict[str, Any], output: Path) -> None:
    lines: List[str] = []
    lines.append("# Chunk Index")
    lines.append(f"Generated: {manifest['generated_at']}")
    lines.append(f"Chunks: {manifest['chunk_count']} (max {manifest['chunk_bytes']} bytes each)")
    lines.append("")
    for chunk in manifest.get("chunks", []):
        lines.append(f"## {chunk['chunk_file']} (size {chunk['size_bytes']} bytes, files {len(chunk['files'])})")
        for f in chunk.get("files", []):
            lines.append(
                f"- [{f['priority']}] {f['label']} ({f['size_bytes']} bytes) - {f['description']}"
            )
        lines.append("")
    repo_key = Path(manifest.get("root", "")).name.replace(' ', '_')
    (output / f"{repo_key}_index.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunk repository text files into Markdown bundles.")
    parser.add_argument("--root", default=".", help="Root directory to scan")
    parser.add_argument("--output", required=True, help="Output directory for chunks")
    parser.add_argument("--chunk-bytes", type=int, default=8 * 1024 * 1024, help="Max bytes per chunk")
    parser.add_argument("--with-index", action="store_true", help="Write index.md in addition to manifest.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    raw_files = [p for p in iter_files(root) if should_include(p)]
    file_entries: List[Dict[str, Any]] = []
    for file_path in raw_files:
        data = load_text(file_path)
        if data is None:
            continue
        rel_path = file_path.relative_to(root).as_posix()
        priority = classify_priority(rel_path)
        description = describe_path(rel_path)
        file_entries.append({
            "path": file_path,
            "rel_path": rel_path,
            "priority": priority,
            "description": description,
            "data": data,
        })

    file_entries.sort(key=lambda e: (PRIORITY_ORDER.get(e["priority"], 3), e["rel_path"]))

    manifest = chunk_files(file_entries, root, output, args.chunk_bytes)
    write_manifest(manifest, output)
    if args.with_index:
        write_index(manifest, output)

    print(
        f"Wrote {manifest['chunk_count']} chunks to {output} | "
        f"chunk_bytes={args.chunk_bytes} | files={sum(len(c['files']) for c in manifest['chunks'])}"
    )


if __name__ == "__main__":
    main()
