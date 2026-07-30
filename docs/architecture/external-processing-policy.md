# External Processing Policy

## Overview

Single authoritative policy governing every path that can send audio or subtitle
text outside the local machine.  Created during Runtime Closure R1.

## Location

- **Policy object:** `src/subtap/runtime/external_policy.py`
- **Enforcement:** `src/subtap/core/clean.py`, `src/subtap/core/asr.py`,
  `src/subtap/core/translate.py`, `src/subtap/core/pipeline.py`
- **CLI consumption:** `src/subtap/cli/pipeline_cli.py`, `src/subtap/cli/batch_cli.py`
- **Persistence/resume:** `src/subtap/engine/state.py` (via `PipelineRunContext`),
  `src/subtap/engine/controller.py`
- **Tests:** `tests/test_external_processing_policy.py`

## Policy Precedence

1. `local_only=True` — denies every remote feature regardless of other flags.
2. `enhance=off` — denies clean-stage LLM features (proofread, hotword).
3. `enhance=local` — denies clean-stage LLM features.
4. `enhance=api` — permits clean-stage LLM features per resolved booleans.
5. **remote ASR** — evaluated separately via backend name,
   subject to local_only + disclosure.
6. **translation** — evaluated separately via the translate flag,
   subject to local_only + disclosure.

## Truth Table

The `ExternalProcessingPolicy` frozen dataclass holds resolved booleans.
Downstream code reads these booleans; it never re-resolves string-based flags.

```
local_only  enhance   remote_asr  proofread  hotword  translation
─────────────────────────────────────────────────────────────────
False       off       False       False      False    False
False       local     False       False      False    False
False       api       varies*     varies     varies   varies
True        *         Denied      Denied     Denied   Denied
```

- `remote_asr`: True when local_only is False AND asr_backend is "http-asr".
- `proofread/hotword`: In api mode, None→True, explicit value→as-set.
- `translation`: True when local_only is False AND translate is requested.

## Audio vs Text Disclosure

The policy distinguishes two data kinds via `ExternalDataKind` enum:

| Kind | Trigger | Disclosure |
|---|---|---|
| `AUDIO` | `asr_backend="http-asr"` | "音频将发送至外部 ASR 服务" |
| `SUBTITLE_TEXT` | `llm_proofread or llm_hotword or translation` | "字幕文本将发送至外部 LLM 服务" |

Disclosures are derived from the policy object (not from string checks).
When no external processing is active, `disclosure_lines()` returns empty list.

## Enforcement Points

### Core stage enforcement (permission, not just UI validation)

| Function | Policy check | Effect |
|---|---|---|
| `run_clean()` | `assert_clean_llm_allowed()` | Denies LLM backend construction |
| `run_asr()` | `assert_remote_asr_allowed()` | Denies HttpASRBackend construction |
| `run_translate()` | `assert_translation_allowed()` | Denies translator backend construction |

Each enforcement point fires before backend construction, so denied paths never
reach the network layer.

### CLI enforcement (validation + disclosure)

| Command | Validation | Disclosure |
|---|---|---|
| `subtap run` | `_validate_run_params()` → `parse_enhance_mode()` | `_warn_external_api_use()` via policy |
| `subtap batch-transcribe` | `parse_enhance_mode()` at entry | Via RichRunner |
| `subtap ... --observer-child` | Same path as parent (CLI flags preserved) | Child re-derives from flags |

## Persistence / Resume / Retry

`PipelineRunContext` (persisted in `pipeline-state.json`) contains all fields
needed to reconstruct the original policy:

- `enhance` — original enhance mode
- `local_only` — hard security boundary
- `llm_proofread`, `llm_hotword` — resolved booleans
- `asr_backend` — backend name (for remote ASR detection)
- `translate_to` — translation target

On resume/retry, `PipelineController._build_policy_from_context()` rebuilds the
`ExternalProcessingPolicy` from persisted context and passes it to the
`TrackedPipeline`. Execution-time enforcement remains active.

### Resume guarantees

- local-only remains a hard deny on resume/retry.
- A local/off run does not become API-enabled because current config changed.
- An API run is not silently treated as local because current config changed.

### Batch resume

Batch manifest stores `params.enhance` from the original run. On resume/retry,
the persisted enhance mode is restored to prevent escalation. Full deterministic
batch resume is **not yet solved** — deferred to R3.

## Note on `resolve_llm_flags()`

The legacy `resolve_llm_flags()` function in `core/clean.py` remains for
call paths not yet migrated to the policy object.  It correctly handles
`enhance_mode="off"` → both flags False.  All new code should use
`ExternalProcessingPolicy` instead.
