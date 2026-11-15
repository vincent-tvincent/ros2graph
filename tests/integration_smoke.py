#!/usr/bin/env python3
"""Exercise standalone discovery, watch, sampling and optional RPC tracing.

Run through run_ros_smoke.sh from a sourced ROS/ros2graph installation. This
launches only the generic demo, observer and optional metadata collector.
It never contacts an application service directly or opens a hardware device.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


PHASES = ('request_sent', 'request_received', 'response_sent', 'response_received')
PREFIX = '/ros2graph_demo'


class Smoke:
    def __init__(self, port, output, timeout):
        self.port = port
        self.base_url = f'http://127.0.0.1:{port}'
        self.output = output
        self.timeout = timeout
        self.processes = []
        self.expected_running = set()
        self.trace_sessions = set()
        self.trace_directories = set()
        self.lease = None
        self.next_renew = 0.
        self.report = {'domain': os.environ.get('ROS_DOMAIN_ID'), 'port': port,
                       'hardware_free': True, 'phases': {}, 'cleanup': {}}

    def start(self, label, executable, *args, domain=None):
        return self.start_command(label, ['ros2', 'run', 'ros2graph', executable, *args], domain=domain)

    def start_command(self, label, command, *, domain=None):
        log = (self.output / f'{label}.log').open('w')
        environment = dict(os.environ)
        if domain is not None:
            environment['ROS_DOMAIN_ID'] = str(domain)
        child = subprocess.Popen(command,
                                 stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, env=environment)
        self.processes.append((label, child, log))
        self.expected_running.add(child)
        return child

    def stop(self, child):
        self.expected_running.discard(child)
        def group_alive():
            try:
                os.killpg(child.pid, 0)
                return True
            except ProcessLookupError:
                return False

        if group_alive():
            os.killpg(child.pid, signal.SIGINT)
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=3)
        deadline = time.monotonic() + 3
        while group_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if group_alive():
            os.killpg(child.pid, signal.SIGKILL)
            raise AssertionError(f'Child process group {child.pid} did not stop cleanly')
        return child.returncode

    def request(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=data,
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.load(response)

    def wait(self, predicate, description):
        deadline = time.monotonic() + self.timeout
        last_error = None
        while time.monotonic() < deadline:
            for label, child, _log in self.processes:
                if child in self.expected_running and child.poll() is not None:
                    raise AssertionError(
                        f'{label} exited unexpectedly with code {child.returncode} while waiting for '
                        f'{description}; see {self.output / (label + ".log")}')
            try:
                value = predicate()
                last_error = None
                if value:
                    return value
            except (ConnectionError, OSError, urllib.error.URLError) as exc:
                last_error = str(exc)
            time.sleep(.2)
        raise AssertionError(f'Timed out: {description}; last transport error: {last_error}')

    def graph(self):
        if self.lease is not None and time.monotonic() >= self.next_renew:
            renewed = self.request('/api/graph/watch', {'operation': 'renew', 'lease_id': self.lease})
            assert renewed['accepted'], renewed
            self.next_renew = time.monotonic() + 4
        return self.request('/api/graph')

    def watch(self):
        self.wait(lambda: self.request('/api/graph'), 'observer HTTP startup')
        result = self.request('/api/graph/watch', {'operation': 'acquire', 'client_id': str(uuid.uuid4())})
        assert result['accepted'], result
        self.lease = result['lease_id']
        self.next_renew = time.monotonic() + 4

    def release(self):
        if self.lease is not None:
            result = self.request('/api/graph/watch', {'operation': 'release', 'lease_id': self.lease})
            assert result['accepted'], result
            self.lease = None
            self.wait(lambda: not self.request('/api/graph')['watch']['active'], 'watch lease release')

    @staticmethod
    def row(graph, section, name):
        return next((row for row in graph[section] if row['name'] == name), None)

    def listener_closed(self):
        with socket.socket() as check:
            check.settimeout(.2)
            return check.connect_ex(('127.0.0.1', self.port)) != 0

    def startup_variants(self):
        from ament_index_python.packages import get_package_share_directory
        params = Path(get_package_share_directory('ros2graph')) / 'config/ros2graph.yaml'
        variants = {
            'launch_startup': ['ros2', 'launch', 'ros2graph', 'ros2graph.launch.py', f'port:={self.port}'],
            'params_file_startup': ['ros2', 'run', 'ros2graph', 'ros2graph', '--ros-args',
                                    '--params-file', str(params), '-p', f'port:={self.port}'],
        }
        for label, command in variants.items():
            child = self.start_command(label, command)
            health = self.wait(lambda: self.request('/healthz'), label + ' health endpoint')
            assert health['application'] == 'ros2graph' and health['status'] == 'ready', health
            graph = self.request('/api/graph')
            assert graph['schema_version'] == 1
            code = self.stop(child)
            self.wait(self.listener_closed, label + ' listener shutdown')
            self.report['phases'][label] = {'health': health, 'exit_code': code,
                                          'empty_rpc_socket_accepted': True}

    def topic_ready(self):
        graph = self.graph()
        topic = self.row(graph, 'topics', PREFIX + '/chatter')
        action = self.row(graph, 'actions', PREFIX + '/fibonacci')
        service = self.row(graph, 'services', PREFIX + '/trigger')
        if topic and service and action and (topic['activity'].get('messages') or 0) >= 5:
            assert topic['types'] == ['std_msgs/msg/String'], topic
            assert service['types'] == ['std_srvs/srv/Trigger'], service
            assert action['types'] == ['example_interfaces/action/Fibonacci'], action
            return graph
        return None

    def no_trace_phase(self):
        demo = self.start('attach-demo', 'demo_graph')
        # The application is already running when the observer attaches.
        time.sleep(.5)
        observer = self.start('attach-observer', 'ros2graph', '--ros-args',
                              '-p', 'host:=127.0.0.1', '-p', f'port:={self.port}')
        self.watch()
        graph = self.wait(self.topic_ready, 'existing graph discovery and measured topic receipts')
        service = self.row(graph, 'services', PREFIX + '/trigger')
        assert service['activity']['messages'] is None, service
        assert service['activity']['state'] in ('unavailable', 'inactive'), service
        sample = self.request('/api/graph/sample', {'topic': PREFIX + '/chatter', 'duration_s': 1.})
        assert sample['accepted'], sample

        def sampled():
            value = self.graph()
            traffic = self.row(value, 'topics', PREFIX + '/chatter')['traffic']
            return value if traffic['state'] == 'complete' and traffic['messages'] > 0 else None

        graph = self.wait(sampled, 'bounded topic sample completion')
        self.report['phases']['attach_without_trace'] = {
            'topic_messages': self.row(graph, 'topics', PREFIX + '/chatter')['activity']['messages'],
            'sample_messages': self.row(graph, 'topics', PREFIX + '/chatter')['traffic']['messages'],
            'rpc_state': service['activity']['state'],
        }
        (self.output / 'attach-graph.json').write_text(json.dumps(graph, indent=2))
        self.release()
        self.stop(observer)
        assert demo.poll() is None, 'Stopping the observer stopped the independent application'
        self.report['phases']['attach_without_trace']['application_survived_observer'] = True
        self.stop(demo)

    def traced_phase(self):
        from ros2graph.rpc_trace import RpcTraceClient
        trace_socket = str(self.output / 'rpc.sock')
        collector = self.start('trace-collector', 'rpc_trace_collector',
                               '--socket', trace_socket, '--parent-pid', str(os.getpid()), '--interval', '.25')
        client = RpcTraceClient(trace_socket)
        try:
            def ready():
                assert collector.poll() is None, 'RPC collector exited; inspect trace-collector.log'
                return client.snapshot().get('trace_ready')
            self.wait(ready, 'collector armed before application node initialization')
        finally:
            client.close()
        for marker in Path('/tmp').glob('ros2graph-rpc-trace-*/owner.json'):
            try:
                owner = json.loads(marker.read_text())
                if os.getpgid(owner['pid']) == collector.pid:
                    self.trace_sessions.add(owner['session'])
                    self.trace_directories.add(marker.parent)
            except (OSError, KeyError, ValueError):
                continue
        assert self.trace_sessions, 'Collector has no test-owned LTTng session marker'
        demo = self.start('trace-demo', 'demo_graph')
        other_domain = int(os.environ.get('ROS2GRAPH_COLLISION_DOMAIN', '197'))
        assert other_domain != int(os.environ['ROS_DOMAIN_ID']), 'Collision test needs a different ROS domain'
        collision_demo = self.start('other-domain-demo', 'demo_graph', domain=other_domain)
        observer = self.start('trace-observer', 'ros2graph', '--ros-args',
                              '-p', 'host:=127.0.0.1', '-p', f'port:={self.port}',
                              '-p', f'rpc_trace_socket:={trace_socket}')
        self.watch()

        def measured():
            graph = self.topic_ready()
            if not graph:
                return None
            service = self.row(graph, 'services', PREFIX + '/trigger')['activity']
            action = self.row(graph, 'actions', PREFIX + '/fibonacci')['activity']
            phases = [service] + [action.get('rpc', {}).get(name, {}) for name in ('goal', 'cancel', 'result')]
            if all(all((value.get('channels', {}).get(phase, {}).get('messages') or 0) > 0
                       for phase in PHASES) for value in phases):
                if (action['feedback'].get('messages') or 0) > 0 and (action['status'].get('messages') or 0) > 0:
                    return graph
            return None

        graph = self.wait(measured, 'all four service and goal/cancel/result RPC phases plus action feedback')
        service = self.row(graph, 'services', PREFIX + '/trigger')['activity']
        action = self.row(graph, 'actions', PREFIX + '/fibonacci')['activity']
        assert service['messages'] == service['requests']['messages'] + service['responses']['messages']
        expected_nodes = {'node:' + PREFIX + '/server', 'node:' + PREFIX + '/client'}
        assert {endpoint['node_id'] for endpoint in service['endpoints']} == expected_nodes
        observed_endpoints = service['endpoints'] + [endpoint for operation in ('goal', 'cancel', 'result')
            for endpoint in action['rpc'][operation]['endpoints']]
        assert observed_endpoints and all(os.getpgid(endpoint['pid']) == demo.pid for endpoint in observed_endpoints), \
            'Graph includes a same-named endpoint from the other ROS domain'
        client = RpcTraceClient(trace_socket)
        try:
            def captured_both_domains():
                records = client.snapshot().get('endpoints', [])
                groups = set()
                for endpoint in records:
                    if endpoint.get('node_fqn') in (PREFIX + '/server', PREFIX + '/client'):
                        try:
                            groups.add(os.getpgid(endpoint['pid']))
                        except ProcessLookupError:
                            pass
                return {demo.pid, collision_demo.pid}.issubset(groups)
            self.wait(captured_both_domains, 'trace capture of both same-named domain196/197 demo instances')
        finally:
            client.close()
        assert graph['rpc_trace']['state'] == 'ready', graph['rpc_trace']
        assert not graph['rpc_trace']['counts_lower_bound'], graph['rpc_trace']
        assert graph['rpc_trace']['payload_export'] is False
        assert all(value == 0 for value in graph['rpc_trace']['loss'].values()), graph['rpc_trace']
        unmeasured = [row['name'] for row in graph['services'] if row['activity']['state'] != 'watching']
        assert not unmeasured, unmeasured
        self.report['phases']['traced'] = {
            'services': len(graph['services']), 'actions': len(graph['actions']),
            'service_phases': {name: service['channels'][name]['messages'] for name in PHASES},
            'action_phases': {operation: {name: action['rpc'][operation]['channels'][name]['messages']
                              for name in PHASES} for operation in ('goal', 'cancel', 'result')},
            'feedback_messages': action['feedback']['messages'],
            'status_messages': action['status']['messages'],
            'cross_domain': {'observer_domain': int(os.environ['ROS_DOMAIN_ID']),
                             'collision_domain': other_domain, 'both_captured': True,
                             'foreign_endpoints_in_graph': 0},
            'rpc_trace': graph['rpc_trace'],
        }
        (self.output / 'traced-graph.json').write_text(json.dumps(graph, indent=2))
        self.release()
        self.stop(observer)
        assert demo.poll() is None
        self.stop(demo)
        self.stop(collision_demo)
        self.stop(collector)
        assert not Path(trace_socket).exists(), 'Collector left its Unix socket behind'
        listed = subprocess.run(['lttng', 'list'], capture_output=True, text=True, timeout=5, check=True)
        remaining = [name for name in self.trace_sessions if name in listed.stdout]
        self.report['cleanup']['trace_sessions_remaining'] = remaining
        assert not remaining, remaining
        assert not any(path.exists() for path in self.trace_directories), 'Collector left its owned snapshots behind'

    def cleanup(self):
        if self.lease is not None:
            try:
                self.release()
            except Exception:
                self.lease = None
        for label, process, log in reversed(self.processes):
            try:
                self.report['cleanup'][label] = self.stop(process)
            except Exception as exc:
                self.report['cleanup'][label] = {'error': str(exc)}
            finally:
                log.close()
        self.report['cleanup']['listener_closed'] = self.listener_closed()
        self.report['cleanup']['all_children_stopped'] = all(p.poll() is not None for _, p, _ in self.processes)
        if (not self.report['cleanup']['listener_closed'] or not self.report['cleanup']['all_children_stopped']
                or any(isinstance(value, dict) and 'error' in value for value in self.report['cleanup'].values())):
            self.report['passed'] = False
        (self.output / 'report.json').write_text(json.dumps(self.report, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18080)
    parser.add_argument('--timeout', type=float, default=45.)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--without-trace', action='store_true', help='Run the attach/discovery/sample gate only')
    args = parser.parse_args()
    output = args.output or Path(tempfile.mkdtemp(prefix='ros2graph-smoke-'))
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as check:
        check.bind(('127.0.0.1', args.port))
    smoke = Smoke(args.port, output, args.timeout)
    try:
        smoke.startup_variants()
        smoke.no_trace_phase()
        if not args.without_trace:
            smoke.traced_phase()
        smoke.report['passed'] = True
    finally:
        smoke.cleanup()
        print(f'Smoke evidence: {output}')
    assert smoke.report['cleanup']['listener_closed']
    assert smoke.report['cleanup']['all_children_stopped']
    assert smoke.report.get('passed'), smoke.report['cleanup']
    print(json.dumps(smoke.report, indent=2))


if __name__ == '__main__':
    main()
