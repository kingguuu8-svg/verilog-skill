# Environment Setup

## Goal

Describe the minimum environment required to run the stage-1 Verilog/SystemVerilog checking flow.

This document is for users and agents that need to make the skill runnable on a local machine before working on HDL code.

## Minimum Requirements

The stage-1 checking path assumes:

- Python can run the scripts under `scripts/`
- the repository can write temporary files under `.tmp/verilog-language-and-syntax`
- `iverilog` is available through either:
  - `IVERILOG_BIN`
  - repo-local install under `tools/iverilog/current`
  - system `PATH` fallback
- `verible-verilog-syntax` and `verible-verilog-lint` are available through either:
  - `VERIBLE_VERILOG_SYNTAX_BIN`
  - `VERIBLE_VERILOG_LINT_BIN`
  - repo-local install under `tools/verible/current`
  - system `PATH` fallback

## Preferred Setup

Prefer repo-local tool installs over machine-global setup.

Recommended layout:

- `tools/iverilog/current/bin/iverilog.exe`
- `tools/iverilog/current/lib/`
- `tools/iverilog/current/include/`
- `tools/verible/current/verible-verilog-syntax.exe`
- `tools/verible/current/verible-verilog-lint.exe`

Reason:

- avoids relying on shell-specific `PATH` initialization
- keeps the skill behavior reproducible across machines
- reduces failures caused by multiple tool versions on one machine

## Bootstrap Flow

### 1. Bootstrap Verible Repo-Locally

If Verible already exists somewhere on the machine, copy it into the repository:

```bash
python scripts/install_verible.py --source-root <existing-verible-root>
```

Or:

```bash
python scripts/install_verible.py --source-bin <path-to-verible-verilog-syntax>
```

### 2. Bootstrap Icarus Repo-Locally

If Icarus already exists somewhere on the machine, copy it into the repository:

```bash
python scripts/install_iverilog.py --source-root <existing-icarus-root>
```

Or:

```bash
python scripts/install_iverilog.py --source-bin <path-to-iverilog>
```

### 3. Probe The Installed Backends

After bootstrap:

```bash
python scripts/probe_backend.py --backend all
```

Expected result:

- `status: ok` for required backends
- `backend_origin: repo_local` when the repo-local install is being used

### 4. Run Skill Validation

```bash
python scripts/validate_skill.py
```

This is the minimum executable check that the skill environment is actually usable.

## Environment Variables

Supported overrides:

- `IVERILOG_BIN`
- `VERIBLE_VERILOG_SYNTAX_BIN`
- `VERIBLE_VERILOG_LINT_BIN`

Use them when:

- you are bootstrapping repo-local tools from an existing machine install
- you need a one-off override for diagnosis
- you cannot yet copy tools into the repository

Do not treat environment variables as the preferred steady-state setup when repo-local tools are possible.

## Temporary Directory Behavior

The checker scripts override `TMP` and `TEMP` to:

- `.tmp/verilog-language-and-syntax`

Reason:

- reduce failures on Windows hosts whose default temp path contains non-ASCII characters
- keep checker artifacts inside the repository workspace

## Failure Diagnosis

### Backend Not Found

Typical symptom:

- `backend_not_found`

Check in this order:

1. whether the repo-local tool files exist under `tools/`
2. whether the relevant environment variable points to a real executable
3. whether the tool is only available through `PATH`

### Backend Not Runnable

Typical symptom:

- `backend_not_runnable`

Common causes:

- copied only the main executable but not the required support files
- source and destination overlap during bootstrap
- DLL or library files are missing from the copied install tree

For Icarus, copying only `iverilog.exe` is not enough. Keep the install tree shape intact.

### Validation Fails But Probe Succeeds

Typical cause:

- tool exists, but the actual input shape or testbench uses constructs outside the current backend support

Interpretation rule:

- probe confirms environment availability
- `check_syntax.py` and `validate_skill.py` confirm actual usable capability

## Practical Rule

Before extending the skill or blaming HDL source, first ensure:

1. `probe_backend.py --backend all` is healthy
2. `validate_skill.py` passes

If those two checks fail, fix the environment first.
