# CampusShield Command Handbook

This handbook is a copy-paste reference for running, demonstrating, validating, and troubleshooting CampusShield in Ubuntu/WSL.

## Before you begin

Open Ubuntu/WSL. Commands in this guide assume the project is stored at:

```bash
/mnt/d/CNDC Project/CampusShield
```

Activate the virtual environment whenever Python packages such as Streamlit, pandas, or matplotlib are required:

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
```

If your prompt already begins with `(campusshield)`, the environment is active.

## Quick experiment selector

| Goal | Command | Main output |
|---|---|---|
| Experiment 1: healthy baseline | `sudo "$(which python3)" experiments/experiment_runner.py baseline --duration 30` | SQLite run, baseline CSV, baseline PNG |
| Experiment 2: three-arm phased congestion | `sudo "$(which python3)" experiments/experiment_runner.py congestion --healthy-duration 10 --duration 30 --recovery-duration 20 --repetitions 10` | SQLite runs, comparison CSV and PNG |
| Experiment 3: physical link failure and recovery | `sudo "$(which python3)" experiments/experiment_runner.py failure --repetitions 10 --timeout 20` | SQLite runs, recovery CSV and PNG |
| Experiment 4: default vs tuned OSPF | `sudo "$(which python3)" experiments/experiment_runner.py ospf --repetitions 10 --timeout 55` | SQLite runs, OSPF comparison CSV and PNG |
| Experiment 5: closed-loop adaptive routing | `sudo "$(which python3)" experiments/experiment_runner.py adaptive-routing --repetitions 10 --hold-down 45` | SQLite telemetry/events, adaptive-routing CSV and PNG |
| Analyze Experiments 2–5 | `python3 experiments/analyze_results.py` | Summary CSV, analysis Markdown, summary PNG |

Run only one Mininet experiment at a time.

## Start the dashboard

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
streamlit run dashboard/app.py
```

Open `http://localhost:8501`. Keep this terminal open. Stop the dashboard with `Ctrl+C`.

After a new experiment finishes, open the dashboard sidebar, click **Reload evidence**, and select the newest run. A run number is assigned by SQLite, so it may not be the number you predicted.

## Experiment 1 - baseline

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py baseline --duration 30
```

What it does: creates a fresh Mininet/FRR topology, establishes OSPF, generates a controlled 10 Mbps emergency flow, measures RTT, packet loss, jitter, throughput, utilization, and Network Health Score, stores the evidence, and cleans up the topology.

Expected final message: `BASELINE EXPERIMENT PASSED`

Files: `results/baseline_run_<id>.csv` and `results/baseline_run_<id>.png`

`--duration 30` controls the measurement period in seconds. Use 30 seconds for reportable evidence. The program requires at least 3 seconds.

## Experiment 2 - three-arm phased congestion comparison

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py congestion \
  --healthy-duration 10 \
  --duration 30 \
  --recovery-duration 20 \
  --repetitions 10
```

What it does: compares basic static QoS, tuned static QoS, and adaptive ANRE using matched healthy, congestion, and recovery phases. It records EF probe quality, traffic performance, NHS recovery, controller response, and per-class queue evidence.

Expected final message: `CONGESTION COMPARISON EXPERIMENT PASSED`

Files: `results/congestion_comparison_<group-id>.csv` and `results/congestion_comparison_<group-id>.png`

Use ten matched repetitions for formal results. The durations control the healthy, congested, and recovery windows inside every scenario. For a quick pilot only, use `--healthy-duration 4 --duration 12 --recovery-duration 8 --repetitions 1`.

## Experiment 3 - link failure and OSPF recovery

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py failure --repetitions 10 --timeout 20
```

What it does: creates a fresh topology for each repetition, verifies the direct R1-R2 route, disables that physical link, measures convergence to R1-R3-R2, restores the link, measures restoration of the direct route, and records packet loss and interruption time.

Expected final message: `LINK FAILURE EXPERIMENT PASSED`

Files: `results/failure_recovery_<group-id>.csv` and `results/failure_recovery_<group-id>.png`

`--repetitions 10` controls the number of fresh runs used for formal confidence intervals. `--timeout 20` is the maximum wait for each route change.

## Experiment 4 - default versus tuned OSPF

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py ospf --repetitions 10 --timeout 55
```

What it does: compares FRR's default neighbor-detection behavior with a tuned
profile using matched, order-rotated fresh topologies. The R1-R2 link remains
physically up but silently drops traffic, so OSPF must detect the failure from
its Hello/dead timers. The tuned profile uses a 1-second dead interval, five
Hellos per second, and 0/50/1000 ms SPF throttle timers.

Expected final message: `OSPF OPTIMIZATION EXPERIMENT PASSED`

Files: `results/ospf_optimization_<group-id>.csv` and
`results/ospf_optimization_<group-id>.png`

Use ten repetitions for the formal H7 result. For a pilot only, change
`--repetitions 10` to `--repetitions 1`; keep `--timeout 55` because the
default dead interval is approximately 40 seconds.

