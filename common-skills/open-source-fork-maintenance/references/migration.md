# Migrate an existing fork gradually

Use this path for an ad hoc fork, an aggregate with historical conflict repairs, or an existing v2/v3 registry. The first milestone is an equivalent source reconstruction on the current baseline. Upgrade the upstream release afterward. Existing feature sources may remain direct indefinitely.

## 1. Preserve the working release

Inspect remotes, branch/status, and all worktrees as in [setup.md](setup.md). Identify the actual upstream baseline, current aggregate SHA/tree, source refs, package receipts, and running version if the project deploys one. Treat an unproved build as unknown; do not turn an old successful build into evidence for a newly reconstructed SHA.

Create a uniquely named backup ref for the committed aggregate and durable refs for historical source/mapped commits needed to reconstruct it. Preserve existing package artifacts and receipts. Dirty files and untracked user data are not preserved by a Git tag: leave them in place and prepare migration in a separate clean worktree. Do not rewrite legacy branches or replace the running service as part of inventory.

Record the migration baseline and remaining ownership gaps in the project's maintenance report. If the current aggregate contains unreleased trunk commits, preserve them during structural migration and report that debt. Do not silently drop them to make the new layout appear based on a stable tag.

## 2. Inventory before rearranging history

Compare the current aggregate to its actual baseline. Use old registries, cherry-pick trailers, commit diffs, and source branches to establish ownership. Similar commit subjects or an issue number alone are not provenance.

Classify every retained change:

| Existing change | Migration action |
| --- | --- |
| Independent feature/fix with a usable source | Keep its ref and register its ordered owned patches. |
| Product behavior implemented only in the aggregate | Extract it into a feature/fix source; preserve a link to the original aggregate commit and verify behavior. |
| Compatibility-only conflict resolution | Assign it to the affected domain with reason, baseline, source mapping, and affected feature IDs. |
| Shared prerequisite used by several features | Give it one source owner and explicit dependents; do not replay copies as separate fixes. |
| Fork maintenance files required for reconstruction | Give them an explicit maintenance selection in the train. |
| Patch fully supplied by the selected upstream release | Prove behavior coverage, then retire it with evidence. Partial adoption retains the remaining local behavior. |
| Unknown or inseparable historical change | Keep it in the preserved old release and list the ownership gap; extract/split it before claiming a complete replacement train. |

An aggregate commit may mix several responsibilities. Split its content in a source/maintenance worktree and record the original mapping; do not claim that the entire commit belongs to each feature. If a change genuinely belongs to multiple selected features, the canonical mapped patch names those owners and is applied once. Verify extraction by the resulting content and behavior.

Upgrade the registry to v4 using [registry.md](registry.md). Preserve stable IDs, historical source-to-aggregate records, `lastPackaged`, and the actual baseline. Classify v2 issue references individually into specification, real upstream feedback, or related context. Existing v4 legacy entries without explicit source selections need the same ownership audit before joining a frozen train. Record unresolved history in the migration report; do not fabricate a successful receipt or an executable source selection to silence warnings.

## 3. Pilot one domain

For a fork with no recurring shared adaptation work, skip domain creation and prove the explicit direct selections in the next step. Its v4 registry can keep `domains: []`; it follows the same maintenance model and can add a domain later.

Choose a small but representative cluster with recurring shared compatibility work. Leave other features direct. Build the domain on the existing baseline from its selected source commits and explicit dependencies, including old conflict adaptations that remain necessary. Keep dormant source refs fixed.

Record every returned source-to-domain mapping, split/combined mapping, and adaptation. Exercise at least one contribution extraction: it should contain the chosen feature, required dependencies, and relevant adaptations, with no unrelated domain features. Run the relevant behavior checks for both the domain and the extracted contribution. This proves that domain aggregation has not made upstream-sized contributions impractical.

A conflict found by the pilot belongs to its source, shared dependency, or domain adapter. A new product fix goes back to a feature/fix source and gets its own verification. Do not conceal behavior changes inside the structural migration.

## 4. Prove the complete reconstruction

Freeze a train containing any pilot domain, the direct features, dependencies, and required maintenance patches. See [maintenance.md](maintenance.md) for compose commands. Commit its inputs, then construct a new create-only candidate.

Prepare the intended snapshot in the migration worktree from the preserved old aggregate plus the declared maintenance changes and any separately accepted repairs. Commit it before comparison. It is an independent content reference for the candidate, not a copy of the candidate used to make the comparison pass.

Use two comparisons:

1. **Legacy release to intended snapshot:** account for every changed path. A structural migration changes only the declared maintenance records/tools; separately accepted product repairs have their own source mappings and verification. Do not hide unexpected product differences behind broad path exclusions.
2. **Intended snapshot to composed candidate:** compare the entire tracked tree with no exclusions. Keep the command/result and both tree IDs as evidence:

   ```bash
   git diff --exit-code <intended-snapshot> <candidate> --
   git rev-parse '<intended-snapshot>^{tree}' '<candidate>^{tree}'
   ```

Equal product files with missing AGENTS, scripts, or documentation are not a complete reconstruction. The composer adds the registry and selected train automatically; all other required maintenance content must be in the selected patch sequence. Resolve all retained ownership gaps before replacing the old aggregate.

For a packaged project, verify and build this exact candidate with its normal workflow. A source-only migration can finish at verified-source status; it cannot claim packaged status. For projects with persistent data, include representative historical schema/ledger upgrade fixtures as described in SKILL.md. Reusing an old build requires proof that its relevant inputs are identical; changing the source SHA is not itself such proof.

## 5. Cut over the maintenance workflow

After reconstruction and the selected delivery stage pass, publish the source/domain/manifest/candidate references to the personal fork and verify remote SHAs. Preserve historical objects through immutable refs, not merely SHA strings in a JSON file. Install or update the project AGENTS block for the completed layout, including it in the intended snapshot and train before final composition. During preparation, transitional guidance must describe the actual checkout rather than falsely declaring an early cutover.

Replace the aggregate root within the authorized migration after checking its branch, status, and worktrees again and preserving its old ref. Do not overwrite concurrent work. Existing deployment authorization and tooling still govern any running service; migration alone does not deploy it.

Migration is complete when any chosen domains and the direct patches have explicit ownership, a full reconstruction and relevant checks pass, publication matches the requested scope, and another environment can retrieve the recorded inputs. It does not require moving every feature into a domain. The next stable release can then upgrade domains independently of dormant sources.

## Keep, change, retire

Keep feature-sized source history, stable IDs, exact package evidence, feedback roles, immutable release refs, and useful standalone patches. Change the location of compatibility work and the way release inputs are frozen. Retire duplicate integration copies and completed temporary worktrees only after their source and evidence are durable and the worktrees are inactive and clean. Upstream issue closure, a merge on trunk, or a domain's existence is not sufficient evidence to delete a local patch.
