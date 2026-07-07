---

description: "Task list for SDK retry with backoff on HTTP 429 responses (IHS-249)"
---

# Tasks: SDK retry with backoff on HTTP 429 responses

**Input**: Design documents from `specs/ihs-249-sdk-429-retry/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present; critique applied)

**Tests**: INCLUDED — the spec's Testing Decisions and the feature request explicitly require unit tests for the pure handler and client-level tests parametrized across the async and sync clients.

**Organization**: Tasks are grouped by user story. Foundational phase builds the shared retry machinery (handler, error, config, drivers wired into all three send sites on both clients); the multipart body re-read fix (critique E2/X1 — Must-Address) lives there because every path flows through it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)

## Path Conventions

Single-project library: source under `infrahub_sdk/`, tests under `tests/unit/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new module and test files the feature will fill in.

- [X] T001 [P] Create new module `infrahub_sdk/rate_limit.py` with imports (`from __future__ import annotations`, `random`, `datetime`/`timezone`, `email.utils.parsedate_to_datetime`) and an empty `RateLimitRetryHandler` class stub.
- [X] T002 [P] Create test files `tests/unit/test_rate_limit.py` (handler unit tests) and `tests/unit/sdk/test_rate_limit_retry.py` (client-level tests) with module docstrings and pytest imports.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the shared retry machinery every user story depends on. Covers FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, and the E2/X1 multipart Must-Address.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Add four fields to `ConfigBase` in `infrahub_sdk/config.py` (alongside `retry_on_failure`/`retry_delay`): `rate_limit_retry_enabled: bool = True`, `rate_limit_max_retries: int = Field(default=5, ge=0)`, `rate_limit_backoff_base: float = Field(default=0.5, gt=0)`, `rate_limit_backoff_max: float = Field(default=60.0, gt=0)`, each with a `description=` per `contracts/config.md`. (FR-009)
- [X] T004 [P] Add `RateLimitError(Error)` to `infrahub_sdk/exceptions.py` with `__init__(self, url, attempts, retry_after=None, message=None)` storing `url`/`attempts`/`retry_after` and building a default message, per `contracts/rate_limit_error.md`. (FR-005)
- [X] T005 Implement `RateLimitRetryHandler` in `infrahub_sdk/rate_limit.py`: `__init__(max_retries, backoff_base, backoff_max)`, `parse_retry_after(header, *, now=None)` (delta-seconds via `int`; HTTP-date via `parsedate_to_datetime` floored at 0; malformed→`None`), `compute_backoff(attempt)` = `min(backoff_max, backoff_base * 2**attempt)`, `jittered_delay(ceiling)` = `random.uniform(0, ceiling)`, `next_delay(attempt, retry_after_header=None, *, now=None)` (honour parsed Retry-After clamped to max, else jittered backoff clamped to max), `should_retry(attempts_made)` = `attempts_made <= max_retries`. Per `contracts/rate_limit_retry_handler.md`. (FR-002, FR-003, FR-004)
- [X] T006 [P] Write handler unit tests in `tests/unit/test_rate_limit.py`: `compute_backoff` growth + clamp to `backoff_max`; `jittered_delay(c)` ∈ `[0, c]` and a sample of draws varies; `parse_retry_after` for delta-seconds, HTTP-date (fixed injected `now`), past date → `0.0`, malformed/empty → `None`; `next_delay` clamping and Retry-After-vs-computed selection; `should_retry` yields exactly `max_retries + 1` total sends. (Depends on T005 signatures; write to fail first.)
- [X] T007 Implement the async retry driver `_send_with_rate_limit_retry(self, send, url)` on `InfrahubClient` in `infrahub_sdk/client.py`: if `not config.rate_limit_retry_enabled` return `await send()`; else loop calling `send()`, count attempts, return on non-429, on 429 either sleep `await asyncio.sleep(handler.next_delay(...))` and log a `WARNING` (url, attempt, delay), or when `not handler.should_retry(...)` build `httpx.HTTPStatusError` via `response.raise_for_status()` and `raise RateLimitError(url, attempts, last_retry_after) from exc`. Wire it into `_request`. (FR-001, FR-005, FR-007, FR-009; depends on T003–T005)
- [X] T008 Implement the sync retry driver `_send_with_rate_limit_retry` on `InfrahubClientSync` in `infrahub_sdk/client.py` with identical logic using `time.sleep`, wired into the sync `_request`. Keep logic byte-for-byte parallel to the async variant (FR-008). (Depends on T003–T005)
- [X] T009 Wire the retry driver into `_request_multipart` on BOTH clients in `infrahub_sdk/client.py` — async `InfrahubClient._request_multipart` (L1383) and sync `InfrahubClientSync._request_multipart` (L2331) — AND implement the E2/X1 Must-Address fix on each: before each attempt, rewind every file object in the `files` payload (`seek(0)`) or materialize the multipart body to bytes once and re-send those bytes, so a retried upload carries the full body. (FR-006, FR-008 + critique E2/X1; depends on T007, T008)
- [X] T010 Wire the retry driver into `_get_streaming` on BOTH clients in `infrahub_sdk/client.py` — async `InfrahubClient._get_streaming` (L1455) and sync `InfrahubClientSync._get_streaming` (L3524) — so a 429 on stream initiation is retried before any body is consumed; the driver wraps opening the stream and reading the response status. (FR-006, FR-008; depends on T007, T008)

