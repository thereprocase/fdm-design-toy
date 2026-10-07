#!/bin/bash
# compute-box CPU benchmark: pause this box's CFD solver ranks (started by us) for the duration, always resume.
cd "$(dirname "$0")"
pids=$(pgrep -u "$(id -u)" -f "simpleFoam -parallel" | tr '\n' ' ')
resume() { [ -n "$pids" ] && kill -CONT $pids 2>/dev/null; echo "resumed CFD ranks: $pids"; }
trap resume EXIT
[ -n "$pids" ] && kill -STOP $pids && echo "paused CFD ranks: $pids"
sleep 3
export NUMBA_NUM_THREADS=${NUMBA_NUM_THREADS:-40}
REPS=20 .venv/bin/python bench_matvec.py numbagen 20 100 160 200 240
