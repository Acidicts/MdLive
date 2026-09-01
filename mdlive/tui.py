import asyncio
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Header, Footer, Static
from textual import on

from mdlive.server import MDLiveServer

CSS = """
Screen {
    background: $surface;
}
#title {
    dock: top;
    padding: 0 1;
    text-style: bold;
    color: $accent;
}
#status {
    dock: top;
    padding: 0 1;
    color: $text-muted;
}
#routes_table {
    height: 1fr;
    margin: 0 1;
}
Footer {
    dock: bottom;
}
"""

BINDINGS = [
    Binding("q", "quit", "Quit"),
]


class MDLiveTUI(App):
    CSS = CSS
    BINDINGS = BINDINGS

    def __init__(self, server: MDLiveServer, host: str = "127.0.0.1", port: int = 8000):
        super().__init__()
        self.server = server
        self.host = host
        self.port = port
        self._uvicorn_server = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(f"mdlive  {self.host}:{self.port}", id="title")
        yield Static("starting...", id="status")
        yield DataTable(id="routes_table")
        yield Footer()

    async def on_mount(self):
        table = self.query_one("#routes_table")
        table.add_columns("Route", "File", "Connections", "Last Updated")
        table.cursor_type = "row"

        self.set_interval(1.0, self._refresh_stats)

        from uvicorn import Server as UvicornServer, Config

        config = Config(
            self.server.app,
            host=self.host,
            port=self.port,
            log_level="error",
        )
        self._uvicorn_server = UvicornServer(config)
        asyncio.create_task(self._run_server())

    async def _run_server(self):
        await self._uvicorn_server.serve()
        self.query_one("#status").update("stopped")

    def _refresh_stats(self):
        if not self._uvicorn_server or not self._uvicorn_server.started:
            return

        self.query_one("#status").update(
            f"listening on {self.host}:{self.port}   |   "
            f"{len(self.server.routes)} route(s)   |   "
            f"q to quit"
        )

        table = self.query_one("#routes_table")
        table.clear()

        for path in sorted(self.server.routes):
            entry = self.server.routes[path]
            file_name = entry["file"].name
            conns = str(entry["connections"])
            last = entry["last_updated"]
            import time
            delta = time.time() - last
            if delta < 1:
                updated = "now"
            elif delta < 60:
                updated = f"{int(delta)}s ago"
            elif delta < 3600:
                updated = f"{int(delta // 60)}m ago"
            else:
                updated = f"{int(delta // 3600)}h ago"
            table.add_row(path, file_name, conns, updated)

    async def action_quit(self):
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        self.exit()
