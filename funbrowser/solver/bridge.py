"""Wire funsolver.com calls onto a Tab via a CDP binding.

Mechanism:
- ``Runtime.addBinding`` registers ``window.__funbrowser_solve`` so any JS
  call to it shows up on the CDP side as a ``Runtime.bindingCalled`` event.
- The bootstrap script gives the page a Promise-based API
  (``window.__funbrowser.solve(req)``) that wraps the binding call.
- The Python handler reads the payload, talks to funsolver.com via the
  ``FunSolverClient``, and pushes the result back with ``Runtime.evaluate``
  calling ``window.__funbrowser_resolve(id, {ok, token|error})``.

Note: this requires ``Runtime.enable``, which has a known minor antibot
tell (CDP frames appear in error stacks). Moving the binding to an
isolated world via ``Page.createIsolatedWorld`` is planned for a
follow-up — it keeps the binding off the page's main world entirely.
"""

from __future__ import annotations

import json
import logging
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from .client import FunSolverClient, FunSolverError

if TYPE_CHECKING:
    from ..tab import Tab

logger = logging.getLogger(__name__)

BINDING_NAME = "__funbrowser_solve"
SCRIPTS = ("_bootstrap.js", "turnstile.js")


def _load_scripts() -> str:
    pkg = files("funbrowser.solver.scripts")
    return "\n".join(pkg.joinpath(s).read_text(encoding="utf-8") for s in SCRIPTS)


_SOLVER_SOURCE = _load_scripts()


async def _solve_dispatch(client: FunSolverClient, payload: dict[str, Any]) -> str:
    cap_type = payload.get("type")
    if cap_type == "turnstile":
        return await client.solve_turnstile(
            sitekey=payload["sitekey"],
            page_url=payload["url"],
            action=payload.get("action"),
            cdata=payload.get("cdata"),
        )
    raise FunSolverError(f"unsupported captcha type: {cap_type!r}")


async def apply_solver(tab: Tab, client: FunSolverClient) -> None:
    """Attach the funsolver bridge + per-captcha detectors to a Tab."""
    await tab._send("Runtime.enable")
    await tab._send("Runtime.addBinding", {"name": BINDING_NAME})

    async def on_binding_called(params: dict[str, Any]) -> None:
        if params.get("name") != BINDING_NAME:
            return
        try:
            payload = json.loads(params["payload"])
        except (KeyError, ValueError):
            logger.exception("solver: malformed binding payload")
            return

        task_id = payload.get("id")
        try:
            token = await _solve_dispatch(client, payload)
            result: dict[str, Any] = {"ok": True, "token": token}
        except Exception as exc:
            logger.warning("solver: solve failed: %s", exc)
            result = {"ok": False, "error": str(exc)}

        try:
            await tab._cdp.send(
                "Runtime.evaluate",
                {
                    "expression": (
                        f"window.__funbrowser_resolve({json.dumps(task_id)}, {json.dumps(result)})"
                    ),
                    "awaitPromise": False,
                },
                session_id=tab.session_id,
            )
        except Exception:
            logger.exception("solver: failed to push result back to page")

    tab._cdp.on(
        "Runtime.bindingCalled",
        on_binding_called,
        session_id=tab.session_id,
    )

    await tab._send(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": _SOLVER_SOURCE, "runImmediately": True},
    )
