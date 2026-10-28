# CampusShield

CampusShield is a student project that builds an adaptive, self-healing campus
network in Mininet with FRRouting, QoS, telemetry, experiment persistence,
security isolation, and a read-only operations dashboard.

## Implemented system

The foundation creates:

- three Linux routers (`r1`, `r2`, and `r3`) in a triangle;
- one test host in each of the five campus networks;
- one isolated Zebra and OSPF daemon pair per router;
- OSPF cost 10 on the direct R1-R2 path;
- OSPF cost 15 on each backup hop through R3;
- 100 Mbps enforced capacity on every routed core link;
- 5 ms one-way delay on every routed core link;
- automated validation of all host addresses, prefixes, and default gateways;
- automated checks that remote campus networks are learned through OSPF;
- automated checks of `tc`, RTT, throughput, connectivity, and failover;
- concurrent emergency UDP, academic TCP, and bulk TCP traffic profiles;
- DSCP EF, AF21, and CS1 packet marking;
- static HTB allocations of 20/50/30 Mbps on every core egress interface;
- per-class 5 ms netem delay and FQ-CoDel queue management;
- DSCP filters that connect packet markings to the three HTB classes;
- kernel byte-counter telemetry for TX/RX rate and utilization;
- lightweight RTT, packet-loss, and probe-jitter measurements;
- selected route, next-hop, interface, and link-state monitoring;
- concurrent collection of interface and probe measurements;
- approximately 30-second environment-aware baseline calibration;
- configurable RTT, loss, and jitter threshold derivation;
- the proposal's normalized weighted Network Health Score;
- ANRE `NORMAL`, `DEGRADED`, and `CRITICAL` state logic;
- confirmed entry and five-sample recovery hysteresis;
- live dynamic changes between the proposal's three QoS allocations;
- adaptive OSPF cost changes with hold-down protection;
- SQLite telemetry, event, experiment, and result persistence;
- repeated congestion and physical-link-failure experiments;
- a responsive Streamlit operations and evidence dashboard;
- namespaced `nftables` isolation between campus segments.

The core-link values are defined near the top of `topology/campus_topology.py`
as `CORE_BANDWIDTH_MBPS` and `CORE_DELAY` so later experiments can adjust them
without rewriting the topology.

## Addressing

| Network | Router interface | Test host |
|---|---|---|
| Emergency `10.10.10.0/26` | R1 `10.10.10.1` | `emergency1` `10.10.10.10` |
| Admin `10.10.20.0/24` | R2 `10.10.20.1` | `admin1` `10.10.20.10` |
| Academic `10.10.30.0/23` | R2 `10.10.30.1` | `academic1` `10.10.30.10` |
| Hostel `10.10.40.0/22` | R3 `10.10.40.1` | `hostel1` `10.10.40.10` |
| IoT/CCTV `10.10.50.0/25` | R3 `10.10.50.1` | `iot1` `10.10.50.10` |
| R1-R2 | R1 `10.10.255.1/30` | R2 `10.10.255.2/30` |
| R1-R3 | R1 `10.10.255.5/30` | R3 `10.10.255.6/30` |
| R2-R3 | R2 `10.10.255.9/30` | R3 `10.10.255.10/30` |

## Run the security-isolation test

This mode first proves that routing and failover work, then installs a
project-owned `nftables` forward hook inside the relevant Mininet router
namespaces and validates each rule with real packets:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --security-test
```

| Source | Destination or service | Expected result |
|---|---|---|
| Emergency | Required Admin service | Allow |
| Hostel | Admin segment | Block |
| Academic | General Admin access | Block |
| Academic | Admin HTTPS, TCP 443 | Allow |
| IoT/CCTV | Monitoring/NVR, TCP 8443 | Allow |
| IoT/CCTV | Other Admin services | Block |
| IoT/CCTV | Simulated external endpoint | Block |
| Admin | IoT/CCTV management direction | Allow |

The external target uses the documentation-only address `198.51.100.1`; it is
only a local lab endpoint and is not presented as a public-Internet emulator.
Successful output ends with:

```text
SECURITY ISOLATION TEST PASSED
```

## Run the automated foundation test

From Ubuntu/WSL:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --test
```

The final line should be:

```text
FOUNDATION AND LINK EMULATION TEST PASSED
```

Before the final result, each campus segment and learned OSPF route should be
shown with a `PASS` status.

## Run the traffic-generation test

