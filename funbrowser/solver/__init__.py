"""Solver — auto-solve captchas through the funsolver.com API.

Scope (M3): Cloudflare Turnstile. M4 adds the rest of the major captcha
families.
"""

from __future__ import annotations

from .bridge import apply_solver
from .client import FunSolverClient, FunSolverError

__all__ = ["FunSolverClient", "FunSolverError", "apply_solver"]
