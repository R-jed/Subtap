#!/usr/bin/env python3
"""Phase 8.1 benchmark: positive process identity TTL cache.

Measures:
  1. Uncached successful verification (real child process with SUBTAP_RUN_ID)
  2. Positive cache hit
  3. 1000 logical 1 Hz ticks with a fake monotonic clock

Unlike the Phase 8 baseline, this creates a real child process carrying
SUBTAP_RUN_ID=bench-task-id so that successful identity matches and
positive cache hits can be exercised.
"""

import os
import subprocess
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from subtap.ui.observer import (
    persisted_process_matches_task,
    _IDENTITY_CACHE,
    _IDENTITY_CACHE_TTL,
    _IDENTITY_CACHE_MAX_ENTRIES,
)


def median(lst):
    return statistics.median(lst)


def p95(lst):
    s = sorted(lst)
    return s[int(len(s) * 0.95)]


if __name__ == "__main__":
    # ── Spawn a child process with SUBTAP_RUN_ID set ──
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        env={**os.environ, "SUBTAP_RUN_ID": "bench-task-id"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    child_pid = child.pid
    run_id = "bench-task-id"

    print(f"Hardware: {os.uname().machine}")
    print(f"Python:   {sys.version}")
    print(f"Child PID: {child_pid}, SUBTAP_RUN_ID={run_id}")
    print(
        f"Cache TTL: {_IDENTITY_CACHE_TTL}s, MAX_ENTRIES: {_IDENTITY_CACHE_MAX_ENTRIES}"
    )
    print()

    # Verify the child can be identified before benchmarking.
    if not persisted_process_matches_task(child_pid, run_id):
        print("ERROR: child identity check failed before benchmark")
        child.kill()
        sys.exit(1)
    print("Identity verification: PASS (child process confirmed)")
    print()

    # ── 1. Uncached successful verification ──
    _IDENTITY_CACHE.clear()
    timings = []
    for _ in range(100):
        t0 = time.perf_counter_ns()
        persisted_process_matches_task(child_pid, run_id)
        t1 = time.perf_counter_ns()
        timings.append(t1 - t0)
        _IDENTITY_CACHE.clear()
    print("1. Uncached successful verification (cache cleared between each call)")
    us = [t / 1000.0 for t in timings]
    print(f"  median:   {median(us):8.2f} µs")
    print(f"  p95:      {p95(us):8.2f} µs")
    print(f"  max:      {max(us):8.2f} µs")
    uncached_median = median(us)

    # ── 2. Positive cache hit ──
    _IDENTITY_CACHE.clear()
    assert persisted_process_matches_task(child_pid, run_id) is True
    timings = []
    for _ in range(1000):
        t0 = time.perf_counter_ns()
        r = persisted_process_matches_task(child_pid, run_id)
        t1 = time.perf_counter_ns()
        timings.append(t1 - t0)
        assert r is True
    print("\n2. Positive cache hit (1000 calls inside TTL)")
    cache_us = [t / 1000.0 for t in timings]
    print(f"  median:   {median(cache_us):8.2f} µs")
    print(f"  p95:      {p95(cache_us):8.2f} µs")
    print(f"  max:      {max(cache_us):8.2f} µs")
    cache_hit_median = median(cache_us)

    # ── 3. Logical 1 Hz workload: 1000 simulated ticks ──
    _IDENTITY_CACHE.clear()
    liveness_calls = 0
    ps_calls = 0
    cache_hits = 0

    import subtap.ui.observer as _obs_mod
    import subtap.cli.pipeline_cli as _cli_mod

    # Fake monotonic clock so the cache TTL expires after 5 logical seconds.
    simulated_now = 0.0
    _real_monotonic = _obs_mod.time.monotonic
    _obs_mod.time.monotonic = lambda: simulated_now

    # Spy on _pid_is_alive
    _real_alive = _obs_mod._pid_is_alive

    def spy_alive(pid):
        global liveness_calls
        liveness_calls += 1
        return _real_alive(pid)

    _obs_mod._pid_is_alive = spy_alive

    # Spy on _observer_process_matches_run_id
    _real_ps = _cli_mod._observer_process_matches_run_id

    def spy_ps(pid, r_id):
        global ps_calls
        ps_calls += 1
        return _real_ps(pid, r_id)

    _cli_mod._observer_process_matches_run_id = spy_ps

    for tick in range(1000):
        simulated_now += 1.0  # 1 logical second per tick
        was_hit = (child_pid, run_id) in _IDENTITY_CACHE
        result = persisted_process_matches_task(child_pid, run_id)
        if result and was_hit:
            cache_hits += 1

    # Restore
    _obs_mod._pid_is_alive = _real_alive
    _cli_mod._observer_process_matches_run_id = _real_ps
    _obs_mod.time.monotonic = _real_monotonic

    ps_reduction_pct = (1 - ps_calls / 1000) * 100
    print("\n3. Logical 1 Hz workload (1000 simulated ticks)")
    print(f"  total logical ticks:  {1000}")
    print(f"  liveness (os.kill):   {liveness_calls}")
    print(f"  ps subprocess:        {ps_calls}")
    print(f"  cache hits:           {cache_hits}")
    print(f"  ps reduction:         {ps_reduction_pct:.1f}%")
    print(f"  expected (TTL=5s):    ~80%")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print(f"  uncached median:           {uncached_median:8.2f} µs  (ps subprocess)")
    print(f"  cache-hit median:          {cache_hit_median:8.2f} µs  (no ps)")
    print(
        f"  cache-hit μ-op speedup:    {uncached_median / max(cache_hit_median, 0.001):.0f}×"
    )
    print(f"  true 1Hz ps frequency:     ~1 per {1000/max(ps_calls,1):.0f} seconds")
    print(f"  ps reduction @ 1Hz TTL=5s: {ps_reduction_pct:.0f}%")
    print(
        f"  24h subprocess upper:      ~{ps_calls * 86400 // 1000:,} vs 86,400 baseline"
    )

    child.kill()
    child.wait()
