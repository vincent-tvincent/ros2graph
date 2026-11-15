"""Small HTTP adapter. No robot command, filesystem browser or payload API."""
import asyncio
import hmac
import json
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from . import __version__

ASSETS = frozenset(("app.js", "client.js", "graph.js", "styles.css"))
WEB_ROOT = Path(__file__).with_name("web")


def response(value, *, status=200):
    return web.json_response(value, status=status, dumps=lambda obj: json.dumps(obj, allow_nan=False))


def create_app(observer, *, token=None, web_root=WEB_ROOT):
    """Construct a testable application around any GraphObserver-compatible object."""
    @web.middleware
    async def boundary(request, handler):
        try:
            if request.path.startswith("/api/"):
                if token is not None:
                    supplied = request.headers.get("Authorization", "")
                    if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
                        return response({"error": "Authentication required", "code": "unauthorized"}, status=401)
                # Browser cross-origin pages cannot create subscriptions on this
                # viewer. Non-browser clients need no Origin header.
                if request.method == "POST" and request.headers.get("Origin"):
                    origin = urlsplit(request.headers["Origin"])
                    if origin.netloc != request.host or origin.scheme != request.scheme:
                        return response({"error": "Cross-origin requests are not accepted"}, status=403)
            return await handler(request)
        except (ValueError, KeyError) as exc:
            return response({"schema_version": 1, "accepted": False, "error": str(exc), "reason": str(exc)}, status=400)

    async def prepare(request, result):
        result.headers["Cache-Control"] = "no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )

    async def index(request):
        return web.FileResponse(Path(web_root) / "index.html")

    async def asset(request):
        name = request.match_info["name"]
        if name not in ASSETS:
            raise web.HTTPNotFound()
        return web.FileResponse(Path(web_root) / name)

    async def graph(request):
        return response(await asyncio.to_thread(observer.snapshot))

    async def body(request):
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="Use application/json")
        value = await request.json()
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    async def watch(request):
        return response(await asyncio.to_thread(observer.watch, await body(request)))

    async def sample(request):
        return response(await asyncio.to_thread(observer.sample, await body(request)))

    async def health(request):
        return response({"application": "ros2graph", "version": __version__, "status": "ready"})

    app = web.Application(middlewares=[boundary], client_max_size=16384)
    app.on_response_prepare.append(prepare)
    app.router.add_get("/", index)
    app.router.add_get("/assets/{name}", asset)
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/graph", graph)
    app.router.add_post("/api/graph/watch", watch)
    app.router.add_post("/api/graph/sample", sample)
    return app
