#!/usr/bin/env python3
"""
CritLayer — Common utility tools shared across all task types.

Adapted from the firmware-analyzer reference: run_command, read_file,
write_file, list_directory.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from agents import function_tool

from .registry import register_tool

logger = logging.getLogger(__name__)


@register_tool
@function_tool
def run_command(command: str, timeout: int = 120) -> str:
    """Run a shell command and return its output.

    Args:
        command: Shell command to execute.
        timeout: Timeout in seconds (default 120).
    """
    # Block obviously destructive commands
    blocked = ["rm -rf /", "mkfs", ":(){:|:&};:"]
    for pat in blocked:
        if pat in command:
            return "Error: blocked potentially dangerous command"

    # Anti-cheat: block commands that try to access evaluation / task
    # definition files (expected answers, evaluation code, etc.)
    import re as _re
    _blocked_cmd_patterns = [
        r"/code/tasks/definitions",
        r"/code/evaluation",
        r"/code/run_experiments",
        r"tasks/definitions",
        r"_task_sanitised\.yaml",
        r"evaluation/evaluator",
        r"evaluation/metrics",
        r"\.yaml\b.*(?:evaluation|expected|grading)",
    ]
    for pat in _blocked_cmd_patterns:
        if _re.search(pat, command, _re.IGNORECASE):
            return "Error: access denied — cannot access evaluation/task definition files"

    # Determine working directory:
    # In Docker container → /work  (created by entrypoint / Dockerfile)
    # Fallback chain for local dev: /tmp/critbench_work → cwd
    work_dir = os.environ.get("CRITBENCH_WORKDIR")
    if not work_dir:
        for candidate in ["/work", "/tmp/critbench_work"]:
            try:
                os.makedirs(candidate, exist_ok=True)
                work_dir = candidate
                break
            except OSError:
                continue
        if not work_dir:
            work_dir = os.getcwd()

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            cwd=work_dir,
        )
        output = f"Exit code: {result.returncode}\n\n"
        output += "=== STDOUT ===\n" + result.stdout + "\n\n"
        output += "=== STDERR ===\n" + result.stderr
        if len(output) > 50_000:
            output = output[:50_000] + "\n... [truncated]"
        return output
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


# Paths the agent is NOT allowed to read (contain evaluation answers)
_BLOCKED_READ_PATTERNS = [
    "/code/tasks/definitions/",
    "/tasks/definitions/",
    "_task_sanitised.yaml",   # prevent reading sanitised copy to discover structure
]


@register_tool
@function_tool
def read_file(file_path: str, max_lines: int = 500) -> str:
    """Read the contents of a file.

    Args:
        file_path: Absolute path to the file.
        max_lines: Maximum number of lines to return (default 500).
    """
    # Anti-cheat: block access to task definitions (contain expected answers)
    resolved = str(Path(file_path).resolve())
    for pattern in _BLOCKED_READ_PATTERNS:
        if pattern in resolved or pattern in file_path:
            return f"Error: access denied — task definition files are not readable"

    p = Path(file_path)
    if not p.exists():
        return f"Error: File not found: {file_path}"
    try:
        content = p.read_text(errors="replace")
        lines = content.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n\n... [{len(lines) - max_lines} more lines truncated]"
        return content
    except Exception as exc:
        return f"Error reading file: {exc}"


@register_tool
@function_tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file.  Only /output and /tmp are writable.

    Args:
        file_path: Path where the file will be created.
        content: Text content to write.
    """
    p = Path(file_path)
    if not (str(p).startswith("/output") or str(p).startswith("/tmp")):
        return "Error: can only write to /output or /tmp directories"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"Wrote {len(content)} bytes to {file_path}"
    except Exception as exc:
        return f"Error writing file: {exc}"


@register_tool
@function_tool
def list_directory(path: str, recursive: bool = False) -> str:
    """List directory contents.

    Args:
        path: Directory path to list.
        recursive: If true, list recursively (default false).
    """
    # Anti-cheat: block listing evaluation / task definition dirs
    resolved = str(Path(path).resolve())
    for pattern in _BLOCKED_READ_PATTERNS:
        if pattern in resolved or pattern in path:
            return "Error: access denied — cannot list evaluation/task definition directories"
    d = Path(path)
    if not d.exists():
        return f"Error: path not found: {path}"
    if not d.is_dir():
        return f"Error: not a directory: {path}"
    try:
        items = list(d.rglob("*"))[:500] if recursive else list(d.iterdir())
        lines = []
        for item in sorted(items):
            rel = item.relative_to(d) if recursive else item.name
            if item.is_symlink():
                target = os.readlink(item)
                lines.append(f"[LINK] {rel} -> {target}")
            elif item.is_dir():
                lines.append(f"[DIR]  {rel}/")
            else:
                try:
                    sz = item.stat().st_size
                    lines.append(f"[FILE] {rel} ({sz} bytes)")
                except Exception:
                    lines.append(f"[FILE] {rel}")
        result = f"Contents of {path}:\n\n" + "\n".join(lines)
        if len(items) >= 500:
            result += "\n\n... [truncated at 500 items]"
        return result
    except Exception as exc:
        return f"Error: {exc}"
