# 02 — Terminal → New Task screen replacement semantics

**What to build:** When a terminal TaskScreen (completed/failed/interrupted) shows "新建任务", the action replaces the current screen instead of pushing. NewTranscriptionScreen replaces terminal screen; on submit, Task B replaces NewTranscriptionScreen. Consecutive 10 terminal→NewTask leaves stack depth bounded (no accumulation).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] TaskScreen.action_new_task() uses `app.switch_screen()` instead of `app.push_screen()` to replace terminal screen with NewTranscriptionScreen
- [ ] NewTranscriptionScreen._finish_review() on confirmed: `dismiss(command)` → caller does `switch_screen` to new ObserverTaskScreen or uses start_transcription which pushes
- [ ] Actually: TaskScreen.action_new_task() currently pushes NewTranscriptionScreen and the callback pushes ObserverTaskScreen. Need to: pop terminal, push NewTranscriptionScreen, on confirmed push ObserverTaskScreen. Alternative: switch_screen to NewTranscriptionScreen, on confirmed switch_screen to ObserverTaskScreen.
- [ ] The invariant: Home → A terminal → New Task → B → detach → Tasks → Escape → Home works correctly
- [ ] Test: consecutive 10 terminal→NewTask → screen stack depth <= 3 (home + tasks + active task)
