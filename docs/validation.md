# Validation

This file records the environments actually checked for this extraction.
Robot-independent design is separate from platform coverage. Detailed RPC
tracing additionally depends on the installed RMW and standard tracepoints.

## Extraction validation — November 15, 2026

The live ROS tests ran on Ubuntu 26.04.1 LTS, kernel `7.0.0-1023-raspi`,
aarch64, ROS 2 Lyrical, `rmw_fastrtps_cpp`, Python 3.14.4 and aiohttp 3.14.5.

| Check | Observed result |
| --- | --- |
| Python observer, HTTP, RPC, identity, compatibility and lifecycle tests | 140 passed. |
| JavaScript graph/flow/filter/resize/client tests | 119 passed. |
| Installed ROS package | Colcon build passed on Linux aarch64, ROS 2 Lyrical, Python 3.14.4; all three executables registered. |
| Ordinary launch command | Installed `ros2graph.launch.py` started with the default empty tracing parameter, served `/healthz`, and exited cleanly. |
| Parameter-file startup | Installed `config/ros2graph.yaml` loaded and served the viewer. |
| Attach after application startup | The viewer discovered the running demo and counted 19 topic receipts; a finite sample counted 10. RPC correctly remained unavailable without the collector. |
| Independent viewer lifetime | The demo stayed alive after the observer stopped. |
| Traced service traffic | Trigger had 3 request-sent, 3 request-received, 3 response-sent and 3 response-received events. |
| Traced action traffic | Goal phases 2/2/2/2; cancel phases 1/1/1/1; result phases 2/2/2/2; 6 feedback and 2 status messages. |
| Trace coverage | All 25 discovered services were observed; one action was measured. No reported event/packet/unmapped loss or capacity truncation. |
| Same names in different domains | Two demos used identical node/interface names in domains 196 and 197. Both were traced; the domain-196 viewer admitted zero foreign-domain endpoints. Exact GID proof verified 29 endpoints on three nodes and excluded 22 others. |
| Shutdown | All eight owned test process groups exited with status 0. Listener, collector socket, trace session and owned temporary snapshots were removed. |
| Python wheel | Built with packaged UI assets, ament resource marker, launch file, config, license and documentation. |
| Browser checks | Fresh Chrome pages at 1440×1000, 1024×768 and 390×844 rendered without JavaScript errors or horizontal page overflow. Type filters, selection, update interval and keyboard pane resize worked. |

The test environment used a separate temporary workspace, private Python
environment and standard demo interface package. No robot source, runtime
service, calibration or device was modified. The screenshot in the README is
the viewer rendering the recorded hardware-free demo snapshot, not a claim of
physical robot validation. Numbers above are samples from the test, not promised
rates for every graph.

## Reproduce

The included smoke test creates only standard-interface demo nodes in an
isolated ROS domain. It verifies attaching after the application starts,
discovery of nodes/topics/services/actions, advancing topic counters, watch
renew/release, finite sampling and clean viewer shutdown while the application
continues. Its optional tracing phase starts the collector before the demo
and checks all four request/reply phases and action goal/cancel/result traffic.

Run the basic check after building and sourcing the package:

```bash
bash tests/run_ros_smoke.sh --without-trace
```

With a supported Linux tracing installation:

```bash
bash tests/run_ros_smoke.sh
```

Use `--output DIR` for the small JSON reports and process logs, `--port PORT`
to choose the loopback test listener, and `ROS2GRAPH_TEST_DOMAIN` to choose a
separate test domain (default 196). Tests stop only their own process groups
and tracing resources. They do not modify or restart a robot application.

## Cross-version CI

[CI run 43747992112](https://github.com/vincent-tvincent/ros2graph/actions/runs/43747992112)
passed for runtime revision `8d04d19`:

- Python 3.10 and 3.12: 140 Python tests, 119 frontend tests and wheel builds.
- ROS Humble and Jazzy: colcon build, ordinary launch, installed parameter-file
  startup, attach to a running demo, live receipts, finite sampling and clean
  independent shutdown.

The Humble check exposed its older one-argument raw callback API; capability
detection now counts those receipts without inventing publisher attribution.
A subsequent full Lyrical test preserved modern publisher GIDs for all 29
checked receipts (18 untraced and 11 traced), with zero unattributed messages.
Service/action tracing, same-name domain isolation and cleanup passed again.
The Python 3.10 rate assertion uses numeric tolerance for floating-point sums.

Optional tracing is not claimed verified on Humble or Jazzy merely because
their basic jobs pass. Lyrical/Fast DDS is the verified detailed-tracing
environment. See the repository's Actions page for newer validation results.

## Live GIF recordings and sustained tracing — November 15, 2026

The [five demonstrations](demos/README.md) record the real application connected
to the running String/Trigger/Fibonacci demo. Each GIF was decoded successfully,
reviewed visually and checked for looping playback. The files are 1280×889 at
10 FPS, run for 17.4–25.1 seconds, and total approximately 4.7 MiB. Capture raised
no browser JavaScript errors. [Recording metadata](demos/recording.json) gives
durations, frame counts, sizes and hashes; the recording tool is included.

The longer recording session exposed a resource leak that short startup tests
had missed: Babeltrace 2.1.2 snapshot iterators retain a graph/listener reference
cycle. The collector reached 1,022 descriptors, including 1,000 deleted trace
file handles. The reader now releases those cycles after each finite snapshot,
including constructor/processing failures and early event-limit exits. Partial
iterators are drained without adding discarded events to counters, so native
message buffers are also released.

After the fix, the live recording collector remained at six descriptors with
zero deleted trace-file handles for 791.5 seconds (over 13 minutes). It reported
no trace loss. The demo, viewer and collector then exited with status 0, and
their listener, owned trace session, socket and temporary snapshots were removed.
No production robot process, configuration or hardware was changed.

The final resource regression suite passes on full reads, early processing
limits, decoder exceptions and constructor exceptions. A separate actual
Babeltrace soak ran 660 finite decodes with automatic Python GC disabled:
220 complete reads, 220 early-limit exits and 220 injected errors. Descriptor
counts stayed at five throughout each mode. After warmup, live native heap
remained about 5.04–5.06 MB and RSS about 34.1–34.2 MB. Discarded cleanup events
were never added to measurement counters. The full Python suite now has
144 passing tests.
