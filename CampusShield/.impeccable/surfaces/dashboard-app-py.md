---
version: 1
slug: "dashboard-app-py"
primary_target: "dashboard/app.py"
related_targets: []
---

# CampusShield Operations Dashboard

## Scope

Primary target: `dashboard/app.py`. Visitor mode: Operate.

## Audience and job

The professor evaluating the CNDC project must understand the network's
health, adaptive mechanism, and experimental evidence within minutes. The
student presenter needs a credible interface that supports a technical walk-
through without hiding detail or inventing data.

## Constraints

Preserve the Streamlit/Python stack and the read-only SQLite/result-file data
flow. No fabricated status, topology state, events, trends, or experimental
values. Navigation must cover Overview, Topology, Telemetry, Routing, QoS,
ANRE, Experiments, Events, and System. Responsive targets are 1440, 1280,
1024, 768, and 390 pixels.

## Direction contract

**THESIS:** CampusShield is a live infrastructure atlas: one composed operating
surface that proves health, redundancy, and closed-loop response. It refuses
the generic wall of equal KPI cards and the oversized marketing header.

**OWN-WORLD:** A midnight-navy shell, blue-black working field, cool-slate
secondary surfaces, and precise hairline seams. White carries primary data;
cyan identifies active routes; green, amber, and red are reserved for state.
A compact workhorse sans handles interface text, while tabular measurements,
addresses, costs, and timestamps use restrained monospace. Corners are tight,
shadows rare, and density deliberate.

**STORY:** The evaluator first answers whether the network is healthy, then
sees why through the active route and topology. The path continues into
telemetry, the ANRE monitor-analyze-decide-act loop, QoS and routing actions,
and finally repeatable experimental evidence. Sparse data becomes an explicit
empty state, never a synthetic demonstration.

**FIRST VIEWPORT:** A persistent navigation rail frames a compact system bar.
The main status line combines Network Health, the numeric NHS, and the named
state as one operational sentence. Beneath it, the signature topology strip
draws R1-R2-R3 as a transit-style redundant route with campus segments and
link-state labels. A decision rail beside it shows the current ANRE action,
reason, route, and last update. RTT, loss, jitter, and utilization form one
aligned measurement band rather than six detached cards.

**FORM:** Network Atlas, fifth in the grounded direction set; Impeccable seed
`a99be312`. The signature move is the real campus topology rendered as a
route map whose active path, backup path, and semantic link states remain
legible at every breakpoint.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with
the finish review, the verdict, DESIGN.md, and every shipping raster carrying
its provenance

## Unresolved decisions

No product-truth decisions remain. The implementation may select exact token
values and responsive breakpoints while preserving this contract.
