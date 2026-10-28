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
sudo mn -c

echo "Starting the formal closed-loop adaptive-routing experiment..."
sudo /home/khaleel/.venvs/campusshield/bin/python \
    experiments/experiment_runner.py adaptive-routing \
    --repetitions 10 \
    --hold-down 45
run_status=$?

if [[ $run_status -eq 0 ]]; then
    /home/khaleel/.venvs/campusshield/bin/python experiments/analyze_results.py
    run_status=$?
fi

exit "$run_status"
