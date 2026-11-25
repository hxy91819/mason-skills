# Workbook template

Default path `<main checkout root>/.local/steward/<topic>.md`; if the project AGENTS.md specifies otherwise, the
project wins. If the directory is missing, run `steward_workbook.py --mode init` first; the workbook and requirement
ledger are committed only to the local git in that directory, never pushed, no MR. The three sections are fixed;
a section with no content says `none`. Admission criteria: SKILL.md "Workbook"; route states: "Closing
reconciliation". When the project already has a roadmap or decision registry, the route and key-decision
sections hold only links and the current position; the example lines in the template are for projects without them.

Section headings, the `←` state keywords, the to-do table header, the to-do status values (`open`/`done`), the
"why only the user" categories and `not blocking` are literals parsed by `scripts/`. Free-text content in `<…>`
placeholders may be written in any language. Existing workbooks and ledgers in the earlier Chinese vocabulary stay
valid and keep their language.

```markdown
# <goal in one sentence>

Updated: <YYYY-MM-DD>; per-item status, results and material in [Requirements ledger](<topic>-requirements.md).

## Route

- [x] <Stage 1: one sentence on the output>
- [ ] <Stage 2> ← in progress thr_xxx
- [ ] <Stage 3> ← waiting on user
- [ ] <Stage 4> ← scheduled <MM-DD HH:MM> <what to do at that time>
- [ ] <Stage 5> ← after <Stage 2>: <which output of Stage 2 it needs>

## Key decisions

- <YYYY-MM-DD> <decision in one sentence>. Reason: <one sentence>. Impact: <which stages or modules>.

## User to-dos

| ID | Status | Item | Background | Recommendation | Why only the user | Blocks | Raised | Done |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | open | <what to do> | <what it is, why the user must do it now, what happens if not; no internal codenames> | <recommended answer> | physical device: <device or session only the user has> | <Stage 3> | <YYYY-MM-DD> | — |
| D2 | open | <what to do> | ... | ... | credentials: <token or permission only the user holds> | not blocking | <YYYY-MM-DD> | — |
| D3 | done | <what to do> | ... | — | ... | ... | <YYYY-MM-DD> | — |
```

After every edit run `steward_workbook.py --mode verify --file <workbook path>`; the script writes completion times
in Singapore time, sorts and validates; commit once it passes. Keep the route time comments the script generates.
Missing historical completion times show as `unverified`; never guess dates.

When one project has several stewards, to-do numbers carry this steward's short prefix (e.g. `HST-D1`); conventions
shared by all stewards go in `shared-conventions.md` in the same directory, and key decisions hold one line
`- Shared conventions: see [shared conventions](shared-conventions.md).`

Add one line to the project `AGENTS.md` so any session can pick up:

```markdown
The steward workbook is at `.local/steward/<topic>.md` under the main checkout root (a local directory, ignored by git, not in the repo); if missing, create it with bb-steward init; if present, read it first and report only open user to-dos.
```

## Requirement ledger template

Default path `.local/steward/<topic>-requirements.md`. Admission, when to write and status semantics: SKILL.md
"Requirement ledger". One table per period; update rows in place and keep historical rows; the ledger is
independent of the workbook's three sections and one-screen gate. Replace the placeholder rows before validating.

The period heading format `## <YYYY-MM-DD> onward (<topic>)`, the five column headers and the seven status values
are literals parsed by `scripts/`.

```markdown
# <goal>: user requirement ledger

## <YYYY-MM-DD> onward (<topic>)

| Date | Requirement | Status | Result | Material |
| --- | --- | --- | --- | --- |
| <MM-DD> | <one independent request from the user> | In progress | <current progress or dependency> | — |
| 10-27 | Optimize CI performance | Done | CI 21→8 min (-62%), docs-only check 52 s | [PR #117](https://github.com/example/project/pull/117) |
```
