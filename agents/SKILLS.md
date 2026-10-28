# SKILLS.md

Conventions for the skills in this repository. All skills and this file
itself must follow them.

## Skill layout

- Each skill is a directory under `agents/skills/`, named exactly after
  the `name` field in its frontmatter, containing a `SKILL.md`
  (e.g. `agents/skills/tmux-interactive-sessions/SKILL.md`). This is
  the portable Agent Skills form.
- `agents/install.sh` copies everything under `agents/skills/` to
  `~/.agents/skills/`. Run it after adding or editing a skill so the
  installed copy stays in sync with the repo.

## Skill frontmatter

- Every `SKILL.md` starts with YAML frontmatter carrying `name` and
  `description`.
- `name`: lowercase letters, numbers, and hyphens only; matches the
  skill's directory name.
- `description`: the routing signal an agent uses to decide whether to
  load the skill. State what the skill teaches and when it applies.
  Keep it on a single line (frontmatter is exempt from the 80-col rule;
  the Agent Skills limit is 1024 characters). It must remain valid YAML:
  an unquoted value cannot contain `: ` (colon + space); use ` - ` or
  quote the value. A malformed frontmatter line keeps the whole skill
  from loading.
- After editing a skill, parse its frontmatter (e.g. with a YAML
  parser) before running `agents/install.sh`; a loading failure is
  silent in normal use.

## Skills Style

- Use only ASCII characters in all skills.
- Prefer proper prose over em dashes.
- No line (except YAML frontmatter and fenced code/command blocks)
  should exceed 80 cols. Tables are not exempt: if a table row cannot
  fit within 80 cols, rewrite the table as a list.
- Wrap prose at a comfortable width below the limit; do not reflow
  existing text only for style.

## Verifying claims

- A skill that documents tool or command behavior may only call behavior
  "verified" if it was actually run and observed. Record the version the
  verification ran against (e.g. tmux 3.7c).
- Mark environment-dependent behavior (shell flavor, remote hosts,
  timings) as such, and keep a note of what is explicitly not verified.
- Prefer extending a skill's verification notes over presenting untested
  behavior as fact.