## Experiment 5 - closed-loop adaptive routing

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
sudo "$(which python3)" experiments/experiment_runner.py adaptive-routing --repetitions 10 --hold-down 45
```

What it does: adds controlled delay and loss to the still-up R1-R2 link,
measures its health, runs ANRE and adaptive routing in one controller loop,
changes QoS on ANRE transitions, raises the R1-R2 OSPF cost from 10 to 100,
verifies the R1-R3-R2 backup path, enforces the 45-second hold-down, and then
restores cost 100 to 10 and the direct route.

Expected final message: `CLOSED-LOOP ADAPTIVE ROUTING EXPERIMENT PASSED`

Files: `results/adaptive_routing_<group-id>.csv` and
`results/adaptive_routing_<group-id>.png`

Use ten repetitions for formal confidence intervals. For a pilot only, change
`--repetitions 10` to `--repetitions 1`; keep the 45-second hold-down for an
honest anti-flapping test.

## Analyze repeated experiments

Run this after completing ten matched congestion repetitions, ten failure
repetitions, ten matched OSPF repetitions, and ten adaptive-routing repetitions:

```bash
source ~/.venvs/campusshield/bin/activate
cd "/mnt/d/CNDC Project/CampusShield"
python3 experiments/analyze_results.py
```

What it does: calculates descriptive means, sample standard deviations, and two-sided 95% Student-t confidence intervals, evaluates the hypotheses from measured directions of change, and builds final comparison artifacts.

Expected final message: `CORE EXPERIMENT ANALYSIS PASSED`

Files: `results/core_experiment_summary.csv`, `results/core_experiment_analysis.md`, and `results/core_experiment_summary.png`

## Validation and subsystem tests

### Foundation, OSPF, connectivity, and failover

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sudo python3 topology/campus_topology.py --test
```

Success: `FOUNDATION AND LINK EMULATION TEST PASSED`

### Concurrent traffic profiles

```bash
sudo python3 topology/campus_topology.py --traffic-test --duration 10
```

Success: `TRAFFIC GENERATION TEST PASSED`

### Static QoS contention

```bash
sudo python3 topology/campus_topology.py --qos-test --duration 8
```

Success: `STATIC QOS TEST PASSED`

### Telemetry snapshot

```bash
sudo python3 topology/campus_topology.py --telemetry-test
```

Success: `TELEMETRY TEST PASSED`

### Baseline calibration and NHS logic

```bash
sudo python3 topology/campus_topology.py --baseline-test
```

Success: `BASELINE AND NHS TEST PASSED`

### ANRE hysteresis and dynamic QoS

```bash
sudo python3 topology/campus_topology.py --anre-test
```

Success: `ANRE DYNAMIC QOS TEST PASSED`

### Adaptive OSPF routing

```bash
sudo python3 topology/campus_topology.py --routing-test
```

Success: `ADAPTIVE ROUTING TEST PASSED`

### Security isolation

```bash
sudo python3 topology/campus_topology.py --security-test
```

Success: `SECURITY ISOLATION TEST PASSED`

### SQLite persistence

```bash
python3 database/validate_database.py
```

Success: `SQLITE PERSISTENCE TEST PASSED`. This writes synthetic validation rows, not experimental evidence.

### Dashboard validation

```bash
python3 dashboard/validate_dashboard.py
```

Success: `STREAMLIT DASHBOARD TEST PASSED`

## Interactive Mininet inspection

Open the standard Mininet CLI:

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
r1 tc class show dev r1-eth0
r1 tc filter show dev r1-eth0 parent 10:
r1 tc -s class show dev r1-eth0
r1 vtysh --vty_socket /tmp/campusshield-frr/r1/vty -c "show ip ospf neighbor"
```

Type `exit` to close Mininet.

To open Mininet with the static QoS policy already applied:

```bash
sudo python3 topology/campus_topology.py --enable-qos
```

## Inspect stored database runs

```bash
cd "/mnt/d/CNDC Project/CampusShield"
sqlite3 database/campusshield.db
```

Then enter:

```sql
.tables
SELECT id, name, run_type, is_experimental, status FROM experiment_runs;
.quit
```

## Recommended professor demonstration

1. Start the dashboard in Terminal 1.
2. Show an existing completed run and explain that every value is stored evidence.
3. Open Terminal 2 and run Experiment 1 with the 30-second baseline command.
4. Explain the live RTT, loss, jitter, utilization, throughput, and NHS samples printed in the terminal.
5. Wait for `BASELINE EXPERIMENT PASSED`.
6. In the dashboard, click **Reload evidence** and choose the newest baseline run.
7. Open Telemetry, Routing, QoS, ANRE, Experiments, Events, and System to connect the live experiment with its stored evidence.

## Troubleshooting and safety

### Python package missing under sudo

Use the virtual environment's exact interpreter:

```bash
sudo "$(which python3)" experiments/experiment_runner.py baseline --duration 30
```

Do not replace it with plain `sudo python3` for the experiment runner if that interpreter lacks matplotlib or pandas.

### Old Mininet state after interruption

```bash
sudo mn -c
```

This removes stale Mininet interfaces, switches, and processes. Use it after an interrupted or failed topology run, not while an experiment is active.

### Open vSwitch service is not running

```bash
sudo systemctl enable --now openvswitch-switch
```

### Dashboard still shows the older run

Wait until the experiment reports success, click **Reload evidence**, and select the newest run in the sidebar. The dashboard does not automatically select a new database run.

### Important operating rules

- Run commands in Ubuntu/WSL, not Windows PowerShell.
- Keep only one experiment runner active at a time.
- Do not close the experiment terminal until Mininet prints its cleanup messages.
- Use `Ctrl+C` to stop Streamlit.
- Do not run the Streamlit dashboard with `sudo`.
- A PASS message confirms collection completed; the measured values determine whether a research hypothesis is supported.
