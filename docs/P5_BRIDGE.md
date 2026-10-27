# P5: Remediation bridge

Adapter path: engine -> `bridge_adapter.run_bridge_adapter` -> `methods.bridge.build_bridge`.

The documented fit threshold is `tau=60`: fit at or above tau needs no remediation bridge. The contract maps outcomes to `not_needed`, `found` (three named steps: Familiarization, Bridge adoption, Conversion), or `not_found` with warnings. Friction before/after and reduction are carried as metrics in `BridgeResult`.

Qloo affinity and category factories are **UNVERIFIED until P7**.

Acceptance: the three P12 scenarios in `tests/test_bridge_adapter.py` (strong-fit not-needed, weak-fit three-step bridge, and no bridge found).