This mode first verifies the existing foundation, then runs all three traffic
profiles concurrently for four seconds:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --traffic-test
```

To choose a different flow duration:

```bash
sudo python3 topology/campus_topology.py --traffic-test --duration 10
```

The traffic section should end with:

```text
TRAFFIC GENERATION TEST PASSED
```

The profiles and their ports are defined in `traffic/traffic_generator.py`:

| Profile | Protocol | Source to destination | DSCP | Port |
|---|---|---|---|---|
| Emergency | UDP, 10 Mbps | `emergency1` to `admin1` | EF (46) | 5201 |
| Academic | TCP | `academic1` to `emergency1` | AF21 (18) | 5202 |
| Bulk | TCP | `hostel1` to `admin1` | CS1 (8) | 5203 |

## Run the static QoS test

This creates three simultaneous flows on the same R1-R2 bottleneck and verifies
the NORMAL-state 20/50/30 Mbps allocation:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --qos-test --duration 8
```

Successful output ends with:

```text
STATIC QOS TEST PASSED
```

To apply the static policy and inspect it interactively:

```bash
sudo python3 topology/campus_topology.py --enable-qos
```

Then use these commands at the `mininet>` prompt:

```text
r1 tc qdisc show dev r1-eth0
r1 tc class show dev r1-eth0
r1 tc filter show dev r1-eth0 parent 10:
r1 tc -s class show dev r1-eth0
```

The queue hierarchy is deliberately ordered as HTB classification, per-class
delay, then FQ-CoDel. This prevents one high-rate flow from filling a shared
delay queue before classification.

## Run the telemetry test

This starts a temporary 10 Mbps emergency UDP flow, samples R1's direct core
interface, sends five lightweight probes, and reads the current kernel route:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --telemetry-test
```

Successful output reports TX/RX Mbps, utilization, RTT, loss, probe jitter,
next hop, interface state, and ends with:

```text
TELEMETRY TEST PASSED
```

Interface rates are calculated from two readings of Linux files such as:

```text
/sys/class/net/r1-eth0/statistics/tx_bytes
/sys/class/net/r1-eth0/statistics/rx_bytes
```

The continuous low-overhead jitter value is the mean absolute change between
consecutive ping RTT samples. Formal UDP experiments will also use iPerf3's
receiver-reported jitter for validation.

### Phase 1 measurement accuracy

CampusShield service probes are marked as DSCP EF (`ping -Q 184`) so their
RTT, loss, and delay variation traverse the same emergency HTB class as the
protected traffic. This fixes the earlier ambiguity where unmarked probes
could enter the default bulk class.

Every telemetry snapshot also reads `tc -s class` from the observed core
interface and stores separate Emergency, Academic, and Bulk evidence:

- cumulative transmitted bytes and packets;
- cumulative dropped packets, overlimits, and requeues;
- instantaneous backlog bytes and packets;
- the class ID and DSCP value used for classification.

The queue evidence is stored in `qos_class_samples`, linked to the matching
`telemetry_samples` row, and is shown in the dashboard's QoS view. Formal CSV
artifacts contain flattened queue fields such as
`emergency_dropped_packets` and `bulk_backlog_bytes`.

The proposal's NHS formula and weights are intentionally unchanged. Queue
counters are supporting diagnostic evidence rather than an undocumented new
health-score term. Runs collected before this schema upgrade remain readable,
but their QoS page correctly reports that per-class evidence was not recorded.

Run the platform-independent Phase 1 tests with:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
python3 -m unittest discover -s tests -v
```

## Run baseline calibration and NHS validation

The proposal's normal calibration period is 30 seconds:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --baseline-test
```

A shorter run may be used only for quick development checks:

```bash
sudo python3 topology/campus_topology.py --baseline-test --calibration-duration 8
```

The calibration reports the baseline vector, derived thresholds, normalized
components, and NHS. Successful output ends with:

```text
BASELINE AND NHS TEST PASSED
```

Initial threshold parameters are kept near the top of
`controller/calibration.py`. The current rules are:

```text
RTT_T    = max(20 ms, 3 * RTT_base)
Loss_T   = max(2%,    3 * Loss_base)
Jitter_T = max(5 ms,  3 * Jitter_base)
```

The implemented proposal formula is:

```text
NHS = 100 - (0.30*L_n + 0.30*P_n + 0.20*J_n + 0.20*C_n)
```

Every normalized component is capped to the range 0-100. Utilization is
normalized against the enforced 100 Mbps core capacity.

## Run the ANRE dynamic QoS test

The normal command performs the full 30-second initial calibration:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --anre-test
```

