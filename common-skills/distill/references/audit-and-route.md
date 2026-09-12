# Audit and route candidate changes

## Phase 2: Audit and Route

Audit two required lanes before proposing additions: the applicable harness and the
project documentation touched by the session's concepts or decisions. The harness lane
must include the repository's agent-instruction and Skill surfaces; they are not optional
documentation. A lane may produce no candidate only after its relevant sources of truth
have been inspected. Apply this table to every existing rule, mechanism, or document in
scope:

| State | Action |
|---|---|
| Stale | Delete it or update the source of truth. |
| Duplicate | Merge the meaning into one authoritative location. |
| Conflicting | Resolve to one authoritative meaning and location; ask if intent remains ambiguous. |
| Superseded | Remove prose replaced by equivalent verified enforcement, retaining only useful rationale or routing. |
| Misplaced | Move it to the narrowest effective scope; broader sources may point but must not restate. |
| Live | Keep it unchanged. |

Resolve conflicts from, in order: the user's current explicit intent and declared
authority and scope; approved specs and contracts; then implementation, tests, and
configuration as evidence of current behavior rather than automatic proof of intended
behavior. Never silently choose between unresolved semantic rules.

### Evidence, scope, and recurrence

Evaluate four dimensions separately:

- **Authority** determines whether a conclusion can be treated as intended truth.
- **Scope** determines where it may be applied: task, repository, team or organization,
  user preference, or general practice.
- **Recurrence** estimates repeated future cost across distinct tasks or sessions.
- **Impact** captures correctness, safety, time, and interaction cost even when an event
  is rare.

One explicit user correction may justify a candidate when its scope is clear and durable.
Do not generalize a task-local instruction into a repository rule, or a personal preference
into project truth. Route user preferences to user-scoped context only when that target is
available and approved. A user-driven behavioral reversal without an explicit statement
is a lower-authority hypothesis.

Agent-inferred gotchas and best practices require independent verification; recurrence
alone never makes them true. Repeated attempts inside one task do not increase recurrence.
A mechanically verified, high-impact one-off may still justify a candidate. Recurrence
after a prior change is stronger evidence that the change is undiscoverable, incomplete,
misrouted, or based on a false hypothesis.

### Decision approval and visibility

Treat a decision as material when it changes what the user receives or must operate,
including product or release composition, independent usability, installation and offline
behavior, compatibility or migration, supported environments, security boundaries,
external dependencies, or operational ownership and cost.

For every material decision, record its provenance as explicitly user-confirmed, inherited
from an approved source, or agent-proposed. An agent-proposed decision remains a hypothesis
until the user sees the choice, user-visible consequences, rationale or tradeoff, and any
rejected alternative needed to understand it, then confirms it. Approval of a broad plan
counts only when that plan disclosed those consequences in plain language; package names,
implementation terminology, code, tests, or completed work do not prove informed approval.

Audit discoverability separately from authority. A material decision must be visible at
the appropriate abstraction level in a document its human stakeholders are expected to
read. Agent-only execution material may carry exact implementation details, but it cannot
be the sole place where the decision or its consequences appear. A human-facing summary
and a linked detailed contract are complementary, not duplicate sources of truth.

For every durable change, test the future task path: would a human or agent encountering
the same work naturally reach the authoritative source before repeating the old mistake?
If not, improve routing or placement rather than copying the rule into multiple locations.

When one human-facing document carries multiple material decisions, present them as a
numbered decision list. For every item, state the decider, the agent recommendation and
whether the user accepted or rejected it, and the result and user-visible impact. Mark an
unconfirmed recommendation as pending user confirmation; never rewrite it as a user
decision because implementation already exists.

If implementation, documentation, or a gate relies on an unconfirmed or human-invisible
material decision, propose surfacing the decision for approval and revoking the affected
readiness or completion claim before treating current behavior as intended.

### Project-knowledge lane

Keep project documentation as a compact map for humans and agents: product concepts,
system boundaries, architecture, major workflows, and the decisions needed to reason
about them. Route details that code, tests, types, schemas, or configuration already make
cheap to discover back to those sources. When a durable decision's rationale is local to
code and the code cannot express why the choice exists, preserve it in a
decision-oriented comment; otherwise update the narrowest authoritative document.

Preserve every durable product or technical decision established by the user in one
authoritative location. Record the choice and why it was made, plus constraints or
consequences needed to apply it correctly. Do not create a duplicate decision log when an
existing product, architecture, specification, or code surface is already the better
home.

