# AGENTS.md

This file defines the working rules for AI agents in this repository.

## Core Position

This repository builds a skill chain for Verilog/SystemVerilog development.

Agents must treat the repository as:

- a project for user-facing skills
- a portable repository
- a staged skill-chain workspace

Do not optimize for one local machine at the cost of repository portability.

## Rule 1: Portability First

When creating or updating any skill, preserve repository portability.

This includes:

- use relative paths for repository-internal references
- do not hardcode local absolute filesystem paths in skill content
- do not assume the repository will live on one fixed drive letter or user directory
- keep links, script references, and document references relocatable

Allowed:

- relative markdown links such as `references/language-requirements.md`
- relative script paths such as `scripts/check_syntax.py`

Not allowed in skill content:

- `E:\...`
- `C:\Users\...`
- any other machine-specific absolute path used as a normal repository reference

## Rule 2: Skill Structure

Organize each skill using the `skill-creator` structure:

- `SKILL.md` for trigger and workflow
- `references/` for supporting documents
- `scripts/` for executable helpers
- `assets/` only when real output assets are needed

Do not add skill-local `README.md` files unless there is a strong project-level reason.
For normal skill organization, `SKILL.md` and `references/` are the primary entry points.

This repository uses `skill-creator` as the structural reference, not as a requirement to add platform-specific metadata files.

Because these skills are not limited to Codex use:

- do not add `agents/openai.yaml` by default
- do not make skill usability depend on OpenAI-specific UI metadata
- keep the skill content portable across environments that understand `SKILL.md` and repository resources

## Rule 3: Language Contract Before Tooling

For Verilog/SystemVerilog skills:

- define the language contract first
- then bind checker behavior to that contract

Do not let one backend define the language by accident.

Always distinguish:

- language standard
- backend support
- project policy

## Rule 4: Programmatic Checking

Do not rely on manual document reading as the final syntax judge.

When a skill includes syntax checking, the checking path must be executable and scriptable.

Documentation defines the contract.
Programs enforce it.

## Rule 5: Minimal Executable Validation

Each skill must include a minimal executable validation path.

Do not stop at:

- concept documents
- language rules
- workflow descriptions

A skill is not considered complete enough for use unless there is at least one runnable validation path appropriate to that skill.

Examples:

- a syntax skill should include runnable checker scripts and minimal fixtures
- a transformation skill should include at least one runnable transformation example
- a generation skill should include at least one artifact-level validation path

The validation scope may be minimal at first, but it must be real.

## Rule 6: Keep The Root Clean

Keep project-level documents in the repository root.
Keep skill-specific material inside its own skill directory.

Do not scatter one skill's internal references, scripts, and fixtures across the root directory.
