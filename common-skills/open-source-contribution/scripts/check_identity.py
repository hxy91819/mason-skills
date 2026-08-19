#!/usr/bin/env python3
"""Git commit identity checker for open-source publication.

Verifies that a repository's Git identity — repository-local config and every
author/committer in commit history — matches an approved personal GitHub
account, and flags company emails and corporate IDs used as author names.

Defaults encode Mason's durable open-source identity; override with flags for
other accounts.

Usage:
    python check_identity.py [-C REPO] [--name NAME] [--email EMAIL]
        [--github-login LOGIN] [--allowed-name NAME ...]
        [--prohibited-email PAT ...] [--prohibited-name NAME ...]
        [--all-refs] [--no-github] [--json]

Exit codes:
    0 - identity is clean (warnings may still be present)
    1 - at least one must-fix or mismatch finding
    2 - usage error or git failure
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

DEFAULT_NAME = "@hxy91819"
DEFAULT_EMAIL = "masonxhuang@proton.me"
DEFAULT_GITHUB_LOGIN = "hxy91819"
DEFAULT_ALLOWED_NAMES = ["Mason Huang"]
DEFAULT_PROHIBITED_EMAILS = ["tencent.com"]
DEFAULT_PROHIBITED_NAMES = ["masonxhuang"]

MAX_EXAMPLES = 5

OK = "ok"
MUST_FIX = "must-fix"
MISMATCH = "mismatch"
WARNING = "warning"


@dataclass
class ConfigLine:
    key: str
    status: str
    message: str


@dataclass
class HistoryLine:
    role: str
    name: str
    email: str
    commits: int
    examples: List[str]
    status: str
    message: str


def run_git(repo: str, *args: str) -> Tuple[int, str]:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def git_required(repo: str, *args: str) -> str:
    rc, out = run_git(repo, *args)
    if rc != 0:
        print(f"error: git {' '.join(args)} failed (exit {rc})", file=sys.stderr)
        sys.exit(2)
    return out


def config_get(repo: str, scope: str, key: str) -> Optional[str]:
    args = ["config"]
    if scope:
        args.append(scope)
    args += ["--get", key]
    rc, out = run_git(repo, *args)
    if rc != 0:
        return None
    return out.strip()


def name_prohibited(name: str, patterns: Sequence[str]) -> bool:
    return name.casefold() in {p.casefold() for p in patterns}


def email_prohibited(email: str, patterns: Sequence[str]) -> bool:
    folded = email.casefold()
    return any(p.casefold() in folded for p in patterns)


def check_config(args: argparse.Namespace) -> List[ConfigLine]:
    lines: List[ConfigLine] = []
    for key, approved, prohibited in (
        ("user.name", args.name, args.prohibited_names),
        ("user.email", args.email, args.prohibited_emails),
    ):
        local = config_get(args.repo, "--local", key)
        effective = config_get(args.repo, "", key)
        if local is None:
            if effective is None:
                lines.append(ConfigLine(key, MISMATCH,
                    f"{key} is not configured anywhere; commits would use an unknown identity"))
            elif name_prohibited(effective, prohibited) or email_prohibited(effective, prohibited):
                lines.append(ConfigLine(key, MUST_FIX,
                    f"{key} is not set locally; effective value '{effective}' is a company identity"))
            elif effective == approved:
                lines.append(ConfigLine(key, WARNING,
                    f"{key} is not set locally; falls back to approved global value "
                    f"'{effective}' — set it with --local"))
            else:
                lines.append(ConfigLine(key, MISMATCH,
                    f"{key} is not set locally; effective value '{effective}' is not "
                    f"the approved identity"))
        elif name_prohibited(local, prohibited) or email_prohibited(local, prohibited):
            lines.append(ConfigLine(key, MUST_FIX,
                f"{key} = '{local}' (local) is a company identity"))
        elif local != approved:
            lines.append(ConfigLine(key, MISMATCH,
                f"{key} = '{local}' (local) is not the approved identity '{approved}'"))
        else:
            lines.append(ConfigLine(key, OK, f"{key} = '{local}' (local)"))
    use_config_only = config_get(args.repo, "--local", "user.useConfigOnly")
    if use_config_only == "true":
        lines.append(ConfigLine("user.useConfigOnly", OK,
                                "user.useConfigOnly = true (local)"))
    else:
        lines.append(ConfigLine("user.useConfigOnly", WARNING,
            "user.useConfigOnly is not true; set it to prevent fallback to a global identity"))
    return lines


def check_history(args: argparse.Namespace) -> List[HistoryLine]:
    ref_args = ["--all"] if args.all_refs else ["--branches", "--remotes"]
    out = git_required(args.repo, "log", *ref_args,
                       "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%s%x00")
    fields = out.rstrip("\n").split("\x00")
    if fields and fields[-1] == "":
        fields.pop()
    if not fields:
        return []
    if len(fields) % 6 != 0:
        print("error: unexpected git log output", file=sys.stderr)
        sys.exit(2)
    identities = {}
    for i in range(0, len(fields), 6):
        sha, an, ae, cn, ce, _subject = fields[i:i + 6]
        for role, name, email in (("author", an, ae), ("committer", cn, ce)):
            entry = identities.setdefault((role, name, email), {"commits": 0, "examples": []})
            entry["commits"] += 1
            if len(entry["examples"]) < MAX_EXAMPLES:
                entry["examples"].append(sha)
    lines: List[HistoryLine] = []
    for (role, name, email), info in sorted(identities.items()):
        status, message = classify_identity(role, name, email, args)
        lines.append(HistoryLine(role, name, email, info["commits"], info["examples"],
                                 status, message))
    return lines


def classify_identity(role: str, name: str, email: str,
                      args: argparse.Namespace) -> Tuple[str, str]:
    if email == "noreply@github.com":
        return OK, "GitHub web-generated committer"
    if name_prohibited(name, args.prohibited_names):
        return MUST_FIX, f"{role} name '{name}' is a corporate ID"
    if email_prohibited(email, args.prohibited_emails):
        return MUST_FIX, f"{role} email '{email}' is a company address"
    name_ok = name == args.name or name in args.allowed_names
    email_ok = email == args.email or email.endswith("@users.noreply.github.com")
    if name_ok and email_ok:
        return OK, "approved identity"
    problems = []
    if not name_ok:
        problems.append(f"name '{name}' is not the approved identity")
    if not email_ok:
        problems.append(f"email '{email}' is not the approved address")
    return MISMATCH, f"{role} " + "; ".join(problems)


def check_github(args: argparse.Namespace) -> Tuple[str, str]:
    if args.no_github:
        return OK, "GitHub cross-check skipped (--no-github)"
    try:
        proc = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                              capture_output=True, text=True)
    except FileNotFoundError:
        return OK, "gh unavailable; GitHub account cross-check skipped"
    if proc.returncode != 0:
        return OK, "gh unavailable or unauthenticated; GitHub account cross-check skipped"
    login = proc.stdout.strip()
    if login != args.github_login:
        return MISMATCH, f"gh reports login '{login}', expected '{args.github_login}'"
    return OK, f"gh login '{login}' matches expected account"


def build_findings(config_lines: List[ConfigLine], history_lines: List[HistoryLine],
                   gh_status: str, gh_message: str) -> List[dict]:
    findings = []
    for line in config_lines:
        if line.status != OK:
            findings.append({"severity": line.status, "section": "config",
                             "key": line.key, "message": line.message})
    for line in history_lines:
        if line.status != OK:
            findings.append({"severity": line.status, "section": "history",
                             "role": line.role, "name": line.name, "email": line.email,
                             "commits": line.commits, "examples": line.examples,
                             "message": line.message})
    if gh_status != OK:
        findings.append({"severity": gh_status, "section": "github", "message": gh_message})
    return findings


def print_human(config_lines: List[ConfigLine], history_lines: List[HistoryLine],
                gh_status: str, gh_message: str) -> None:
    print("CONFIG")
    for line in config_lines:
        print(f"  [{line.status}] {line.message}")
    print("HISTORY")
    if not history_lines:
        print("  [ok] no commits")
    for line in history_lines:
        detail = f" — {line.commits} commits, e.g. {' '.join(line.examples)}"
        message = f" ({line.message})" if line.status != OK else ""
        print(f"  [{line.status}] {line.role} {line.name} <{line.email}>{detail}{message}")
    print("GITHUB")
    print(f"  [{gh_status}] {gh_message}")


def print_json(findings: List[dict], gh_status: str, gh_message: str,
               args: argparse.Namespace) -> None:
    counts = {MUST_FIX: 0, MISMATCH: 0, WARNING: 0}
    for finding in findings:
        counts[finding["severity"]] += 1
    clean = counts[MUST_FIX] == 0 and counts[MISMATCH] == 0
    payload = {
        "findings": findings,
        "github": {"login": args.github_login, "status": gh_status, "message": gh_message},
        "summary": {"must_fix": counts[MUST_FIX], "mismatch": counts[MISMATCH],
                    "warning": counts[WARNING], "clean": clean},
    }
    print(json.dumps(payload, indent=2))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a repository's Git identity against an approved GitHub account.")
    parser.add_argument("-C", "--repo", default=".",
                        help="repository path (default: current directory)")
    parser.add_argument("--name", default=DEFAULT_NAME,
                        help=f"approved author name (default: {DEFAULT_NAME})")
    parser.add_argument("--email", default=DEFAULT_EMAIL,
                        help=f"approved email (default: {DEFAULT_EMAIL})")
    parser.add_argument("--github-login", default=DEFAULT_GITHUB_LOGIN,
                        help=f"expected GitHub login (default: {DEFAULT_GITHUB_LOGIN})")
    parser.add_argument("--allowed-name", action="append", dest="allowed_names",
                        default=list(DEFAULT_ALLOWED_NAMES),
                        help="additional approved display name (repeatable)")
    parser.add_argument("--prohibited-email", action="append", dest="prohibited_emails",
                        default=list(DEFAULT_PROHIBITED_EMAILS),
                        help="email substring treated as a company address (repeatable)")
    parser.add_argument("--prohibited-name", action="append", dest="prohibited_names",
                        default=list(DEFAULT_PROHIBITED_NAMES),
                        help="name treated as a corporate ID (repeatable)")
    parser.add_argument("--all-refs", action="store_true",
                        help="scan every ref including local-only bookkeeping refs")
    parser.add_argument("--no-github", action="store_true",
                        help="skip the gh account cross-check")
    parser.add_argument("--json", action="store_true",
                        help="emit a machine-readable JSON report")
    args = parser.parse_args(argv)

    config_lines = check_config(args)
    history_lines = check_history(args)
    gh_status, gh_message = check_github(args)
    findings = build_findings(config_lines, history_lines, gh_status, gh_message)

    if args.json:
        print_json(findings, gh_status, gh_message, args)
    else:
        print_human(config_lines, history_lines, gh_status, gh_message)
        counts = {MUST_FIX: 0, MISMATCH: 0, WARNING: 0}
        for finding in findings:
            counts[finding["severity"]] += 1
        clean = counts[MUST_FIX] == 0 and counts[MISMATCH] == 0
        print("SUMMARY")
        print(f"  must-fix: {counts[MUST_FIX]}, mismatch: {counts[MISMATCH]}, "
              f"warning: {counts[WARNING]}")
        print(f"  {'CLEAN' if clean else 'NOT CLEAN'}")

    clean = not any(f["severity"] in (MUST_FIX, MISMATCH) for f in findings)
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
