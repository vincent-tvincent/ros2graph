"""Run one ordinary ROS observer with an independently scheduled web server."""
import asyncio
from pathlib import Path
import signal
import ssl
import threading

from aiohttp import web

from .graph_observer import GraphObserver
from .rpc_trace import RpcTraceClient
from .server import create_app
from .settings import DEFAULTS, Settings


def cleanup_resources(*callbacks):
    """Attempt every teardown step even if an earlier resource failed to close."""
    errors = []
    for callback in callbacks:
        try:
            callback()
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise errors[0]


async def serve(node, observer, executor, settings):
    loop = asyncio.get_running_loop()
    stopped = asyncio.Event()
    spin_errors = []
    runner = web.AppRunner(create_app(observer, token=settings.read_token()), access_log=None)
    handlers = []
    worker = None

    def spin():
        try:
            executor.spin()
        except Exception as exc:
            from rclpy.executors import ExternalShutdownException
            if not isinstance(exc, ExternalShutdownException):
                spin_errors.append(exc)
        finally:
            loop.call_soon_threadsafe(stopped.set)

    try:
        await runner.setup()
        context = None
        if settings.tls_cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(Path(settings.tls_cert).expanduser()), str(Path(settings.tls_key).expanduser()))
        site = web.TCPSite(runner, settings.host, settings.port, ssl_context=context)
        await site.start()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stopped.set)
            handlers.append(sig)
        worker = threading.Thread(target=spin, name="ros2graph-executor", daemon=True)
        worker.start()
        observer.start()
        host = "[::1]" if settings.host == "::" else settings.host
        node.get_logger().info(f"ros2graph: {'https' if context else 'http'}://{host}:{settings.port}/")
        await stopped.wait()
    finally:
        errors = []
        for close_async in (runner.cleanup, lambda: asyncio.to_thread(observer.close)):
            try:
                await close_async()
            except Exception as exc:
                errors.append(exc)
        try:
            cleanup_resources(
                lambda: executor.shutdown(timeout_sec=5.),
                lambda: worker.join(timeout=5.) if worker is not None else None,
                *(lambda sig=sig: loop.remove_signal_handler(sig) for sig in handlers),
            )
        except Exception as exc:
            errors.append(exc)
        if errors:
            raise errors[0]
    if spin_errors:
        raise spin_errors[0]


def main(args=None):
    import rclpy
    from rcl_interfaces.msg import ParameterDescriptor
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions

    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = None
    observer = None
    try:
        node = Node("ros2graph")
        values = {}
        for name, default in DEFAULTS.items():
            values[name] = node.declare_parameter(name, default, ParameterDescriptor(read_only=True)).value
        settings = Settings(**values)
        provider = RpcTraceClient(str(Path(settings.rpc_trace_socket).expanduser())) if settings.rpc_trace_socket else None
        observer = GraphObserver(node, settings.observer_config(), rpc_provider=provider)
        executor = MultiThreadedExecutor(num_threads=2)
        executor.add_node(node)
        asyncio.run(serve(node, observer, executor, settings))
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_resources(
            lambda: observer.close() if observer is not None else None,
            lambda: node.destroy_node() if node is not None else None,
            lambda: rclpy.shutdown() if rclpy.ok() else None,
        )


if __name__ == "__main__":
    main()