For a quick logic check only:

```bash
sudo python3 topology/campus_topology.py \
  --anre-test \
  --calibration-duration 4
```

The test first confirms a real calibrated NHS starts in `NORMAL`. It then uses
a clearly labeled deterministic score sequence to verify hysteresis and live
QoS actuation. Those deterministic scores test controller logic and are not
reported as experimental network measurements.

| State | Emergency | Academic/Admin | Bulk |
|---|---:|---:|---:|
| NORMAL | 20 Mbps | 50 Mbps | 30 Mbps |
| DEGRADED | 40 Mbps | 45 Mbps | 15 Mbps |
| CRITICAL | 55 Mbps | 35 Mbps | 10 Mbps |

Initial hysteresis behavior is configurable in `controller/anre.py`:

- `NORMAL` enters `DEGRADED` below NHS 70 after two confirmations.
- A score below 50 from `NORMAL`, or below 45 from `DEGRADED`, moves toward
  `CRITICAL` after two confirmations.
- `CRITICAL` recovers stepwise to `DEGRADED` above NHS 60 after five
  confirmations.
- `DEGRADED` returns to `NORMAL` above NHS 80 after five confirmations.
- A contradictory sample cancels the pending transition.

Successful output ends with:

```text
ANRE DYNAMIC QOS TEST PASSED
```

## Run the adaptive OSPF routing test

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --routing-test
```

The routing controller calculates a health score for the primary R1-R2 link
from utilization, packet loss, RTT, and jitter. Its initial safety rules are:

- Link health below 50 for three consecutive evaluations penalizes the link.
- The controller raises the OSPF cost at both ends from 10 to 100.
- R1-R2 traffic then uses the R1-R3-R2 backup path, whose total cost is 30.
- A 45-second hold-down prevents an immediate route reversal.
- After the hold-down, link health above 80 for three consecutive evaluations
  restores the cost to 10 and the direct route becomes preferred again.

The test takes a real health reading from R1-R2 and performs live FRR/OSPF
cost changes and route checks. The failure and recovery timestamps are a
clearly labeled deterministic controller-logic test, not experimental network
measurements; this avoids waiting 45 real seconds while still verifying the
hold-down rule.

Successful output ends with:

```text
ADAPTIVE ROUTING TEST PASSED
```

## Initialize and validate SQLite persistence

The persistent database is `database/campusshield.db`. It contains four
related tables:

- `experiment_runs` identifies each validation or experimental run.
- `telemetry_samples` stores RTT, loss, jitter, rates, utilization, NHS,
  ANRE state, link health, QoS policy, and the selected route.
- `controller_events` stores state changes, QoS/routing actions, OSPF events,
  failures, and recoveries.
- `experiment_results` stores named quantitative results and their units.

Initialize the schema and verify reading and writing with:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
python3 database/validate_database.py
```

Successful output ends with:

```text
SQLITE PERSISTENCE TEST PASSED
```

The validation command writes a small run whose `run_type` is `VALIDATION`
and whose `is_experimental` value is `0`. Its synthetic values test database
behavior only and must not be used in experimental graphs or final results.

To inspect the stored runs manually:

```bash
sqlite3 database/campusshield.db
```

Then enter:

```sql
.tables
SELECT id, name, run_type, is_experimental, status FROM experiment_runs;
.quit
```

SQLite WAL mode and a five-second busy timeout are configured automatically.
Each backend or dashboard process should create its own
`CampusShieldDatabase` object; each logging method uses a short transaction so
database work does not hold up network control.

## Open the Streamlit dashboard

