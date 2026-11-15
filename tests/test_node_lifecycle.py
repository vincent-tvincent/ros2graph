import asyncio
from types import SimpleNamespace
import pytest

from ros2graph import node
from ros2graph.settings import Settings


def test_cleanup_attempts_all_resources_before_reporting_first_error():
    calls = []
    def fails():
        calls.append("observer")
        raise RuntimeError("observer close failed")
    with pytest.raises(RuntimeError, match="observer close failed"):
        node.cleanup_resources(fails, lambda: calls.append("node"), lambda: calls.append("context"))
    assert calls == ["observer", "node", "context"]


@pytest.mark.parametrize("failed", ["http", "observer"])
def test_web_or_observer_cleanup_failure_still_stops_executor(monkeypatch, failed):
    calls = []
    class Runner:
        def __init__(self, *args, **kwargs): pass
        async def setup(self): pass
        async def cleanup(self):
            calls.append("http")
            if failed == "http": raise RuntimeError("http")
    class Site:
        def __init__(self, *args, **kwargs): pass
        async def start(self): pass
    class Observer:
        def start(self): pass
        def close(self):
            calls.append("observer")
            if failed == "observer": raise RuntimeError("observer")
    class Executor:
        def spin(self): pass
        def shutdown(self, **kwargs): calls.append("executor")
    monkeypatch.setattr(node.web, "AppRunner", Runner)
    monkeypatch.setattr(node.web, "TCPSite", Site)
    logger = SimpleNamespace(info=lambda _: None)
    with pytest.raises(RuntimeError, match=failed):
        asyncio.run(node.serve(SimpleNamespace(get_logger=lambda: logger), Observer(), Executor(), Settings()))
    assert calls == ["http", "observer", "executor"]