**Checkpoint**: Retry machinery is complete and applied on all three send sites of both clients. User story validation can now proceed.

---

## Phase 3: User Story 1 - Transparent retry-and-succeed (Priority: P1) 🎯 MVP

**Goal**: A 429 followed by a 200 returns the 200 result transparently, no error, no caller retry code.

**Independent Test**: Mock a transport returning `[429, 200]`; issue a request; assert the 200 payload is returned, no exception raised, and the transport was called twice.

- [X] T011 [P] [US1] Client-level test in `tests/unit/sdk/test_rate_limit_retry.py`: script `[429, 200]` via a mocked `requester`/`sync_requester` (or mocked transport), parametrized across `InfrahubClient` and `InfrahubClientSync`; assert result returned transparently, no exception, exactly two sends. Patch the driver sleep to avoid real waits. (SC-001)
- [X] T012 [US1] Confirm the `_request` path (used by `_get`/`_post`/`login`/`refresh_login`) returns non-429 responses untouched and retries a 429 transparently; adjust T007/T008 if the test reveals a gap. (SC-001)

**Checkpoint**: MVP — the SDK transparently rides through a transient 429 on both clients.

---

## Phase 4: User Story 2 - Respect `Retry-After` (Priority: P2)

**Goal**: The SDK waits the server-specified `Retry-After` duration (delta-seconds and HTTP-date), clamped to max, before retrying.

**Independent Test**: Script `429` with `Retry-After` then `200`; capture the driver's sleep argument; assert it ≈ header value (and ≈0 for a zero/past value, clamped when larger than max).

- [ ] T013 [P] [US2] Client-level tests in `tests/unit/sdk/test_rate_limit_retry.py` (parametrized async+sync): (a) `Retry-After: N` delta-seconds → wait ≈ N; (b) HTTP-date form → wait ≈ interval; (c) `Retry-After: 0` and past date → wait ≈ 0; (d) malformed header → falls back to computed backoff and still retries; (e) `Retry-After` > `rate_limit_backoff_max` → clamped to max. Patch/record the sleep argument. (SC-002, FR-003, FR-004)

**Checkpoint**: Server-directed backoff honoured on both clients.

---

## Phase 5: User Story 3 - Give up cleanly on sustained rate-limiting (Priority: P3)

**Goal**: Persistent 429 → after `rate_limit_max_retries` retries, raise one `RateLimitError` (with url/attempts/retry_after and chained `__cause__`), having logged each retry.

**Independent Test**: Script persistent `429` with `max_retries=5`; assert exactly 6 sends, one `RateLimitError`, its attributes, and one WARNING log per retry.

- [ ] T014 [P] [US3] Client-level tests in `tests/unit/sdk/test_rate_limit_retry.py` (parametrized async+sync): persistent `429` → exactly `max_retries + 1` sends; exactly one `RateLimitError` raised; assert `err.url`, `err.attempts == max_retries + 1`, `err.retry_after`, and `isinstance(err.__cause__, httpx.HTTPStatusError)`; with `caplog`, assert one `WARNING` per retry containing url, attempt number, and delay. (SC-004, FR-005, FR-007)
- [ ] T015 [US3] Verify the driver (T007/T008) synthesizes the terminal `httpx.HTTPStatusError` from the final 429 response and chains it as `RateLimitError.__cause__`, and tracks `last_retry_after`; refine if T014 fails. (FR-005)

