# Save or update polishing preferences

Read this only when the user requests persistent defaults. A missing `EXTEND.md` does not trigger setup; ordinary polishing uses the defaults and precedence in [SKILL.md](../../SKILL.md#resolve-preferences).

## Resolve values and destination

Use choices already supplied by the user or an existing preference file. Ask only for unresolved values that matter to the requested saved configuration, including project versus user scope if that scope is not established. Batch necessary questions through the host's supported input tool, within its question/option limits; otherwise ask concisely in the user's language.

Supported values and defaults live in [extend-schema.md](extend-schema.md). Custom style, audience, and goal text are allowed. Preserve unrelated fields when updating an existing file.

| Scope | Destination |
| --- | --- |
| Project | `.mason-skills/article-polish/EXTEND.md` |
| XDG user config | `${XDG_CONFIG_HOME:-$HOME/.config}/mason-skills/article-polish/EXTEND.md` |
| Legacy user config | `$HOME/.mason-skills/article-polish/EXTEND.md` |

When creating a new user-scope file, prefer XDG unless the user selected the legacy location. Project preferences take precedence over both; disclose an existing higher-priority file if it would hide the requested change.

## Save and continue

Create or update only the requested destination, using schema-valid YAML. Report the saved path and continue any pending polishing through the selected mode's final output.

Deleting a preference file restores defaults on the next use; it does not reintroduce a setup questionnaire.