Activate the project environment if the prompt does not already begin with
`(campusshield)`, then start the dashboard:

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
streamlit run dashboard/app.py
```

Open the URL printed by Streamlit, normally:

```text
http://localhost:8501
```

The dashboard opens the SQLite database in read-only mode. Automatic refresh
is disabled by default for stable demonstrations; enable `Refresh telemetry`
to refresh the selected run every two seconds. The sidebar selects a run and
the amount of history to display. Use `Reload run index` after a new experiment
completes.
The dark NOC interface is divided into nine focused views:

- `Overview`: current NHS/state, service measurements, physical topology,
  active route and recent control-plane events;
- `Topology`: core links, campus segments and the configured link baseline;
- `Telemetry`: interactive delay, loss, throughput and utilization history;
- `Routing`: observed routes plus OSPF, failure and recovery evidence;
- `QoS`: the controller's configured allocation policy, clearly separated
  from observed rates when measurements are available;
- `ANRE`: closed-loop monitor, analysis, decision and action evidence;
- `Experiments`: baseline, congestion, recovery and hypothesis outcomes;
- `Events`: filterable controller and routing event records;
- `System`: run metadata, data sources and stored experiment results.

All dashboard evidence is loaded from the SQLite database or generated result
files; the dashboard does not fabricate live values. The layout adapts from a
desktop operations console to a compact mobile presentation.

The header identifies whether the selected database run is validation or
experimental evidence. The Experiments view instead declares its independent
file scope because it summarizes the latest complete baseline, congestion and
failure-result CSVs. Stop the dashboard with `Ctrl+C` in the terminal.

To run the non-browser dashboard check:

```bash
python3 dashboard/validate_dashboard.py
```

Successful output ends with:

```text
STREAMLIT DASHBOARD TEST PASSED
```

## Run Experiment 1 - baseline calibration

Keep the `(campusshield)` virtual environment active. Mininet requires root,
while the virtual environment supplies the graphing libraries, so pass its
exact Python path to `sudo`:

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py baseline --duration 30
```

This is a real experimental run. It creates the topology, waits for all OSPF
adjacencies, generates a controlled 10 Mbps EF-marked emergency flow, and
collects low-overhead telemetry for approximately 30 seconds. It then derives
the baseline thresholds, calculates NHS for every sample, and saves:

- all samples and summary metrics in `database/campusshield.db`;
- a timestamped sample table in `results/baseline_run_<id>.csv`;
- a four-panel graph in `results/baseline_run_<id>.png`.

Successful output ends with:

```text
BASELINE EXPERIMENT PASSED
```

The run is stored with `run_type = BASELINE` and `is_experimental = 1`, so it
is available immediately in the Streamlit run selector. Repeating the command
creates a new run instead of overwriting earlier measurements.

## Run Experiment 2 - three-arm adaptive congestion comparison

The Phase 2 design compares three matched scenarios on fresh topologies:

- `ANRE_OFF`: the original fixed NORMAL 20/50/30 Mbps allocation;
- `STATIC_TUNED`: a stronger fixed 55/35/10 Mbps emergency-priority policy;
- `ANRE_ON`: the controller starts at NORMAL and changes policy only from
  measured NHS and hysteresis decisions.

Every scenario has a 10-second healthy phase, a 30-second congested phase, and
a 20-second recovery phase. Congestion offers 60 Mbps emergency UDP plus
competing academic and bulk TCP on the 100 Mbps primary link. Healthy and
recovery phases use a controlled 10 Mbps emergency flow. Scenario order rotates
between repetitions to reduce systematic run-order bias.

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py congestion \
  --healthy-duration 10 \
  --duration 30 \
  --recovery-duration 20 \
  --repetitions 10
```

The runner records the phase name on every telemetry row, calculates formal
congestion metrics only from the congested window, and separately records
healthy NHS, recovery NHS, recovery-to-NORMAL time, per-class queue-drop
deltas, and peak emergency backlog. The test does not force an ANRE transition
or manufacture an improvement.

Use this shorter command only to verify the workflow before a formal run:

```bash
sudo "$(which python3)" experiments/experiment_runner.py congestion \
  --healthy-duration 4 \
  --duration 12 \
  --recovery-duration 8 \
  --repetitions 1
```

Each scenario stores its telemetry, flow metrics, ANRE events, and results in
SQLite. The comparison also creates:

```text
results/congestion_comparison_<group-id>.csv
results/congestion_comparison_<group-id>.png
```

Successful data collection ends with:

```text
CONGESTION COMPARISON EXPERIMENT PASSED
```

This message means the matched measurements were collected successfully. The
measured values, rather than the PASS message, determine whether each research
hypothesis is supported. Use ten repetitions for reportable congestion
results; a shorter single repetition is only a pilot check.

Only one command from `experiments/experiment_runner.py` may run at a time.
The runner uses an exclusive lock because simultaneous Mininet experiments
would share and corrupt the same virtual-network namespaces.

## Run Experiment 3 - physical link failure and OSPF recovery

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py failure \
  --repetitions 10 \
  --timeout 20
```

For every repetition, the runner builds a fresh topology, confirms the direct
R1-R2 route, starts continuous 100 ms probes, disables the physical R1-R2
link, waits for the R1-R3-R2 backup route, restores the link, and confirms the
direct route returns. It records:

