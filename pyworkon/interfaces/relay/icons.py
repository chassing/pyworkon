"""Re-exports `pyworkon.icons.DASHBOARD_ICONS` for the relay dashboard.

The actual dict construction lives in `pyworkon.icons` now, not here -- the
strip also needs it and must not depend on this package to get at it (see
`pyworkon/icons.py`'s module docstring). Kept as a thin shim so `relay/app.py`
and this package's own tests keep describing "the relay's view of icons" as
a dedicated surface, without re-deriving anything.
"""

from __future__ import annotations

from pyworkon.icons import DASHBOARD_ICONS

__all__ = ["DASHBOARD_ICONS"]
