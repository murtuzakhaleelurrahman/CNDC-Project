#!/usr/bin/env bash

set -u

cd "/mnt/d/CNDC Project/CampusShield" || exit 1
source /home/khaleel/.venvs/campusshield/bin/activate

echo
echo "Ubuntu authentication is required for the Phase 4 Mininet pilot."
echo "Type your password when prompted; no characters will be displayed."
echo
sudo -v || exit 1

echo "Cleaning interrupted emulation state..."
sudo mn -c

sudo /home/khaleel/.venvs/campusshield/bin/python \
    experiments/experiment_runner.py adaptive-routing \
    --repetitions 1 \
    --hold-down 45
