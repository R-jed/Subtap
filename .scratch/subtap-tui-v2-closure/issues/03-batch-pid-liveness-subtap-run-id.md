# 03 — Batch PID liveness verification + SUBTAP_RUN_ID injection

**What to build:** BatchTaskScreen reads persisted PID from StateStore for reopened batches. PID dead + manifest still live → observation_error + timer stop. Inject SUBTAP_RUN_ID=batch-task-id into batch subprocess env so single-task and batch share the same process-identity model.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] BatchScreen.start_batch() injects SUBTAP_RUN_ID into batch subprocess env
- [ ] BatchTaskScreen checks PID liveness via `_pid_is_alive()` for persisted batches
- [ ] PID dead + manifest status running/starting → observation_error + persist status + stop timer
- [ ] _observer_process_matches_run_id() works for batch tasks (SUBTAP_RUN_ID already in env)
- [ ] Test: batch PID initially alive → PID dead → observation_error + timer stopped
