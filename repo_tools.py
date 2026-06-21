#!/usr/bin/env python3
"""
repo_tools.py — Read-only file-tree access for the disprover agent.

Gives the LLM tool-calling access to list and read files in the target
repo, scoped to a single root directory, so it can pull exact function
bodies itself instead of you pasting arithmetic_notes.txt by hand.

This is READ-ONLY by design. No write_file, no run_command, no forge
execution. That's a deliberate boundary, not a missing feature — an
agent that can autonomously write+run Foundry tests in a loop will burn
real API spend and compute chasing hypotheses a 2-minute manual check
would kill, which is the exact failure mode the scope gate exists to
prevent. If you want an execution loop later, build it as an explicit,
separate, opt-in script — not bolted onto this one.

Path containment: every path is resolved and checked against the repo
root before any read happens. Symlinks that escape the root are refused.
"""

import os
import json

MAX_FILE_BYTES = 200_000  # refuse to dump huge files into context wholesale
MAX_LIST_ENTRIES = 500


def _resolve_safe(repo_root: str, rel_path: str) -> str | None:
    """Resolve rel_path against repo_root and verify the real path stays
    inside repo_root. Returns the absolute path, or None if it escapes."""
    root_real = os.path.realpath(repo_root)
    candidate = os.path.realpath(os.path.join(repo_root, rel_path.lstrip("/")))
    if not (candidate == root_real or candidate.startswith(root_real + os.sep)):
        return None
    return candidate


def list_files(repo_root: str, rel_dir: str = ".", extensions: list[str] | None = None) -> dict:
    """List files under rel_dir (recursively), optionally filtered by extension.
    Returns relative paths so the model can request specific ones next."""
    safe_dir = _resolve_safe(repo_root, rel_dir)
    if safe_dir is None:
        return {"error": f"path escapes repo root: {rel_dir}"}
    if not os.path.isdir(safe_dir):
        return {"error": f"not a directory: {rel_dir}"}

    results = []
    skip_dirs = {".git", "node_modules", "lib", "out", "cache", "artifacts", "broadcast"}
    for dirpath, dirnames, filenames in os.walk(safe_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for fname in filenames:
            if extensions and not any(fname.endswith(ext) for ext in extensions):
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, repo_root)
            results.append(rel)
            if len(results) >= MAX_LIST_ENTRIES:
                return {"files": results, "truncated": True}
    return {"files": results, "truncated": False}


def read_file(repo_root: str, rel_path: str) -> dict:
    """Read a single file's full contents. Refuses files over MAX_FILE_BYTES
    so a single tool call can't blow the context budget — ask for a
    narrower file or a specific range instead."""
    safe_path = _resolve_safe(repo_root, rel_path)
    if safe_path is None:
        return {"error": f"path escapes repo root: {rel_path}"}
    if not os.path.isfile(safe_path):
        return {"error": f"not a file: {rel_path}"}
    size = os.path.getsize(safe_path)
    if size > MAX_FILE_BYTES:
        return {"error": f"file too large ({size} bytes > {MAX_FILE_BYTES} limit): {rel_path}. Consider grep_files instead."}
    with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"path": rel_path, "content": content, "bytes": size}


def grep_files(repo_root: str, pattern: str, rel_dir: str = ".", extensions: list[str] | None = None, max_matches: int = 100) -> dict:
    """Simple substring grep across files under rel_dir. Returns
    file:line:text triples. Useful for finding all callers of a function
    without reading every file in full."""
    safe_dir = _resolve_safe(repo_root, rel_dir)
    if safe_dir is None:
        return {"error": f"path escapes repo root: {rel_dir}"}

    matches = []
    skip_dirs = {".git", "node_modules", "lib", "out", "cache", "artifacts", "broadcast"}
    for dirpath, dirnames, filenames in os.walk(safe_dir):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for fname in filenames:
            if extensions and not any(fname.endswith(ext) for ext in extensions):
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, repo_root)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, start=1):
                        if pattern in line:
                            matches.append({"file": rel, "line": i, "text": line.strip()})
                            if len(matches) >= max_matches:
                                return {"matches": matches, "truncated": True}
            except (OSError, UnicodeDecodeError):
                continue
    return {"matches": matches, "truncated": False}


# --- Tool schema for OpenAI-compatible function calling (DeepSeek uses this format) ---

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in the target repo under a directory, optionally filtered by extension (e.g. ['.sol']). Use this first to find what's available before reading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rel_dir": {"type": "string", "description": "Directory relative to repo root, default '.'"},
                    "extensions": {"type": "array", "items": {"type": "string"}, "description": "Optional file extension filter, e.g. ['.sol']"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of one file by its path relative to repo root. Refuses files over 200KB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rel_path": {"type": "string", "description": "File path relative to repo root, e.g. 'src/end.sol'"},
                },
                "required": ["rel_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "Search for a substring across files under a directory. Returns file:line:text matches. Use to find all call sites of a function/variable without reading every file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Substring to search for"},
                    "rel_dir": {"type": "string", "description": "Directory relative to repo root, default '.'"},
                    "extensions": {"type": "array", "items": {"type": "string"}, "description": "Optional file extension filter"},
                },
                "required": ["pattern"],
            },
        },
    },
]


def dispatch_tool_call(repo_root: str, name: str, arguments: dict) -> dict:
    """Routes a tool call by name to the corresponding read-only function."""
    if name == "list_files":
        return list_files(repo_root, arguments.get("rel_dir", "."), arguments.get("extensions"))
    elif name == "read_file":
        return read_file(repo_root, arguments["rel_path"])
    elif name == "grep_files":
        return grep_files(repo_root, arguments["pattern"], arguments.get("rel_dir", "."), arguments.get("extensions"), arguments.get("max_matches", 100))
    else:
        return {"error": f"unknown tool: {name}"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python repo_tools.py <repo_root> [list|read|grep] [args...]")
        sys.exit(1)
    root = sys.argv[1]
    if len(sys.argv) >= 3 and sys.argv[2] == "list":
        print(json.dumps(list_files(root, sys.argv[3] if len(sys.argv) > 3 else "."), indent=2))
    elif len(sys.argv) >= 4 and sys.argv[2] == "read":
        print(json.dumps(read_file(root, sys.argv[3]), indent=2))
    elif len(sys.argv) >= 4 and sys.argv[2] == "grep":
        print(json.dumps(grep_files(root, sys.argv[3]), indent=2))
    else:
        print(json.dumps(list_files(root), indent=2))
