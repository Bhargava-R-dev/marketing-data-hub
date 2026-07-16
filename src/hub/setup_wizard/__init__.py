"""Browser-based setup wizard — the non-technical onboarding path.

`hub setup` serves a single local page where a user connects Google logins,
ticks the properties/sites they want, pastes ad-platform tokens, runs a first
sync, and copies the Claude MCP snippet. Everything binds to 127.0.0.1 and
every state-changing call requires the per-run token embedded in the page, so
random websites can't poke the endpoints while the wizard is open.
"""
from hub.setup_wizard.app import create_setup_app, run_setup  # noqa: F401
