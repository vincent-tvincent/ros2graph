# Graph HTTP API

The API is served by the same process and origin as the browser application.
It manages discovery and observation only. There are no message-payload,
robot-command, file-upload or generic ROS service-call routes.

## Observe traffic from a script

The following uses Python's standard library. Set `ROS2GRAPH_URL` to the
viewer URL, and optionally `ROS2GRAPH_TOKEN` if its bearer authentication is
configured. Keep the viewer and ROS environment running first.

```python
import json
import os
import time
import urllib.request
import uuid

base = os.environ.get("ROS2GRAPH_URL", "http://localhost:8080").rstrip("/")
token = os.environ.get("ROS2GRAPH_TOKEN")

def request(path, body=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)

watch = request("/api/graph/watch", {
    "operation": "acquire", "client_id": str(uuid.uuid4())
})
if not watch.get("accepted"):
    raise RuntimeError(watch)
lease_id = watch["lease_id"]
try:
    # Short demonstration. A long-running client renews its lease before expiry.
    delay = min(2.0, watch["expires_in_ms"] / 3000)
    for _ in range(5):
        time.sleep(delay)
        renewed = request("/api/graph/watch", {"operation": "renew", "lease_id": lease_id})
        if not renewed.get("accepted"):
            raise RuntimeError(renewed)
        graph = request("/api/graph")
        for topic in graph["topics"]:
            activity = topic["activity"]
            print(topic["name"], activity["state"], activity["rate_hz"])
finally:
    request("/api/graph/watch", {"operation": "release", "lease_id": lease_id})
```

An HTTPS deployment uses normal certificate validation. Trust your deployment
certificate through the OS/Python trust configuration instead of disabling TLS
verification in the client.

## Snapshot contract

`GET /api/graph` currently returns `schema_version: 1`. Readers should ignore
additional fields so that additive improvements remain compatible.

| Field | Meaning |
| --- | --- |
| `nodes` | Stable IDs, reported name/namespace/FQN, instance count or unresolved-identity state. |
| `topics` | Stable IDs, exact names, types, publisher/subscription endpoints with GIDs and QoS, `activity` and finite-sample `traffic`. |
| `services` | Exact names/types, client/server node IDs and phase-specific `activity`. |
| `actions` | Exact names/types, client/server IDs, feedback/status activity, RPC components and combined `display` metrics. |
| `edges` | IDs, relationship `kind`, `from`, `to`, and endpoint ID where available. |
| `coverage` | Discovery completeness for each interface category. |
| `errors` | Explicit graph/API/discovery errors with section, method and reason. |
| `watch` | Observer lease state, capacity, subscriptions and activity coverage. |
| `rpc_trace` | Collector availability, mapping/identity coverage, snapshot freshness, loss and lower-bound flags. |
| `sequence`, `captured_at_ns`, `age_ms` | Topology snapshot sequence, Unix-nanosecond discovery capture and its age. |
| `activity_clock_id`, `activity_captured_at_ns` | Counter snapshot clock identity and monotonic-nanosecond capture (decimal string). |

IDs are opaque identifiers; preserve them rather than reconstructing identity
from the shortened labels drawn on screen. Node FQNs can have duplicate
instances. Unresolved middleware endpoint ownership is not a normal named node.

Edge kinds are `publish`, `subscribe`, `service_client`, `service_server`,
`action_client` and `action_server`. The graph relationships express discovered
connections, not a proof of successful delivery.

## Counter contract

Topic `activity` contains `state`, `sample_id`, `source`, `measurement_scope`,
`messages`, `bytes`, `rate_hz`, `bytes_per_second`, `last_message_age_ms`,
`history`, `publisher_counts`, `unknown_publisher_messages`, `reason` and
`payload_export: false`. Nullable fields are unknown, not zero.

Calculate deltas only inside the same `sample_id`/counter epoch. A new watch
session or subscription can reset counters. The first snapshot establishes a
baseline; do not animate its total as newly arrived messages. Compare monotonic
timestamps only within the same `activity_clock_id`. They are not cross-host
timestamps or a browser network-latency measurement.

For services, `activity.channels` separates `request_sent`, `request_received`,
`response_sent`, `response_received`. `activity.endpoints` carries the relevant
channel counts for exact client/server identities. Missing endpoint mappings
must stay unavailable. The service summary counts server-received requests
plus server-sent responses; it does not add both ends of every phase together.

Actions expose `activity.rpc.goal`, `.cancel`, `.result` as service-shaped
metrics, plus `feedback` and `status` topic metrics. `activity.display` combines
the independently observed components for presentation. Do not treat that
combined number as unique goals, completed operations or packets.

See [measurements.md](measurements.md) for observer scope and failure states.

## Leases and finite samples

Use a UUID `client_id` for acquisition. Successful acquisition returns an
opaque `lease_id` and an `expires_in_ms` value. Renew before that deadline; release
when finished. An expired ID can return `accepted: false` and `code: not_found`;
acquire a new lease and establish new counter baselines. Do not renew someone
else's lease or assume one browser owns all watchers.

The UI renews separately from its visual update interval. Ordinary graph GETs
do not start traffic subscriptions, and hiding an interface in the UI does not
stop its measurements while a watch is active.

`POST /api/graph/sample` is a separate bounded one-topic sampling facility,
limited to two concurrent samples and ten seconds per sample. Use Live watch
for continuous graph-wide monitoring and raw media. Both paths retain metadata
only and release their subscriptions when stopped or expired.
