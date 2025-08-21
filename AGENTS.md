# AGENTS Guidelines for This Repository

This repository contains a Python-based Vercel Functions application for monitoring RPC node response times. When working on the project interactively with an agent (e.g. the Codex CLI) please follow the guidelines below to ensure smooth development and testing.

## 1. Use Test Scripts for Local Development

* **Always use the test scripts** (`test_api_read.py`, `test_api_write.py`, `test_update_state.py`) for local testing and development.
* **Do _not_ deploy to Vercel during the agent session** unless explicitly requested. Deployments should be handled outside of the interactive workflow to avoid disrupting production services.
* **Create a `.env.local` file** with the necessary environment variables before testing locally.

## 2. Keep Dependencies in Sync

If you add or update dependencies:

1. Update `requirements.txt` with the new package and version.
2. Reinstall dependencies in your virtual environment with `pip install -r requirements.txt`.
3. Verify compatibility with Python 3.9+ as specified in the project.

## 3. Coding Conventions

* Follow PEP 8 style guidelines.
* Use type hints for all function parameters and return values.
* Include Google-style docstrings for all functions and classes.
* Keep cyclomatic complexity below 10 (enforced by Ruff).
* Prefer composition over inheritance when designing metric classes.

## 4. Code Quality Checks

Before completing any task, run these quality checks:

| Command               | Purpose                                           |
| --------------------- | ------------------------------------------------- |
| `black .`             | Format code to project standards                 |
| `ruff check .`        | Run linting checks                               |
| `ruff check . --fix`  | Auto-fix linting issues where possible           |
| `mypy .`              | Run type checking                                |

## 5. Testing Guidelines

* Test new metrics locally using the appropriate test script:
  - `python tests/test_api_read.py` for read metrics
  - `python tests/test_api_write.py` for write metrics  
  - `python tests/test_update_state.py` for state updates
* Ensure `endpoints.json` is properly configured before testing.
* Mock external API calls when writing unit tests.

## 6. Project Structure

When adding new features, maintain the existing structure:

* `/api/` - Vercel Functions entry points only
* `/common/` - Shared utilities and base classes
* `/metrics/` - Blockchain-specific metric implementations
* `/tests/` - Test scripts and unit tests

## 7. Environment Variables

Never commit credentials or secrets. Always use environment variables:

* Development: `.env.local` (git-ignored)
* Production: Configured in Vercel dashboard
* Metrics are automatically prefixed using the `METRIC_PREFIX` constant from `config/defaults.py` which reads `os.getenv("VERCEL_ENV")` (e.g., "dev_" for non-production and "" for production)

---

Following these practices ensures reliable development and prevents disruption to the production monitoring system. When in doubt, test locally before making any deployment-related changes.