- the failure timestamp and route before failure;
- packets lost and the longest service-interruption gap during convergence;
- backup-route convergence time and route after failure;
- OSPF FULL-neighbor counts before and after failure;
- primary-route restoration time and final route;
- health snapshots before failure and on the backup path.

The repeated summary and graph are written to:

```text
results/failure_recovery_<group-id>.csv
results/failure_recovery_<group-id>.png
```

Successful collection ends with:

```text
LINK FAILURE EXPERIMENT PASSED
```

## Run Experiment 4 - default versus tuned OSPF

Phase 3 tests the proposal's H7 rather than assuming that faster timers are
better. Each matched repetition uses two fresh topologies and alternates their
execution order:

- `OSPF_DEFAULT`: FRR defaults (10-second Hello, 40-second dead interval);
- `OSPF_TUNED`: a 1-second minimal dead interval with five Hellos per second,
  plus 0/50/1000 ms SPF throttle timers.

The runner silently drops all traffic on R1-R2 while leaving its carrier up.
This forces OSPF to detect a missing neighbor from Hello/dead timers instead of
receiving an immediate interface-down signal. Continuous 100 ms probes measure
packets lost, service interruption, backup convergence, and primary-route
restoration.

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py ospf \
  --repetitions 10 \
  --timeout 55
```

For a pilot workflow check, use one repetition. It still takes roughly a
minute for the default profile to declare the silent neighbor dead:

```bash
sudo "$(which python3)" experiments/experiment_runner.py ospf \
  --repetitions 1 \
  --timeout 55
```

The paired evidence is written to:

```text
results/ospf_optimization_<group-id>.csv
results/ospf_optimization_<group-id>.png
```

Successful collection ends with `OSPF OPTIMIZATION EXPERIMENT PASSED`. H7 is
supported only when the measured tuned mean service interruption is lower than
the measured default mean.

## Run Experiment 5 - closed-loop adaptive routing

Phase 4 connects ANRE and adaptive routing to the same live observation loop.
The experiment keeps R1-R2 physically up while adding 80 ms delay and 30%
packet loss to all three QoS classes. Real EF-marked probes lower the measured
link-health score; persistent degradation then triggers both QoS protection and
an OSPF cost change from 10 to 100. The runner verifies the route moves from
R1-R2 to R1-R3-R2, removes the impairment, enforces the full 45-second
anti-flapping hold-down, and restores cost 100 to 10 only after sustained
recovery.

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py adaptive-routing \
  --repetitions 10 \
  --hold-down 45
```

Use `--repetitions 1` only for a pilot. Every run stores link-health telemetry,
ANRE state changes, QoS actions, OSPF-cost actions, route evidence, and timing
metrics in SQLite. The repeated artifacts are:

```text
results/adaptive_routing_<group-id>.csv
results/adaptive_routing_<group-id>.png
```

Successful collection ends with
`CLOSED-LOOP ADAPTIVE ROUTING EXPERIMENT PASSED`.

## Analyze the repeated core experiments

After the ten-repetition three-arm congestion command and the repeated failure
command finish, generate the descriptive summary and hypothesis evaluation:

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
python3 experiments/analyze_results.py
```

When Phase 3 or Phase 4 evidence exists, the analyzer also requires ten
complete OSPF or adaptive-routing repetitions. It reports means, sample standard
deviations, two-sided 95% Student-t confidence intervals, adaptive-versus-basic
changes, adaptive-versus-tuned changes, and the measured H7 outcome. For a legacy or pilot dataset, the
minimum may be lowered explicitly, for example
`--minimum-repetitions 3`; such output is not the formal Phase 2 result.

```text
results/core_experiment_summary.csv
results/core_experiment_analysis.md
results/core_experiment_summary.png
```

Successful output ends with:

```text
CORE EXPERIMENT ANALYSIS PASSED
```

Hypotheses are marked supported or not supported directly from the measured
direction of change. Confidence intervals report uncertainty and are not
misrepresented as proof of causation or practical significance.

## Open the Mininet command line

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py
```

Useful commands at the `mininet>` prompt:

```text
nodes
net
pingall
r1 ip route
r1 tc qdisc show dev r1-eth0
r1 vtysh --vty_socket /tmp/campusshield-frr/r1/vty -c "show ip ospf neighbor"
```

Type `exit` to stop the topology. If an interrupted run leaves old Mininet
state behind, clean it with:

```bash
sudo mn -c
```