**Checkpoint**: Clean, catchable, observable exhaustion on both clients.

---

## Phase 6: User Story 4 - Tune or disable the behaviour (Priority: P3)

**Goal**: Retry is tunable and fully disableable via `Config`, with identical behaviour across async and sync.

**Independent Test**: With `rate_limit_retry_enabled=False`, a single 429 raises immediately (no wait, one send); with altered `max_retries`/backoff, attempt counts and waits follow config.

- [ ] T016 [P] [US4] Client-level tests in `tests/unit/sdk/test_rate_limit_retry.py` (parametrized async+sync): (a) `rate_limit_retry_enabled=False` → a 429 surfaces the underlying HTTP error immediately, no `RateLimitError`, no wait, one send (SC-006, FR-009); (b) lowered `rate_limit_max_retries` → observed attempt count follows; (c) explicit async/sync parity assertion — same 429 sequence yields identical attempt counts, waits within jitter tolerance, and same error type (SC-005, FR-008).

**Checkpoint**: All four user stories independently functional and validated on both clients.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: FR-006 all-paths coverage, the E2/X1 regression guard, changelog, and repo gates.

- [ ] T017 [P] FR-006 all-paths test in `tests/unit/sdk/test_rate_limit_retry.py`: parametrize a `429→200` retry across a regular request, a multipart upload (`_request_multipart`), and streaming initiation (`_get_streaming`), on both clients; assert retry occurs on each. (FR-006)
- [ ] T018 [P] E2/X1 regression test in `tests/unit/sdk/test_rate_limit_retry.py`: a multipart upload returning `429` then `200` with non-empty file content; capture the body the transport receives per attempt and assert the second attempt carries the full body equal to the first (proves payload rewind/re-materialize). (Critique E2/X1)
- [ ] T019 [P] Add towncrier changelog fragments in `changelog/`: `1124.added.md` (transparent 429 retry with jittered backoff, `Retry-After` support, four `rate_limit_*` Config fields, new `RateLimitError`) and `1124.changed.md` (a persistent 429 now raises `RateLimitError` after retries exhaust instead of `httpx.HTTPStatusError`; the raw error is available via `__cause__`).
- [ ] T020 Run `uv run invoke docs-generate` (Config gained public fields) and confirm generated SDK docs update; do not hand-edit generated files.
- [ ] T021 Run `uv run invoke format lint-code` and `uv run pytest tests/unit/test_rate_limit.py tests/unit/sdk/test_rate_limit_retry.py` — all green (quickstart.md validation).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user stories. Internal order: T003/T004 [P] → T005 → T006 [P] / T007 / T008 → T009 / T010.
- **User Stories (Phases 3–6)**: All depend on Foundational completion. Because the machinery is shared, the stories are validation-led and can run in parallel once Phase 2 is done; recommended order P1 → P2 → P3 → P3.
- **Polish (Phase 7)**: Depends on Foundational (T017/T018) and all stories for T021.

### Within Each User Story

- Tests are written to fail first, then the foundational implementation is confirmed/adjusted to make them pass.

### Parallel Opportunities

- T001, T002 in parallel.
- T003, T004 in parallel; T006 parallel with T007/T008 once T005 lands.
- Story test tasks T011, T013, T014, T016 touch the same test file — treat as sequential edits (do NOT run in parallel to avoid conflicts) unless split into separate test functions by different agents; T017/T018/T019 are [P] across different files (T019 is changelog).

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (critical) → 3. Phase 3 US1 → validate `[429, 200]` transparent success on both clients → demo.

### Incremental Delivery

Foundation → US1 (MVP) → US2 (Retry-After) → US3 (clean give-up) → US4 (tune/disable + parity) → Polish (FR-006 coverage, E2 regression, changelog, gates). Each story is independently testable against the shared machinery.

---

## Notes

- [P] = different files, no dependencies. The single client test file makes most story test tasks sequential edits.
- The async and sync drivers (T007/T008) must stay logically identical (FR-008); review them together.
- Do not modify generated code (`protocols.py`). Run `docs-generate` for the new Config fields (T020).
- The multipart re-read fix (T009) is the critique's Must-Address — do not skip its regression test (T018).
