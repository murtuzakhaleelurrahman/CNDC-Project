#!/usr/bin/env bash

set -u

cd "/mnt/d/CNDC Project/CampusShield" || exit 1
source /home/khaleel/.venvs/campusshield/bin/activate

echo
echo "Ubuntu authentication is required to create the Mininet topology."
echo "Type your password when prompted; no characters will be displayed."
echo

sudo -v || exit 1

echo "Cleaning interrupted CampusShield emulation state..."
for pid_file in \
    /tmp/campusshield-frr/r1/ospfd.pid \
    /tmp/campusshield-frr/r1/zebra.pid \
    /tmp/campusshield-frr/r2/ospfd.pid \
    /tmp/campusshield-frr/r2/zebra.pid \
    /tmp/campusshield-frr/r3/ospfd.pid \
    /tmp/campusshield-frr/r3/zebra.pid; do
    if [[ -f "$pid_file" ]]; then
        daemon_pid="$(cat "$pid_file")"
        daemon_command="$(tr '\0' ' ' < "/proc/$daemon_pid/cmdline" 2>/dev/null || true)"
        if [[ "$daemon_command" == *"/tmp/campusshield-frr/"* ]]; then
            sudo kill "$daemon_pid" 2>/dev/null || true
        fi
    fi
done
sudo mn -c

echo "Cleanup complete. Starting the formal Phase 3 experiment..."
echo

sudo /home/khaleel/.venvs/campusshield/bin/python \
    experiments/experiment_runner.py ospf \
    --repetitions 10 \
    --timeout 55
run_status=$?

if [[ $run_status -eq 0 ]]; then
    /home/khaleel/.venvs/campusshield/bin/python experiments/analyze_results.py
    run_status=$?
fi

exit "$run_status"
