from glob import glob
from setuptools import setup

setup(
    name="ros2graph",
    version="0.1.0",
    packages=["ros2graph"],
    package_data={"ros2graph": ["web/*.html", "web/*.js", "web/*.css", "web/*.json"]},
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/ros2graph"]),
        ("share/ros2graph", ["package.xml", "README.md", "CONTRIBUTING.md", "LICENSE", "NOTICE"]),
        ("share/ros2graph/docs", glob("docs/*.md") + glob("docs/*.png")),
        ("share/ros2graph/launch", glob("launch/*.launch.py")),
        ("share/ros2graph/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools", "aiohttp>=3.8,<4"],
    python_requires=">=3.10",
    zip_safe=False,
    maintainer="Vincent Pu",
    maintainer_email="vincent.pu@outlook.com",
    description="Standalone ROS 2 graph explorer with live topic, service and action activity",
    license="Apache-2.0",
    url="https://github.com/vincent-tvincent/ros2graph",
    entry_points={"console_scripts": [
        "ros2graph = ros2graph.node:main",
        "rpc_trace_collector = ros2graph.rpc_trace_collector:main",
        "demo_graph = ros2graph.demo:main",
    ]},
)
