"""Ratchet: a bug report in, a receipt out.

The engine is S17Code. Ratchet imports it rather than reimplementing any part of
the coding loop; everything here is orchestration, streaming and the receipt.

S17Code is not on PyPI. Either run Ratchet inside S17Code's own environment, or
point ``S17CODE_ROOT`` at the checkout and this module puts it on ``sys.path``.
"""
from __future__ import annotations

import os
import sys

_S17CODE_ROOT = os.getenv("S17CODE_ROOT", "").strip()
if _S17CODE_ROOT and _S17CODE_ROOT not in sys.path:
    sys.path.insert(0, _S17CODE_ROOT)

__all__ = ["proof", "runner"]
