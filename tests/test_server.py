import asyncio
import json
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
import pytest

from ros2graph.server import ASSETS, WEB_ROOT, create_app
from ros2graph.settings import Settings


class Observer:
    def __init__(self):
        self.requests = []

    def snapshot(self):
        return {"schema_version": 1, "nodes": [{"id": "node:/generic/producer"}], "topics": []}

    def watch(self, body):
        if body.get("operation") not in ("acquire", "renew", "release"):
            raise ValueError("Watch operation must be acquire, renew or release")
        self.requests.append(body)
        return {"accepted": True, "lease_id": "test-lease"}

    def sample(self, body):
        if not isinstance(body.get("topic"), str):
            raise ValueError("A fully qualified topic name is required")
        self.requests.append(body)
        return {"accepted": True}


def test_http_contract_auth_origin_validation_and_assets():
    async def run():
        observer = Observer()
        client = TestClient(TestServer(create_app(observer, token="example-test-token")))
        await client.start_server()
        try:
            assert (await client.get("/healthz")).status == 200
            assert (await client.get("/")).status == 200
            for asset in ASSETS:
                result = await client.get("/assets/" + asset)
                assert result.status == 200
                assert result.headers["X-Content-Type-Options"] == "nosniff"
                assert result.headers["Cache-Control"] == "no-store"
            assert (await client.get("/assets/settings.py")).status == 404
            assert (await client.get("/api/graph")).status == 401
            assert (await client.post("/api/graph/watch", json={"operation": "acquire"})).status == 401
            assert observer.requests == []
            auth = {"Authorization": "Bearer example-test-token"}
            result = await client.get("/api/graph", headers=auth)
            assert (await result.json())["nodes"][0]["id"] == "node:/generic/producer"
            assert "example-test-token" not in await result.text()
            bad_origin = {**auth, "Origin": "https://another.example"}
            assert (await client.post("/api/graph/watch", headers=bad_origin, json={"operation": "acquire"})).status == 403
            assert observer.requests == []
            for body in ([], None, 1, "text", {"operation": "unknown"}):
                result = await client.post("/api/graph/watch", headers={**auth, "Content-Type": "application/json"}, data=json.dumps(body))
                assert result.status == 400
            result = await client.post("/api/graph/watch", headers=auth, json={"operation": "acquire", "client_id": "demo"})
            assert (await result.json())["accepted"]
            assert (await client.post("/api/graph/sample", headers=auth, json={"topic": "/generic/topic"})).status == 200
            assert (await client.post("/api/graph/watch", headers=auth, data="not-json")).status == 415
            assert (await client.post("/api/graph/watch", headers={**auth, "Content-Type": "application/json"}, data="{" )).status == 400
            assert (await client.post("/api/graph/watch", headers=auth, json={"operation": "acquire", "padding": "x" * 17000})).status == 413
            assert (await client.post("/api/operate", headers=auth, json={})).status == 404
        finally:
            await client.close()
    asyncio.run(run())


def test_anonymous_local_api_and_same_origin_watch_work():
    async def run():
        observer = Observer()
        client = TestClient(TestServer(create_app(observer)))
        await client.start_server()
        try:
            assert (await client.get("/api/graph")).status == 200
            origin = str(client.make_url("/")).rstrip("/")
            result = await client.post("/api/graph/watch", headers={"Origin": origin}, json={"operation": "acquire"})
            assert result.status == 200
            assert len(observer.requests) == 1
        finally:
            await client.close()
    asyncio.run(run())


def test_web_assets_are_installed_relative_to_package():
    assert (WEB_ROOT / "index.html").is_file()
    for name in ASSETS:
        assert (WEB_ROOT / name).is_file()


@pytest.mark.parametrize("values", [
    {"port": 0}, {"port": True}, {"watch_max_topics": 0}, {"watch_max_clients": 9},
    {"refresh_s": float("nan")}, {"watch_lease_s": 2.}, {"host": ""},
    {"tls_cert": "cert.pem"}, {"tls_key": "key.pem"}, {"watch_enabled": 1},
])
def test_invalid_settings_fail_before_listening(values):
    with pytest.raises(ValueError):
        Settings(**values)


def test_topic_capacity_and_optional_token_are_configurable(tmp_path):
    assert Settings(watch_max_topics=512).observer_config()["watch"]["max_topics"] == 512
    assert Settings().read_token() is None
    token_file = tmp_path / "viewer-token"
    token_file.write_text("sample-token\n")
    assert Settings(token_file=str(token_file)).read_token() == "sample-token"
    token_file.write_text(" ")
    with pytest.raises(ValueError):
        Settings(token_file=str(token_file)).read_token()
