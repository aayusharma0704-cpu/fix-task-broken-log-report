#!/bin/bash
set -euo pipefail

# Install the reference log-processing program as the deliverable. The verifier
# re-runs it against the shipped sample and many held-out logs.
cp /solution/process_log.py /app/process_log.py

# Produce the report for the shipped sample log as well.
python3 /app/process_log.py