For a surviving project-knowledge candidate, read
[核心知识落点](knowledge-sinks.md). Route it to the narrowest live source rather
than adding retrospective prose: `AGENTS.md` for mandatory agent behavior and reachability,
`CONTEXT.md` for domain boundaries, the documentation index for routing, a domain contract
for durable decisions and user-visible behavior, and Skills/scripts for repeatable work.
The source must carry the choice, rationale, scope, authority, and a current verification
path; code, tests, schema, and configuration remain authoritative for mechanically cheap
facts. Historical evidence must visibly name its replacement instead of becoming a second
live procedure.

Simplify documentation in this order:

1. Delete or reconcile conflicting, superseded, and duplicate material.
2. Correct claims that disagree with current approved intent or verified behavior.
3. Consolidate scattered explanations into the narrowest authoritative source and leave
   pointers only where discovery requires them.
4. Add only missing global context or decision rationale that survives the evidence and
   value gates.

Prefer a net reduction when deletion or consolidation communicates the same truth. Keep
implementation walkthroughs, line-by-line behavior, inventories, and other cheap lookups
in code and the environment. Persistent documentation must describe the project, not the
retrospective session that caused it to change.

### Harness lane

Prefer pruning and consolidation before addition. Route the surviving signal to the
closest reliable layer:

| Signal | Harness layer |
|---|---|
| Unclear intent, behavior, or acceptance | Spec, contract, or task interface |
| Missing discovery or judgment-dependent guidance | Context pointer, focused documentation, or skill |
| Repeated operation | Tool, script, or common command entry point |
| Mechanically decidable invariant | Type/schema constraint, behavioral test, lint, or architecture check |
| Check must apply to every change | Run the same local verifier from pre-commit and existing CI |
| Environment, access, or consequence risk | Reproducible environment, permission boundary, or approval control |
| Promising but unverified change | Falsifiable eval with a predicted outcome |

#### Agent instructions and Skills

Always inspect the applicable `AGENTS.md` chain and inventory the repository-owned Skills,
including their names, descriptions, invocation policies, and visible relationships.
Deep-read every Skill that was invoked, edited, referenced, expected to trigger, or plausibly
overlaps a surviving signal. In review mode, also deep-read the remaining repository Skills
in deterministic batches when the stated scope is a repository harness review; disclose
any portion not inspected rather than implying full coverage.

Audit this surface as a system, not only as prose files:

- **Coverage:** Does each recurring job or judgment have one clear owner, and are there
  gaps, duplicate Skills, or overlapping responsibilities that leave routing ambiguous?
- **Invocation:** Do names, descriptions, explicit-only markers, `agents/openai.yaml`, and
  user-facing invocation examples agree with the workflow's actual risk and intended use?
- **Reachability:** Will the applicable `AGENTS.md` pointer or Skill description cause the
  right instructions to be loaded before the relevant decision? Are references and
  dependencies reachable without relying on hidden repository knowledge?
- **Usability:** Are branches, approval gates, completion criteria, failure handling, and
  handoff outcomes clear enough to execute without avoidable questions, retries, or user
  correction? Treat a repeated workaround as evidence about the interface, not merely the
  operator.
- **Coherence:** Do repository instructions, Skill instructions, scripts, validators, and
  actual host behavior reinforce one authoritative workflow, or conflict, duplicate, and
  cache facts that belong elsewhere?
- **Effectiveness:** Where comparable evidence exists, did the instruction or Skill change
  the task path as intended? Distinguish a design defect from incorrect execution, missing
  host capability, and absence of a comparable opportunity.

Do not require a session failure before reporting a mechanically demonstrable Skill or
instruction defect, such as conflicting invocation policy, a broken pointer, an impossible
completion criterion, or two Skills claiming the same trigger. Carry subjective usability
concerns without task evidence as hypotheses and propose a forward test when current
inspection cannot settle them.

CI is an execution venue, not the sole implementation of a rule. Keep one source for each
meaning. Let the environment state facts that are cheap to inspect; prose should carry
intent, rationale, non-obvious constraints, or routing. Remove a safety, permission,
approval, or validation rule only after equivalent protection is demonstrated.

Complete this phase when every surviving signal in both lanes has one proposed action and
target layer, with existing overlap and conflicts accounted for. Group signals solved by
the same authoritative change; they are one candidate, not several.
