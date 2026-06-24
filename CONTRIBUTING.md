# Contributing to FunBrowser

Thanks for considering a contribution. The project is young — the surface
moves, but the core pieces (CDP core, stealth, solver, pool, panel) have
settled. PRs that touch test coverage, fix detection regressions, or add
captcha types are especially welcome.

## Local setup

```bash
git clone https://github.com/WhyY0u/funBrowser.git
cd funBrowser
uv sync          # creates .venv, installs deps incl. dev + optional extras
```

You'll need Chrome (or Chromium / Brave / Edge) installed for the
integration tests. Set `FUNBROWSER_CHROME=<path>` if it isn't in the
default location.

## Running checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy funbrowser
uv run pytest -q
```

The full suite has ~170 tests. Pure-Python tests are <10s; integration
tests against real Chrome take 1-2 minutes.

## Style

- Python 3.11+, async-first
- ruff for lint + format (config in `pyproject.toml`)
- mypy strict mode on the `funbrowser` package
- Docstrings: short, why-focused. Don't restate the obvious.
- Tests live next to the feature; integration tests need a Chrome guard
  (`pytest.mark.skipif(find_chrome() is None, ...)`)

## Stealth contributions

If you spot a fingerprint leak we don't handle, please open an issue
with the detection query first (the JS that catches us). Fixes go in
`funbrowser/stealth/scripts/` as a new IIFE-wrapped JS file plus an
entry in `SCRIPTS` in `funbrowser/stealth/patches.py`.

`examples/detect_check.py` is the canonical "does the JS layer pass"
audit. Every stealth change should keep it at 25/25.

## Captcha contributions

To add a new captcha type:

1. New `funbrowser/solver/scripts/<name>.js` with a detector that calls
   `window.__funbrowser.solve({type: "...", ...})` on match
2. New `solve_<name>()` method on `FunSolverClient` constructing the
   correct task payload
3. New branch in `_solve_dispatch()` in `funbrowser/solver/bridge.py`
4. Unit tests covering both the client method and dispatch

See the M4 commit for the pattern (`recaptcha_v2`, `hcaptcha`,
`funcaptcha`, `geetest` are good references).

## Releasing

Maintainer-only:

```bash
# Bump version in pyproject.toml + funbrowser/__init__.py
git commit -m "release: v0.1.X"
git tag v0.1.X
git push --tags
# CI publishes to PyPI via the release workflow.
```

## Code of conduct

Don't be a jerk. Keep PR discussion technical. If you're working on
something defensive (CTF, your own research, authorised pentest), say
so up front in the PR description.
