import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import markdown
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
from watchfiles import awatch

PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ max-width: 800px; margin: 2rem auto; font-family: sans-serif; line-height: 1.6; padding: 0 1rem; }}
  pre {{ background: #f4f4f4; padding: 1rem; overflow-x: auto; }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; }}
</style>
</head>
<body>
<div id="content">{body}</div>
<script>
(function() {{
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(proto + "//" + location.host + "/ws");
  ws.onmessage = (event) => {{
    if (event.data === "reload") {{
      location.reload();
    }}
  }};
  ws.onclose = () => {{
    setTimeout(() => location.reload(), 1000);
  }};
}})();
</script>
</body>
</html>
"""


class MDLiveServer:
    def __init__(self, md_path: str):
        self.md_path = Path(md_path).resolve()
        if not self.md_path.exists():
            raise FileNotFoundError(self.md_path)
        self.clients: set[WebSocket] = set()
        self.app = Starlette(
            routes=[
                Route("/", self.index),
                WebSocketRoute("/ws", self.ws_endpoint),
            ],
            lifespan=self.lifespan,
        )

    def render(self) -> str:
        text = self.md_path.read_text(encoding="utf-8")
        body = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "toc", "codehilite"],
        )
        return PAGE_TEMPLATE.format(title=self.md_path.name, body=body)

    async def index(self, request):
        return HTMLResponse(self.render())

    async def ws_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        self.clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            self.clients.discard(websocket)

    async def broadcast_reload(self):
        dead = set()
        for ws in self.clients:
            try:
                await ws.send_text("reload")
            except Exception:
                dead.add(ws)
        self.clients -= dead

    async def watch_loop(self):
        async for changes in awatch(self.md_path.parent):
            for _, path in changes:
                if Path(path).resolve() == self.md_path:
                    await self.broadcast_reload()
                    break

    @asynccontextmanager
    async def lifespan(self, app):
        task = asyncio.create_task(self.watch_loop())
        try:
            yield
        finally:
            task.cancel()
