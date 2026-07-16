#!/bin/bash
# pytest is baked into the environment image (environment/Dockerfile).
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if pytest /tests/test_outputs.py -rA --ctrf /logs/verifier/ctrf.json; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

exit 0
