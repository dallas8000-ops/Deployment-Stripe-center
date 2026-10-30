---
name: skill-creator
description: >-
  Helps you build custom Claude Code skills — reusable, invocable workflows
  that encode repeatable tasks for this project. Use when you want to codify a
  workflow you keep doing manually, automate a multi-step process, or add a
  slash command that future Claude sessions can invoke. Triggers on: "create a
  skill", "make a slash command", "encode this workflow", "add a /command for",
  or "I keep doing X — can you make it a skill".
metadata:
  short-description: Build custom reusable skills and slash commands

---

## What is a skill?

A skill is a markdown file (`SKILL.md`) stored under `.agents/skills/<name>/` and symlinked into `.claude/skills/`. When Claude sees `/<name>` in a user message, it loads the skill and follows its instructions. Skills encode repeatable, project-specific workflows so you don't have to re-explain them every session.

## Skill file format

```markdown
---
name: skill-name            # kebab-case, matches directory name
description: >-
  One paragraph. Explain WHAT the skill does and WHEN Claude should use it.
  Include trigger phrases — the exact user words that should activate this skill.
  This is what appears in the skill list and determines auto-detection.
metadata:
  short-description: 5-word summary shown in menus
allowed-tools:              # optional: restrict which tools this skill may use
  - Bash(npm run *)
  - Read
  - Edit

---

## Instructions for Claude

Write the actual workflow here in prose + code blocks.
Treat this as a briefing to a smart colleague who has never done this task.
Include: the goal, the steps in order, commands to run, things to check, how to report results.
```

## Process for creating a skill

1. **Identify the workflow** — ask: what is the repeatable task? What does the user type to trigger it? What are the steps?
2. **Name it** — kebab-case, verb or noun, short (e.g., `deploy-check`, `seed-db`, `gen-types`).
3. **Write the description carefully** — this is the most important field. It must:
   - Say exactly what the skill does
   - List trigger phrases (the user words that should invoke it)
   - Be specific enough that Claude knows when to auto-invoke vs. skip
4. **Write the body** — step-by-step instructions, commands, rules, and edge cases.
5. **Create the files**:
   ```bash
   mkdir -p ".agents/skills/<name>"
   # write SKILL.md there
   ln -s "../../.agents/skills/<name>" ".claude/skills/<name>"
   ```
6. **Test it** — type `/<name>` in Claude Code and confirm it loads and behaves correctly.

## Rules for good skills

- **Description first** — a vague description means Claude won't trigger the skill at the right time.
- **One skill, one job** — don't combine unrelated workflows. Better to have two focused skills than one bloated one.
- **Include commands verbatim** — don't say "run the build command"; say `npm run build`.
- **Specify what to report** — tell Claude what output to give the user when done.
- **Use `allowed-tools`** when the skill should only use specific tools (improves safety and focus).
- **Add references** — for data-heavy skills, put reference docs in `references/` subdirectory and link with `<references/filename.md>`.

## Skill with references

For skills that need substantial reference material (API docs, schema, rules):

```
.agents/skills/my-skill/
  SKILL.md              ← main instructions
  references/
    api.md              ← referenced as <references/api.md>
    schema.md
```

In `SKILL.md` body: `Read <references/api.md> before answering any question about the API.`
