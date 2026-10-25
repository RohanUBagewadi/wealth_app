# Baseline report

## Repository audit

- The repository contained only a PyCharm sample `main.py`, the product specification, and Spendee research notes. There was no existing application UI, API, persistence layer, dependency manifest, migration, test suite, or Git repository.
- `main.py` only printed `Hi, PyCharm` and ran successfully before implementation.
- PyCharm initially had no interpreter configured. A project virtual environment was configured at `.venv` using Python 3.9.6; the interpreter is `.venv/bin/python` and package manager is pip.
- No framework or data libraries were installed initially (no Flask, FastAPI, SQLAlchemy, pytest, cryptography, or PDF library).
- REA research remains incomplete and its current blocker is recorded in `rea_work/research/spendee/00-research-index.md`. It is not used as implementation evidence.

## Baseline test and run status

- No tests were present, so there were no baseline tests to run.
- Baseline command: `.venv/bin/python main.py`; result: `Hi, PyCharm`.
- No documented application launch command or deployment configuration was present.

## Initial gaps

- No finance domain model or validated integer-minor-unit money handling.
- No database, transaction semantics, import staging, backup, sync, or authentication.
- No responsive UI, accessibility patterns, error handling, or documentation.

## Implementation boundary

The first implementation uses a single-user local service bound only to loopback and SQLite stored under an ignored local `instance/` directory. Hosted synchronization/authentication and live pCloud OAuth remain unresolved deployment decisions. The application offers encrypted manual backup files as a safe local fallback. It does not connect to banks or extract statements automatically.
