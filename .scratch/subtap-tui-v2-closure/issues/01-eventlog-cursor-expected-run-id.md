# 01 — EventLogCursor expected_run_id validation

**What to build:** Add `expected_run_id` parameter to `EventLogCursor` so every schema-v2 event row's `run_id` is validated against the expected task identity. Legacy v1 rows are skipped (schema_version < 2 has no run_id field). ObserverHostApp passes `self._run_id`, RecordedTaskScreen passes `task_id`.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] EventLogCursor.__init__ accepts optional `expected_run_id: str | None`
- [ ] read_updates validates every parsed v2 row: `row["run_id"] == expected_run_id`
- [ ] Validation mismatch raises ValueError("任务日志行任务标识不匹配…")
- [ ] ObserverHostApp._build_presentation() passes `self._run_id` to cursor
- [ ] RecordedTaskScreen.__init__ passes `task_id` to cursor
- [ ] Legacy v1 rows (no schema_version or == 1) skip validation
- [ ] Test: cursor with matching run_id works
- [ ] Test: cursor with mismatched run_id raises
- [ ] Test: mid-log mixed run_id raises on first mismatch
