#!/usr/bin/env python3
"""Fail if the repository contains identifiers that must never be published.

Two layers:
1. generic patterns (GUIDs, private IPs, real storage/DevOps hosts, e-mails,
   token-like strings, passwords in connection strings);
2. an optional local list of forbidden terms in `.sensitive-terms.local`
   (one term per line, case-insensitive). The file is gitignored on purpose:
   the list itself would leak the names it protects.

File names and paths are checked too. Exit code 1 when anything is found.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "data", "__pycache__", ".pytest_cache", ".ruff_cache"}
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".sql", ".json", ".toml", ".txt", ".tmdl", ".pbism", ".ps1", ".sh", ".cfg", ""}

PATTERNS = {
    "guid": re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    "private_ip": re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    "storage_account": re.compile(r"\b(?!onelake\b)[a-z0-9]{3,24}\.(?:dfs|blob)\.core\.windows\.net"),
    "devops_org": re.compile(r"(?<![\w.])dev\.azure\.com/(?!<)[A-Za-z0-9_-]+"),
    "tenant": re.compile(r"[A-Za-z0-9-]+\.onmicrosoft\.com"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com|users\.noreply\.github\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "token_like": re.compile(r"\b[A-Za-z0-9]{48,}\b"),
    "password": re.compile(r"(?i)\b(?:pwd|password)\s*[=:]\s*(?![<.\s$'\"]|\.\.\.)[^;\s]{3,}"),
}


def tracked_files() -> list[Path]:
    """Files git would publish (tracked + untracked not ignored); falls back to a walk."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        files = [ROOT / line for line in out.splitlines() if line]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    return [p for p in ROOT.rglob("*") if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(ROOT).parts)]


def local_terms() -> list[str]:
    path = ROOT / ".sensitive-terms.local"
    if not path.exists():
        return []
    return [line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def main() -> int:
    terms = local_terms()
    findings: list[str] = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "scripts/check_sensitive.py" or not path.exists():
            continue
        for term in terms:
            if term in rel.lower():
                findings.append(f"{rel}: nome de arquivo contem termo proibido")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            for term in terms:
                if term in lowered:
                    findings.append(f"{rel}:{number}: termo proibido")
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{rel}:{number}: {name}")

    mode = f"padroes genericos + {len(terms)} termo(s) locais" if terms else "padroes genericos (sem .sensitive-terms.local)"
    if findings:
        print(f"check_sensitive: {len(findings)} ocorrencia(s) [{mode}]")
        for finding in findings:
            print("  " + finding)
        return 1
    print(f"check_sensitive: ok [{mode}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
