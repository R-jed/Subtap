# 04 — Complete regression test suite

**What to build:** All tests required by the spec, organized by area. Uses spy/monkeypatch counters for bounded-work assertions.

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] A→B lifecycle using real start_transcription() (not manual reset)
- [ ] RecordedTaskScreen pipeline_end(interrupted) → INTERRUPTED presentation
- [ ] Batch 500-item: mount → load_manifest==1, 100 idle ticks → still 1, clear_options/add_options==0
- [ ] Batch PID alive→dead → observation_error + timer stopped
- [ ] EventLogCursor expected_run_id mismatch (constructor arg + mid-log mixed)
- [ ] Consecutive 10 terminal→NewTask → screen stack depth bounded
- [ ] existing tests pass (no regressions)
