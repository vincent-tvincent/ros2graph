"""Generic ROS graph traffic: String, Trigger and Fibonacci, with no devices.

Run with ``ros2 run ros2graph demo_graph``. Two nodes exchange a topic,
periodically call a service, and alternate completed and canceled action goals.
"""
import threading
import time

import rclpy
from example_interfaces.action import Fibonacci
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from std_srvs.srv import Trigger


NAMESPACE = '/ros2graph_demo'


class DemoServer(Node):
    def __init__(self):
        super().__init__('server', namespace=NAMESPACE)
        self.stopping = threading.Event()
        self.sequence = 0
        self.publisher = self.create_publisher(String, NAMESPACE + '/chatter', 10)
        self.create_timer(.1, self.publish_sample)
        self.create_service(Trigger, NAMESPACE + '/trigger', self.trigger)
        self.action = ActionServer(
            self, Fibonacci, NAMESPACE + '/fibonacci', self.execute,
            callback_group=ReentrantCallbackGroup(),
            goal_callback=lambda request: GoalResponse.ACCEPT if 1 <= request.order <= 40 else GoalResponse.REJECT,
            cancel_callback=lambda _: CancelResponse.ACCEPT,
        )

    def publish_sample(self):
        self.sequence += 1
        self.publisher.publish(String(data=f'sample {self.sequence}'))

    def trigger(self, _request, response):
        response.success = True
        response.message = f'Observed {self.sequence} generated samples'
        return response

    def execute(self, goal):
        sequence = [0, 1]
        for _ in range(goal.request.order):
            if goal.is_cancel_requested:
                goal.canceled()
                return Fibonacci.Result(sequence=sequence)
            if self.stopping.is_set() or not rclpy.ok():
                if goal.is_active:
                    goal.abort()
                return Fibonacci.Result(sequence=sequence)
            sequence.append(sequence[-1] + sequence[-2])
            goal.publish_feedback(Fibonacci.Feedback(sequence=sequence))
            self.stopping.wait(.08)
        goal.succeed()
        return Fibonacci.Result(sequence=sequence)


class DemoClient(Node):
    def __init__(self):
        super().__init__('client', namespace=NAMESPACE)
        self.received = 0
        self.create_subscription(String, NAMESPACE + '/chatter', self.receive, 10)
        self.service = self.create_client(Trigger, NAMESPACE + '/trigger')
        self.service_pending = None
        self.create_timer(.75, self.call_service)
        self.action = ActionClient(self, Fibonacci, NAMESPACE + '/fibonacci')
        self.goal_pending = False
        self.goal_handle = None
        self.goal_count = 0
        self.cancel_at = None
        self.next_goal_at = 0.
        self.create_timer(.1, self.drive_action)

    def receive(self, _message):
        self.received += 1

    def call_service(self):
        if self.service_pending is not None and not self.service_pending.done():
            return
        if self.service.service_is_ready():
            self.service_pending = self.service.call_async(Trigger.Request())

    def drive_action(self):
        now = time.monotonic()
        if self.goal_handle is not None and self.cancel_at is not None and now >= self.cancel_at:
            self.cancel_at = None
            self.goal_handle.cancel_goal_async()
        if self.goal_pending or now < self.next_goal_at or not self.action.server_is_ready():
            return
        self.goal_pending = True
        self.goal_count += 1
        cancel = self.goal_count % 2 == 0
        future = self.action.send_goal_async(Fibonacci.Goal(order=30 if cancel else 6),
                                             feedback_callback=lambda _message: None)
        future.add_done_callback(lambda result: self.goal_accepted(result, cancel))

    def goal_accepted(self, future, cancel):
        try:
            handle = future.result()
            if not handle.accepted:
                self.goal_finished(None)
                return
            self.goal_handle = handle
            self.cancel_at = time.monotonic() + .25 if cancel else None
            handle.get_result_async().add_done_callback(self.goal_finished)
        except Exception:
            self.goal_finished(None)

    def goal_finished(self, _future):
        self.goal_handle = None
        self.goal_pending = False
        self.cancel_at = None
        self.next_goal_at = time.monotonic() + .6


def main(args=None):
    # Let the main thread stop the demo worker before invalidating ROS handles.
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    server = DemoServer()
    client = DemoClient()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(server)
    executor.add_node(client)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        server.stopping.set()
        executor.shutdown(timeout_sec=3.)
        client.destroy_node()
        server.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
