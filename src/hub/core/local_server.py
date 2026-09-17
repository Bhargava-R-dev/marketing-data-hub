"""Local UI lifecycle: only open a browser after successful server startup."""
from __future__ import annotations

import asyncio
import time
import webbrowser

import uvicorn


class LocalServer(uvicorn.Server):
    def __init__(self, config, *, open_browser: bool, idle_minutes: int = 0):
        super().__init__(config)
        self.open_browser = open_browser
        self.idle_minutes = idle_minutes
        self.watchdog = None

    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        if not self.started or self.should_exit:
            return
        if self.open_browser:
            webbrowser.open(f"http://127.0.0.1:{self.config.port}")
        state = getattr(self.config.app.state, "hub", None)
        if state is not None:
            self.watchdog = asyncio.create_task(self._watch(state))

    async def _watch(self, state):
        while not self.should_exit:
            await asyncio.sleep(1)
            if state["shutdown"] or (self.idle_minutes > 0 and
                    time.time() - state["last_seen"] > self.idle_minutes * 60):
                self.should_exit = True

    async def shutdown(self, sockets=None):
        if self.watchdog is not None:
            self.watchdog.cancel()
        await super().shutdown(sockets=sockets)


def serve_local(app, port: int, *, open_browser: bool, idle_minutes: int = 0):
    server = LocalServer(uvicorn.Config(app, host="127.0.0.1", port=port,
                                       log_level="warning"),
                         open_browser=open_browser, idle_minutes=idle_minutes)
    server.run()
