# Contributing

Use a fork and a pull request. Describe the observable behavior being changed
and the checks you ran. Start from the [README](README.md) and the hardware-free
demo; no SO-Arm Station checkout or robot is needed.

Keep the ROS observer independent of robot names, drivers and custom interfaces.
Application-specific controls belong outside this project. Preserve exact node
and interface identities, measurement provenance, missing-data explanations,
and bounded memory/storage. Never convert an unavailable observation to 0 Hz
or infer subscriber delivery from a topic counter.

The graph renderer uses plain JavaScript and SVG. Keep its shared node blocks,
warm/cool relationship colors, smooth curves and keyboard-accessible controls.
No frontend build tool is required to serve an installed package.

Run `python3 -m pytest tests` and `node --test tests/*.mjs` for affected logic.
ROS-dependent changes also need the isolated smoke test from the README. Record
the ROS distribution, RMW and OS when reporting compatibility results.

Do not commit credentials, certificates, trace archives, robot calibration,
private graph snapshots or generated environments. Synthetic fixtures and
hardware-free examples are welcome. Contributions are licensed under the
repository's Apache 2.0 license.
