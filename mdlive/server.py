import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
from watchfiles import awatch

from mdlive import md_block

PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ max-width: 800px; margin: 2rem auto; font-family: sans-serif; line-height: 1.6; padding: 0 1rem; }}
  pre {{ background: #f4f4f4; padding: 1rem; overflow-x: auto; }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; }}
  li input[type="checkbox"] {{ margin-right: 0.4rem; transform: scale(1.15); vertical-align: middle; }}
  blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 1rem; color: #555; }}
  table {{ border-collapse: collapse; }}
  th, td {{ border: 1px solid #ccc; padding: 0.3rem 0.6rem; }}
  img {{ max-width: 100%; }}
  hr {{ border: none; border-top: 1px solid #ccc; margin: 1.5rem 0; }}
</style>
</head>
<body>
<div id="content">{body}</div>
<script>
(function() {{
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(proto + "//" + location.host + "/ws?path={ws_path}");
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


def _relative_time(ts: float) -> str:
    delta = time.time() - ts
    if delta < 1:
        return "just now"
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    return f"{int(delta // 3600)}h ago"


class MDLiveServer:
    def __init__(self, default_md_path: str):
        self.routes: dict[str, dict] = {}
        self.ws_clients: dict[str, set[WebSocket]] = {}
        self.watch_tasks: dict[str, asyncio.Task] = {}

        default_path = Path(default_md_path).resolve()
        if not default_path.exists():
            raise FileNotFoundError(default_path)
        self._add_route_data("/", default_path)

        self.app = Starlette(
            routes=[
                Route("/api/add", self.api_add, methods=["POST"]),
                Route("/api/remove", self.api_remove, methods=["DELETE"]),
                Route("/api/stats", self.api_stats),
                WebSocketRoute("/ws", self.ws_endpoint),
                Route("/", self.index),
                Route("/{path:path}", self.serve_file),
            ],
            lifespan=self.lifespan,
        )

    def _add_route_data(self, url_path: str, md_file: Path) -> None:
        normalized = "/" + url_path.strip("/")
        self.routes[normalized] = {
            "file": md_file,
            "last_updated": time.time(),
            "connections": 0,
        }
        self.ws_clients[normalized] = set()

    def _remove_route_data(self, url_path: str) -> None:
        normalized = "/" + url_path.strip("/")
        self.routes.pop(normalized, None)
        self.ws_clients.pop(normalized, None)
        task = self.watch_tasks.pop(normalized, None)
        if task:
            task.cancel()

    def render(self, md_file: Path) -> str:
        text = md_file.read_text(encoding="utf-8")
        body = md_block.render(text)
        return PAGE_TEMPLATE.format(title=md_file.name, body=body, ws_path="/")

    def _resolve_route(self, path: str) -> Path | None:
        normalized = "/" + path.strip("/")
        entry = self.routes.get(normalized)
        if entry:
            return entry["file"]
        return None

    async def index(self, request: Request):
        entry = self.routes.get("/")
        if not entry:
            return HTMLResponse("<h1>No default route</h1>", status_code=404)
        try:
            html = self.render(entry["file"])
        except Exception as e:
            return HTMLResponse(f"<h1>Error rendering: {e}</h1>", status_code=500)
        return HTMLResponse(html)

    async def serve_file(self, request: Request):
        path = request.path_params["path"]
        md_file = self._resolve_route(path)
        if not md_file:
            return HTMLResponse("<h1>Not found</h1>", status_code=404)
        try:
            html = self.render(md_file)
        except Exception as e:
            return HTMLResponse(f"<h1>Error rendering: {e}</h1>", status_code=500)
        return HTMLResponse(html)

    async def ws_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        route_path = websocket.query_params.get("path", "/")
        normalized = "/" + route_path.strip("/")

        if normalized not in self.routes:
            await websocket.close(code=4004, reason="Unknown route")
            return

        self.ws_clients.setdefault(normalized, set()).add(websocket)
        self.routes[normalized]["connections"] = len(self.ws_clients[normalized])
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            self.ws_clients.get(normalized, set()).discard(websocket)
            if normalized in self.routes:
                self.routes[normalized]["connections"] = len(
                    self.ws_clients.get(normalized, set())
                )

    async def broadcast_reload(self, route_path: str):
        clients = self.ws_clients.get(route_path, set())
        dead = set()
        for ws in clients:
            try:
                await ws.send_text("reload")
            except Exception:
                dead.add(ws)
        clients -= dead

    async def _watch_route(self, route_path: str, md_file: Path):
        try:
            async for changes in awatch(md_file.parent):
                for _, changed_path in changes:
                    if Path(changed_path).resolve() == md_file:
                        self.routes[route_path]["last_updated"] = time.time()
                        await self.broadcast_reload(route_path)
                        break
        except asyncio.CancelledError:
            return

    async def api_add(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        file_path = body.get("file")
        url_path = body.get("path")
        if not file_path or not url_path:
            return JSONResponse(
                {"error": "Missing 'file' or 'path'"}, status_code=400
            )

        normalized = "/" + url_path.strip("/")
        if normalized in self.routes:
            return JSONResponse(
                {"error": f"Route {normalized} already exists"},
                status_code=409,
            )

        md_file = Path(file_path).resolve()
        if not md_file.exists():
            return JSONResponse(
                {"error": f"File not found: {file_path}"}, status_code=400
            )

        self._add_route_data(url_path, md_file)
        task = asyncio.create_task(self._watch_route(normalized, md_file))
        self.watch_tasks[normalized] = task

        return JSONResponse({"ok": True, "path": normalized, "file": str(md_file)})

    async def api_remove(self, request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        url_path = body.get("path")
        if not url_path:
            return JSONResponse({"error": "Missing 'path'"}, status_code=400)

        normalized = "/" + url_path.strip("/")
        if normalized not in self.routes:
            return JSONResponse(
                {"error": f"Route {normalized} not found"}, status_code=404
            )
        if normalized == "/":
            return JSONResponse(
                {"error": "Cannot remove the default route '/'"}, status_code=400
            )

        self._remove_route_data(url_path)
        return JSONResponse({"ok": True, "path": normalized})

    async def api_stats(self, request: Request):
        stats = {}
        for path, entry in self.routes.items():
            stats[path] = {
                "file": str(entry["file"]),
                "connections": entry["connections"],
                "last_updated": _relative_time(entry["last_updated"]),
            }
        return JSONResponse(stats)

    async def _start_watches(self):
        for route_path, entry in self.routes.items():
            task = asyncio.create_task(
                self._watch_route(route_path, entry["file"])
            )
            self.watch_tasks[route_path] = task

    @asynccontextmanager
    async def lifespan(self, app):
        await self._start_watches()
        try:
            yield
        finally:
            for task in self.watch_tasks.values():
                task.cancel()
