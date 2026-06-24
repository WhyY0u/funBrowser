"""ElementHandle — a chainable reference to a DOM element in a Tab.

Held by an opaque CDP ``objectId`` so the same JS object is targeted on each
call even if the surrounding DOM mutates. Becomes stale (and methods will
raise) after the page navigates away — get a fresh handle via ``tab.find`` or
``tab.query`` after navigation.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from . import humanly as _humanly

if TYPE_CHECKING:
    from .tab import Tab


def _is_navigation_race(details: dict[str, Any]) -> bool:
    """Mirror of :func:`funbrowser.tab._is_navigation_race`. Kept here
    to avoid a circular import (element.py is imported by tab.py)."""
    text = details.get("text", "")
    exc = details.get("exception", {}) or {}
    has_real_exception = bool(
        exc.get("objectId")
        or exc.get("className")
        or exc.get("description")
        or exc.get("value") is not None
    )
    return text in ("Uncaught", "") and not has_real_exception


class ElementHandle:
    __slots__ = ("_object_id", "_tab")

    def __init__(self, tab: Tab, object_id: str) -> None:
        self._tab = tab
        self._object_id = object_id

    @property
    def object_id(self) -> str:
        return self._object_id

    async def _call(
        self,
        function_declaration: str,
        args: list[Any] | None = None,
    ) -> Any:
        params: dict[str, Any] = {
            "objectId": self._object_id,
            "functionDeclaration": function_declaration,
            "returnByValue": True,
            "awaitPromise": True,
        }
        if args is not None:
            params["arguments"] = [{"value": a} for a in args]
        result = await self._tab._cdp.send(
            "Runtime.callFunctionOn", params, session_id=self._tab.session_id
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            if _is_navigation_race(details):
                return None
            raise RuntimeError(f"JS exception: {details.get('text', '')}")
        return result.get("result", {}).get("value")

    async def _call_objects(
        self,
        function_declaration: str,
        args: list[Any] | None = None,
    ) -> list[str]:
        """Call a function that returns an array of elements; return their objectIds."""
        params: dict[str, Any] = {
            "objectId": self._object_id,
            "functionDeclaration": function_declaration,
            "returnByValue": False,
            "awaitPromise": True,
        }
        if args is not None:
            params["arguments"] = [{"value": a} for a in args]
        result = await self._tab._cdp.send(
            "Runtime.callFunctionOn", params, session_id=self._tab.session_id
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            if _is_navigation_race(details):
                return []
            raise RuntimeError(f"JS exception: {details.get('text', '')}")
        array_id = result.get("result", {}).get("objectId")
        if not array_id:
            return []
        props = await self._tab._cdp.send(
            "Runtime.getProperties",
            {"objectId": array_id, "ownProperties": True},
            session_id=self._tab.session_id,
        )
        ids: list[str] = []
        for prop in props.get("result", []):
            if not prop.get("enumerable"):
                continue
            value = prop.get("value", {})
            obj_id = value.get("objectId")
            if obj_id and value.get("subtype") == "node":
                ids.append(obj_id)
        return ids

    # ── interaction ────────────────────────────────────────────────────

    async def click(self) -> None:
        """Click via real Input.dispatchMouseEvent at the element's centre.

        With ``humanly`` active on the tab the cursor curves toward the
        target (cubic Bezier + ease-in-out), the button-press holds for a
        random duration, and the impact point includes pixel-level jitter
        — none of which are visible at the DOM level but all of which
        modern antibots score on. Without humanly, it's an instant click.

        Briefly retries (up to ~1.5s) on a zero-size box — covers elements
        that are visible-soon (CSS transitions, ``display:none`` toggles,
        late layout passes) without the caller having to wait explicitly.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 1.5
        box = None
        while True:
            box = await self._call(
                "function() {"
                " this.scrollIntoView({block:'center', inline:'center'});"
                " const r = this.getBoundingClientRect();"
                " return {x:r.left+r.width/2, y:r.top+r.height/2,"
                "         w:r.width, h:r.height};"
                "}"
            )
            if box and box["w"] > 0 and box["h"] > 0:
                break
            if loop.time() >= deadline:
                raise ValueError("element has zero size — cannot click")
            await asyncio.sleep(0.05)
        behaviour = self._tab._humanly
        x, y = _humanly.jitter_target(behaviour, float(box["x"]), float(box["y"]))
        await _humanly.move(self._tab, x, y)
        await _humanly.pre_action_delay(behaviour)
        await self._tab._send(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )
        await _humanly.click_hold(behaviour)
        await self._tab._send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )
        self._tab._cursor = (x, y)

    async def focus(self) -> None:
        await self._call("function() { this.focus(); }")

    async def type(self, text: str, *, delay_ms: float = 0.0) -> None:
        """Focus the element and insert ``text``.

        ``delay_ms > 0`` pauses that long between characters. With ``humanly``
        active and ``delay_ms == 0`` (the default), the pause is randomised
        per keystroke using the tab's behaviour profile, so keystroke timing
        looks like a real user instead of an even cadence.

        Uses ``Input.insertText`` rather than synthesised ``keyDown``/``keyUp``
        events — more reliable across IME / layout cases. If a caller needs
        actual key codes (shortcuts, Tab key), reach for raw CDP directly.
        """
        await self.focus()
        behaviour = self._tab._humanly
        if delay_ms > 0:
            for ch in text:
                await self._tab._send("Input.insertText", {"text": ch})
                await asyncio.sleep(delay_ms / 1000.0)
        elif behaviour is not None:
            for ch in text:
                await self._tab._send("Input.insertText", {"text": ch})
                await asyncio.sleep(_humanly.type_delay(behaviour))
        else:
            await self._tab._send("Input.insertText", {"text": text})

    async def fill(self, value: str) -> None:
        """Set ``element.value`` and dispatch input + change events.

        Faster than typing for forms where the page only cares about the
        final value. Use ``type`` when per-keystroke handlers matter.
        """
        await self._call(
            "function(v) {"
            " this.focus();"
            " this.value = v;"
            " this.dispatchEvent(new Event('input', {bubbles:true}));"
            " this.dispatchEvent(new Event('change', {bubbles:true}));"
            "}",
            [value],
        )

    async def hover(self) -> None:
        box = await self._call(
            "function() {"
            " this.scrollIntoView({block:'center', inline:'center'});"
            " const r = this.getBoundingClientRect();"
            " return {x:r.left+r.width/2, y:r.top+r.height/2};"
            "}"
        )
        if not box:
            raise ValueError("element not visible")
        behaviour = self._tab._humanly
        x, y = _humanly.jitter_target(behaviour, float(box["x"]), float(box["y"]))
        await _humanly.move(self._tab, x, y)

    # ── reading ────────────────────────────────────────────────────────

    async def text(self) -> str:
        return (await self._call("function(){return this.innerText;}")) or ""

    async def value(self) -> str:
        return (await self._call("function(){return this.value;}")) or ""

    async def attribute(self, name: str) -> str | None:
        result = await self._call("function(n){return this.getAttribute(n);}", [name])
        return None if result is None else str(result)

    async def html(self, *, outer: bool = True) -> str:
        if outer:
            return (await self._call("function(){return this.outerHTML;}")) or ""
        return (await self._call("function(){return this.innerHTML;}")) or ""

    async def is_visible(self) -> bool:
        return bool(
            await self._call(
                "function(){"
                " const r = this.getBoundingClientRect();"
                " const s = window.getComputedStyle(this);"
                " return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';"
                "}"
            )
        )

    async def bounding_box(self) -> dict[str, float] | None:
        result = await self._call(
            "function(){"
            " const r = this.getBoundingClientRect();"
            " return {x:r.left, y:r.top, width:r.width, height:r.height};"
            "}"
        )
        if result is None:
            return None
        return {k: float(v) for k, v in result.items()}

    # ── nested queries ─────────────────────────────────────────────────

    async def query(self, selector: str) -> ElementHandle | None:
        ids = await self._call_objects(
            "function(s){ const r=this.querySelector(s); return r ? [r] : []; }",
            [selector],
        )
        return ElementHandle(self._tab, ids[0]) if ids else None

    async def query_all(self, selector: str) -> list[ElementHandle]:
        ids = await self._call_objects(
            "function(s){ return Array.from(this.querySelectorAll(s)); }",
            [selector],
        )
        return [ElementHandle(self._tab, i) for i in ids]
