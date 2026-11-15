# Measurement semantics

## Discovery is not traffic

The ROS graph APIs provide interface names, types, endpoint identities, QoS and
client/server relationships. These are used without application-specific labels
or configuration. Discovery can succeed while an interface is idle, incompatible,
unreachable or unable to load its message type on this observer.

Topic Live watch adds raw, best-effort, volatile subscriptions with shallow
queues. It records counts, serialized byte lengths, bounded histories and
publisher GIDs from message metadata. It does not decode arbitrary application
payloads, save images/video, or export message bodies. Hidden action status is
decoded only for bounded action-state metadata.

Receiving a message proves receipt by ros2graph. It does not prove every drawn
subscriber took that message or ran its callback. Moving subscription dots for
topic traffic intentionally carry that observer-level meaning. Service/action
trace phases are separately labeled and can report endpoint-specific activity.

Raw image, compressed image and point-cloud streams are eligible for continuous
watch. Eligibility does not make subscribing free: DDS must transport the data
to the observer and Python callbacks still run. On a busy robot, run the viewer
on an appropriate host, select a suitable topic budget, or disable Live watch
when only topology is needed. UI polling is separate from ROS publication rates.

## Identity and transport aliases

Preserve middleware-provided publisher GIDs and exact endpoint IDs. Some RMW
implementations expose buffer transport aliases as well as logical topics.
Subscribing to those internal aliases can create recursive transport channels.
The observer instead projects a matching logical topic's counts only when exact
globally unique publisher-GID evidence proves the correspondence. Projected byte
counts remain unknown, and partial attribution is not presented as full coverage.

The UI normally hides transport aliases and built-in infrastructure topics;
enable Infrastructure to inspect them. Their raw identities and explanations
remain in the snapshot. Unknown owners are never assigned to a familiar node by
name guessing, prefix heuristics or visual proximity.

## RPC tracing

The optional collector consumes standard LTTng metadata tracepoints. It tracks
ROS node, publisher/subscriber and service/client initialization, then the four
request/reply phases. No request or response contents are retained. `taken=false`
events are not counted as received messages.

Tracing starts before application initialization so that handles can be mapped
to real nodes. Node/process identities include process lifetime; stale mappings
and PID reuse must not attribute new events to a dead node. Exact endpoint-GID
evidence ties a traced node to the domain visible to this observer. Matching
only a node's FQN would be unsafe when other ROS domains use the same name.
Nodes without the required identity evidence remain unverified/unavailable.

The collector observes supported local-user processes on its host. The optional
`--parent-pid` switch narrows that to a process tree, but is not needed for normal
standalone use. It cannot retrospectively recover initialization events, infer
missing tracepoints, or trace a node on another computer through DDS discovery.
The current viewer accepts one local collector socket; it is not a distributed
trace aggregation system.

Counts start with an active browser observation lease. The collector retains
initialization mappings outside that lease, allowing application nodes to start
before the browser opens. Snapshot overlap is deduplicated; event/packet loss
and capacity bounds are reported. `0 Hz` is only used for a live observation
with no events during its positive observation interval.

## Bounds and storage

- Continuous-watch raw subscription capacity defaults to 256 in the standalone
  node and is configurable. Topics over capacity have an explicit state/reason.
- At most eight browser watch leases share the observer. The default lease is
  twelve seconds and is renewed independently of display refresh.
- Per-topic default budget: 10,000 receipts over five seconds. Global receipt
  budget: 50,000 over five seconds. Counters are not silently changed to zero
  when a budget is reached.
- History is bounded to 20 buckets per topic; publisher attribution and endpoint
  mappings are bounded as well. The snapshot reports missing or incomplete
  coverage instead of pretending every interface is measured.
- The finite-sample API has independent limits: two topics and ten seconds,
  with media exclusions. Use continuous watch for raw/high-volume types.
- The optional collector owns a bounded LTTng ring buffer and rotates two
  temporary snapshots, capped at 36 MiB of snapshot files. Its Unix socket and
  temporary directory are private to the user. No permanent archive is created.
- Clean shutdown removes only the collector's own session, socket and temporary
  files. It does not stop application processes or unrelated tracing sessions.

## Display states

| Display/state | Meaning |
| --- | --- |
| Watching / a numeric rate | A measurement path is active. Zero is a measured idle interval. |
| Monitor off / inactive | No active watch, or watching has been disabled. |
| Unavailable | Missing type support, missing trace identity, stale source, or another concrete observation error. |
| Capacity / limited | The configured observer capacity was reached. |
| Throttled | A receipt-rate budget was reached. |
| Cleanup pending | A subscription could not yet be destroyed; its explanation remains visible. |
| Partial / lower bound | Some measurement sources or trace events are missing. Inspect coverage and loss fields. |

The browser preserves these distinctions in the inspector. A curve is a graph
relationship; a sparkline is observed history; a moving dot is fresh activity
evidence. None should be substituted for the other.
