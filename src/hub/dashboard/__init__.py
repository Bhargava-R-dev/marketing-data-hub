"""Read-only 'what's in my hub' dashboard — grouped by source, showing every
brand's Google login, date range, and row count, plus per-source sync status.

Two entry points sharing the same routes/data:
- `hub dashboard` — standalone, works anytime independent of the wizard.
- mounted inside the setup wizard as a same-process recap after first sync.
"""
from hub.dashboard.app import create_dashboard_app, dashboard_router, run_dashboard  # noqa: F401
from hub.dashboard.data import build_dashboard  # noqa: F401
