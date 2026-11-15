#!/usr/bin/env bash
set -euo pipefail

# Source ROS and the ros2graph colcon overlay before running this script.
# The isolated domain and localhost discovery apply only to test children.
command -v ros2 >/dev/null || { echo 'Source your ROS installation first.' >&2; exit 1; }
ros2 pkg prefix ros2graph >/dev/null
ros2 pkg prefix example_interfaces >/dev/null || {
  echo 'The generic demo requires the standard example_interfaces package.' >&2
  exit 1
}
export ROS_DOMAIN_ID="${ROS2GRAPH_TEST_DOMAIN:-196}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_SECURITY_ENABLE=false
unset ROS_SECURITY_KEYSTORE ROS_SECURITY_STRATEGY
exec "${PYTHON:-python3}" "$(dirname "$0")/integration_smoke.py" "$@"
