# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary audience is the professor evaluating the CampusShield CNDC project.
The project owner uses the interface during demonstrations to establish
credibility quickly, explain the network's behavior, and present measured
evidence. A technically literate campus-network operator is the secondary
usage model for the operations views.

## Product Purpose

CampusShield demonstrates an adaptive, self-healing campus network. The
interface must make current network health understandable immediately, then
let an evaluator inspect topology, telemetry, routing, QoS, ANRE decisions,
events, and reproducible experiment evidence without reading source code.
Success means the interface looks professionally engineered and makes the
project's real technical work easy to verify.

## Positioning

CampusShield combines FRRouting/OSPF redundancy, live telemetry, a weighted
Network Health Score, hysteresis-based ANRE decisions, dynamic QoS, adaptive
routing, persistent evidence, and repeatable experiments in one student-built
campus-network system.

## Operating Context

The application runs locally in WSL as a Streamlit dashboard backed by a
read-only SQLite connection. It is viewed during project demonstrations and
evaluation, with completed experimental runs selected from stored history.
The interface must distinguish live or stored operational evidence from
validation-only data and must remain useful when a run has sparse telemetry.

## Capabilities and Constraints

- Preserve the Python, Mininet, FRRouting, OSPF, telemetry, NHS, ANRE, QoS,
  routing, SQLite, security, and experiment implementations.
- The dashboard entry point is `dashboard/app.py`; read-only queries live in
  `dashboard/queries.py`.
- Use only values, events, states, and experiment results available from the
  database or generated result files.
- Never fabricate trends, topology state, routing state, QoS state, events, or
  experimental results. Show explicit unavailable or empty states instead.
- The product vocabulary includes NHS, ANRE, OSPF, QoS, Emergency, Admin,
  Academic, Hostel, and IoT/CCTV.
- The web interface must work at 1440, 1280, 1024, 768, and 390 pixels.

## Brand Commitments

The product name is CampusShield. The interface should present it as serious
network-operations software rather than a marketing site, generic SaaS
dashboard, or college-project template. Status colors are semantic: green for
NORMAL, amber for DEGRADED, and red for CRITICAL.

## Evidence on Hand

- SQLite telemetry, controller events, experiment runs, and experiment-result
  rows in `database/campusshield.db`.
- Formal baseline, ANRE OFF/ON congestion, and physical-link-failure CSV and
  graph outputs in `results/`.
- Descriptive hypothesis analysis in `results/core_experiment_analysis.md` and
  `results/core_experiment_summary.csv`.
- There are no customer claims, production deployment claims, or external
  monitoring integrations to present.

## Product Principles

1. Establish network health and project credibility in the first viewport.
2. Explain the adaptive control loop through real evidence, not decoration.
3. Keep technical detail dense, legible, and progressively disclosed.
4. Make every status color, chart, and indicator carry operational meaning.
5. Prefer honest empty states over invented demonstration data.

## Accessibility & Inclusion

Use high contrast, visible keyboard focus, semantic labels, non-color status
cues, reduced-motion support, responsive reflow, readable technical values,
and accessible tabular alternatives for charted evidence.
