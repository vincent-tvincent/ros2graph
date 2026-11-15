"""Optional launch convenience; existing robot launch files need no edits."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("host", default_value="127.0.0.1"),
        DeclareLaunchArgument("port", default_value="8080"),
        DeclareLaunchArgument("rpc_trace_socket", default_value=""),
        Node(package="ros2graph", executable="ros2graph", output="screen", parameters=[{
            "host": ParameterValue(LaunchConfiguration("host"), value_type=str),
            "port": ParameterValue(LaunchConfiguration("port"), value_type=int),
            "rpc_trace_socket": ParameterValue(LaunchConfiguration("rpc_trace_socket"), value_type=str),
        }]),
    ])
