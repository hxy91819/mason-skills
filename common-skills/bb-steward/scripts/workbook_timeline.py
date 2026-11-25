"""Workbook timestamps and reverse-chronological ordering; touches only route checkboxes and user to-do tables.

Generated text follows the language of what it extends: a route section headed with a legacy Chinese name gets
Chinese completion suffixes, a to-do table with Chinese headers gets Chinese columns and values. An existing
completion suffix keeps its own form.
"""
from datetime import datetime
import re
from zoneinfo import ZoneInfo

import steward_vocab as vocab

SGT = ZoneInfo("Asia/Singapore")
CREATED = re.compile(r" <!-- steward-created: (.*?) -->")
COMPLETED = vocab.COMPLETED_RE
CHECKBOX = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+)$")
HISTORICAL_WARNING = ": historical completion time unverified"
UNVERIFIED_VALUES = set(vocab.UNVERIFIED.values())


def date_key(value, now):
    value = value.strip().removesuffix(" SGT")
    if re.fullmatch(r"\d{2}-\d{2}", value):
        value = f"{now.year}-{value}"
    try:
        return datetime.fromisoformat(value).replace(tzinfo=SGT).timestamp()
    except ValueError:
        return float("-inf")


def completed_value(match):
    """(value, language) of a completion suffix match."""
    return (match.group("zh"), "zh") if match.group("zh") is not None else (match.group("en"), "en")


def route_identity(line):
    body = CHECKBOX.match(line).group(2)
    body = CREATED.sub("", COMPLETED.sub("", body))
    # Stage number first; otherwise the title before the colon, so results and state can change freely.
    stage = re.match(r"((?:阶段|階段|发布|發佈|Stage)\s*\d+)\b", body, re.I)
    return stage.group(1) if stage else re.split(r"[:：←]", body, maxsplit=1)[0].strip()


def cells(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def sections(text):
    """[(canonical section name, heading as written, lines)]."""
    result = []
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            result.append((vocab.section_name(name), name, [line]))
        elif result:
            result[-1][2].append(line)
        else:
            result.append(("", "", [line]))
    return result


def format_timeline(text, baseline=None, now=None):
    """Times are when the script observed a state change; old completed rows never get an invented time."""
    now = now or datetime.now(SGT)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(SGT)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S SGT")
    old_sections = {name: lines for name, _, lines in sections(baseline or "")}
    warnings = []
    output = []
    input_lines = 0
    for name, heading, lines in sections(text):
        first_lineno = input_lines + 1
        input_lines += len(lines)
        old_lines = old_sections.get(name, [])
        if name == vocab.ROUTE:
            lang = "zh" if heading in vocab.SECTION_ALIASES else "en"
            old = {route_identity(line): line for line in old_lines if CHECKBOX.match(line)}
            blocks, prefix = [], []
            for line in lines:
                if CHECKBOX.match(line):
                    blocks.append([line])
                elif blocks:
                    blocks[-1].append(line)
                else:
                    prefix.append(line)
            dated = []
            for block in blocks:
                line = block[0]
                prior = old.get(route_identity(line), "")
                created = CREATED.search(line) or CREATED.search(prior)
                created = created.group(1) if created else stamp
                done = CHECKBOX.match(line).group(1).lower() == "x"
                was_done = bool(prior and CHECKBOX.match(prior).group(1).lower() == "x")
                found = COMPLETED.search(line) or (COMPLETED.search(prior) if was_done else None)
                completed, suffix_lang = completed_value(found) if found else (None, lang)
                if done and not completed:
                    completed = stamp if baseline is not None and not was_done else vocab.UNVERIFIED[suffix_lang]
                if done and completed in UNVERIFIED_VALUES:
                    warnings.append(f"{route_identity(line)}{HISTORICAL_WARNING}")
                line = CREATED.sub("", COMPLETED.sub("", line))
                if done:
                    line += vocab.completed_suffix(completed, suffix_lang)
                line += f" <!-- steward-created: {created} -->"
                block[0] = line
                # Unknown historical completion times sort last; equal times keep their order.
                dated.append((date_key(completed if done else created, now), block))
            lines = prefix + [line for _, block in sorted(dated, key=lambda x: x[0], reverse=True) for line in block]
        elif name == vocab.TODOS:
            def tables(content):
                result = []
                for i, line in enumerate(content):
                    row = cells(line) if line.strip().startswith("|") else []
                    keys = [vocab.todo_column(c) for c in row]
                    if "Status" in keys and "Item" in keys:
                        result.append((i, row, keys))
                return result

            old_rows = {}
            for start, _, keys in tables(old_lines):
                for line in old_lines[start + 2:]:
                    if not line.strip().startswith("|"):
                        break
                    row = dict(zip(keys, cells(line)))
                    old_rows[row.get("ID", row.get("Item"))] = row
            # Replace bottom-up, keeping notes and other tables outside the to-do table.
            for start, header, keys in reversed(tables(lines)):
                lang = "zh" if any(c in vocab.TODO_COLUMN_ALIASES for c in header) else "en"
                end = start + 2
                rows = []
                while end < len(lines) and lines[end].strip().startswith("|"):
                    row = cells(lines[end])
                    if len(row) != len(header):
                        raise ValueError(
                            f"Line {first_lineno + end}: user to-do table column count mismatch "
                            f"(expected {len(header)}, found {len(row)}): {lines[end]}"
                        )
                    rows.append(dict(zip(keys, row)))
                    end += 1
                added = [c for c in ("Raised", "Done") if c not in keys]
                columns = header + [vocab.TODO_COLUMN_LOCAL[lang][c] for c in added]
                column_keys = keys + added
                dated = []
                for row in rows:
                    prior = old_rows.get(row.get("ID", row.get("Item")), {})
                    prior_done = vocab.todo_status(prior.get("Status", "")) == vocab.TODO_DONE
                    created = row.get("Raised", "")
                    if date_key(created, now) == float("-inf"):
                        created = prior.get("Raised") or stamp
                    row["Raised"] = created
                    done = vocab.todo_status(row["Status"]) == vocab.TODO_DONE
                    completed = row.get("Done", "")
                    if completed in ("", "—", "-"):
                        completed = prior.get("Done", "") if prior_done else ""
                    if done and completed in ("", "—", "-"):
                        completed = stamp if baseline is not None and not prior_done else vocab.UNVERIFIED[lang]
                    row["Done"] = completed if done else "—"
                    if done and completed in UNVERIFIED_VALUES:
                        warnings.append(f"{row.get('ID', row['Item'])}{HISTORICAL_WARNING}")
                    dated.append((date_key(completed if done else created, now), row))
                render = lambda row: "| " + " | ".join(row) + " |"
                lines[start:end] = [render(columns), render(["---"] * len(columns))] + [
                    render([row.get(c, "") for c in column_keys])
                    for _, row in sorted(dated, key=lambda x: x[0], reverse=True)]
        output.extend(lines)
    return "\n".join(output) + "\n", warnings
