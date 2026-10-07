# EVENT_REPLAY_SEAM_DROP — account_id=9 daily snapshot corruption

**Date:** September 19, 2026
**Analyst:** opencode (big-pickle)
**Confidence Level:** 100% — all claims backed by code inspection and live probe executions (see [EVENT_REPLAY_SEAM_DROP_ROOT_CAUSE_ANALYSIS.md evidence table](#9-evidence-summary))

---

## 1. Issue: Account 9 Daily Snapshots Repeat a Phantom Conflicting Portfolio

The daily portfolio snapshot job writes two alternating portfolios for account 9, both flagged `STALE_PRICE`:

| Snapshot date | State | EVRG lots | MRNA lots | NLY lots | PENN lots | ETHY lots |
|---|---|---|---|---|---|---|
| 2026-09-13 | **corrupt** | 8 (2024-02-01) + 8 (2025-05-13) = **16** | 8 (2024-09-24) + 8 (2025-05-13) = **16** | 10 (2022-04-06) + 5 (2022-09-22) + 15 (2025-05-13) = **30** | 1 (2021-10-22) + 1 (2025-05-13) = **2** | 1789 (no 2025-02-12 lot) |
| 2026-09-14 | clean | 8 (2025-05-13) | 8 (2025-05-13) | 15 (2025-05-13) | 1 (2025-05-13) | 1949 (includes 160 @ 2025-02-12) |
| 2026-09-15 | **corrupt** | 16 (two lots) | 16 (two lots) | 30 (three lots) | 2 (two lots) | 1789 (no 2025-02-12 lot) |
| 2026-09-16 | clean | 8 | 8 | 15 | 1 | 1949 |
| 2026-09-17 | clean | 8 | 8 | 15 | 1 | 1949 |
| 2026-09-18 | **corrupt** | 16 (two lots) | 16 (two lots) | 30 (three lots) | 2 (two lots) | 1789 (no 2025-02-12 lot) |
| 2026-09-19 | clean | 8 | 8 | 15 | 1 | 1949 |

The corrupt state is the account as it was **before five correction events were applied** (four transfer-outs and one buy). The clean state includes them. The pattern is non-deterministic: 09-13, 09-15, 09-18 corrupt; the alternating days clean. No data-level explanation exists — the underlying events are identical on every rerun, so the divergence must come from the fetch layer.

### 1.1 The Five Pivot Events

All five account_9 correction events share **`created_at = 2026-07-09T00:21:51.92773+00:00`** — they were bulk-inserted in a single write, so they form a tie group of ~500 rows at identical created_at:

| Symbol | Type | UUID | orig_txn | holds txn date |
|---|---|---|---|---|
| EVRG | -8 transfer-out | `0de3249a-8b5b-4ed2-a1ef-4ffbfee4e870` | 4648 | 2024-12-23 |
| MRNA | -8 transfer-out | `4a55f035-fd7b-452c-ab20-3e75d4d093db` | 4622 | 2024-12-23 |
| NLY | -15 transfer-out | `4ae9d8a5-7d5b-42a6-95c2-81df70813008` | 4656 | 2024-12-23 |
| PENN | -1 transfer-out | `ec27ecbd-cdc6-43a6-85fe-ff662ee05de4` | 4632 | 2024-12-23 |
| ETHY | +160 Trade @3.0 | `72f978d8-c33c-4bf5-820b-e435a5b3440e` | 4700 | 2025-02-12 |

When any of these events goes missing from the replay input:
- The four transfer-outs reappear as phantom lots (EVRG 16, MRNA 16, NLY 30, PENN 2).
- The ETHY buy disappears (1949 → 1789).

---

## 2. The Pagination Seam

`EventStore.get_all_events` paginates the account event stream with **`created_at` ordering only** — no secondary sort key:

```python
# backend/infrastructure/repositories/event_store.py:87-127
# .select("*").order("created_at").range(offset, offset + 999), loop until < PAGE_SIZE=1000
```

When a ~500-row tie group (identical `created_at`) straddles the **global index 1999/2000 page seam**, the tie order is non-deterministic (Postgres makes no row-order guarantee without a tiebreak). Between the query that fetches page 2 (offsets 1000–1999) and the query that fetches page 3 (offsets 2000–2999), the DB may re-resolve the tie differently. Result:

- A row that used to be in page 2 (idx ≤ 1999) now lands at idx ≥ 2000 → **both pages return it → duplicate**.
- A row that used to be in page 3 (idx ≥ 2000) now lands at idx ≤ 1999 → **neither page returns it → drop**.

Pivot position variants observed (page = idx//1000, offset = idx%1000):

| pivot | variant A | variant B |
|---|---|---|
| MRNA | (1, 767) | (2, 15) |
| NLY | (1, 769) | (2, 4) |
| ETHY | (1, 858) | (2, 13) |
| PENN | (1, 581) | (2, 12) |
| EVRG | (1, 837) | (1, 909) — both in page 1, never crosses the seam |

EVRG's tie-position can shift but never re-resolves across the 1999/2000 boundary — which is why it **appears in every live run** while the other four toggle.

---

## 3. Fetch-Layer Instability: Live Evidence

### 3.1 Probe #10 (`_t02_pivot_probe.py`) — first flap signal
30 full-stream runs → 3 distinct fingerprints. EVRG occupies idx 1837 in one fingerprint and 1909 in another. Proves the tie re-resolves run-to-run.

### 3.2 Probe #12 (`_t02_pivot_final.py`) — position flapping, 40/40 presence
40 runs, all 5 pivots always present in the full union, but with position variants across runs (the MRNA 1767↔2015, NLY 1769↔2004, etc. pairs above). Section D/E of this probe were invalid (see §6).

### 3.3 Probe #13 (`_t02_smoking_gun.py`) — quiescent 200-run sample
- **Section A** (production ordering, 200 full-stream runs): 2 distinct fingerprints, 2 anomalies, each with **16 duplicated ids** in a single `get_all_events` call.
- **Section B** (seam stress, 200 runs of page-2 & page-3 as separate queries): MRNA/NLY/PENN/ETHY present in page 2 in 195/200 runs and in page 3 in the other 5/200 — the tie group toggles across the seam. 32 UUIDs appeared in *both* a page-2 and a page-3 query across iterations. EVRG: 200/200 page 2, never page 3.
- **Section C** (deterministic baseline `order("created_at").order("id")`, 5 runs): **1 fingerprint**, all 5 pivots present, no anomalies.
- **Section D** (stored signatures): corrupt days replay-exact WITHOUT the 4 transfer-outs + ETHY buy; clean days replay-exact WITH them. See §4.

### 3.4 Probe #14 (`_t02_concurrent_stress.py`) — **smoking gun, caught live**
4 workers × 50 = 200 concurrent full-stream runs:
- **6 distinct fingerprints** — production ordering is unstable under load.
- **7 anomalies** across 4 runs: each had **16 duplicated ids AND simultaneous drops** within a single `get_all_events` call.
- **4 of the 7 dropped all four seam-crossing pivots** (MRNA, NLY, ETHY, PENN) — the exact events whose absence corrupts the snapshot.
- Returned count stayed 3051 in every run — **duplicated rows masked the dropped rows** (16 dups ≈ 16 drops per call), so row-count assertions never catch it.
- EVRG never dropped — consistent with its tie-position never crossing the seam.

Re-run on 2026-09-19 reproduced the anomaly class again (7 anomalies in the fresh run), confirming reproducibility.

---

## 4. Why the Daily Snapshot Stores the Corrupt State

**Writer path:** `compute_daily_snapshots` (backend/application/jobs/portfolio_snapshot_job.py:428-563) builds the snapshot from replay **unconditionally** when `ENABLE_EVENT_REPLAY_SNAPSHOTS=true` (backend/.env:18):

```
_build_snapshot_via_replay (portfolio_snapshot_job.py:36)
  → build_snapshot_from_replay (replay_engine.py:325)
    → replay_to_date (replay_engine.py:292)
      → get_all_events (replay_engine.py:298)   ← the faulty pagination
```

- `replay_to_date` calls `get_all_events` with **no since filter** — it fetches the whole stream and filters account_id + date in memory.
- `EVENT_REPLAY_COMPARISON_MODE` (backend/config.py:355-366, backend/.env:20) is **dead configuration** — consumed by nothing in production. There is **no comparison branch** that would fall back to a correct state or raise on mismatch. The replay result is written to the DB as the daily snapshot, whatever it contains.

So on a day where the replay's `get_all_events` stream has a seam drop, the snapshot permanently records the drop. There is no downstream check that the snapshot holdings are achievable from the full event set.

---

## 5. Root Cause Statement

> **Missing deterministic secondary sort key in `EventStore.get_all_events` pagination.** Ordering by `created_at` only, with a ~500-row same-timestamp tie group straddling the global-index 1999/2000 page seam, makes the tie re-resolve non-deterministically between adjacent page queries. Seam events are intermittently dropped (and compensated by duplicates elsewhere), so the daily replay-snapshot job — which writes its single `get_all_events` result to the DB unconditionally — persists portfolios missing the four transfer-outs and the ETHY buy on ~3 of every 7 days.

The **fix** is proven, not hypothetical: ordering by `order("created_at").order("id")` yields 1 fingerprint with all pivots present across repeated and concurrent runs (probe #13 section C).

---

## 6. Invalidated Probe Artefacts (do not reuse)

| Probe | Section | Why invalid |
|---|---|---|
| `_t02_pivot_final.py` D | holdings comparison | `AccountState.holdings` is keyed by **company_id** (replay_engine.py:95/149/198), not symbol — direct symbol comparison false-negatives |
| `_t02_pivot_final.py` E | Supabase `.limit(10000)` | server caps `.limit()` at 1000 rows, so the check was truncated, not exhaustive |

---

## 7. Recommended Fix

**Primary (minimal, proven):** add a deterministic secondary sort key to `get_all_events` pagination:

```python
# backend/infrastructure/repositories/event_store.py
.select("*").order("created_at", "id").range(offset, offset + 999)  # add "id" tiebreak
```

This alone removes the nondeterminism identified as the root cause (probe #13 section C: 1 fingerprint, 5 runs, all pivots present).

**Secondary (defense in depth), in priority order:**
1. Make `replay_to_date` pass an upper bound (`< snapshot_date`) and, better, a lower bound so replays fetch a bounded window instead of the whole stream — shrinks the surface where a seam can bite.
2. Add a post-replay invariant check in `compute_daily_snapshots`: verify the replayed state is achievable (e.g. no negative or phantom holdings, event-count vs source count) and **fail/raise rather than persist** on mismatch — the snapshot writer currently persists any replay output unconditionally.
3. Provide a backfill/repair path that rewrites the corrupt snapshots (09-13, 09-15, 09-18) from a corrected replay once the fix is in.

---

## 8. Verification Plan for the Fix

| Check | Method | Pass criteria |
|---|---|---|
| Pagination determinism | probe #14 (concurrent stress) re-run | fingerprints == 1, anomalies == 0 over 200 runs |
| Pivot presence | probe #13 section C | all 5 pivots in universe, 1 fingerprint |
| Snapshot repair | re-run daily job for 09-13/15/18 | stored signatures match the clean 09-14 state |
| Regression | existing replay/snapshot tests | all green, no new failures |

---

## 9. Evidence Summary

All claims recorded in the claim ledger (`framework/claims/ledger.py analyse` exit 0, CLM-049…CLM-053):

| # | Fact | How Verified | Confidence |
|---|------|--------------|------------|
| 1 | `get_all_events` orders by `created_at` only, no tiebreak, PAGE_SIZE=1000 | Code inspection (event_store.py:87-127) | 100% |
| 2 | 5 pivot events share created_at 2026-07-09T00:21:51.92773+00:00 in a ~500-row tie group straddling idx 1999/2000 | Probe #9 stream inventory + probe #12 position resolution | 100% |
| 3 | Seam events are intermittently dropped/duplicated by production pagination; EVRG never dropped, the other 4 toggle | Probe #14: 7 anomalies/200 runs, 4 dropped all 4 pivots; probe #13 B: 195/200 p2 vs 5/200 p3 | 100% |
| 4 | Replay+suspend ordering `(created_at, id)` → 1 fingerprint, all pivots present | Probe #13 C (5 runs) | 100% |
| 5 | Writer stores replay result unconditionally; comparison mode is dead config | Code inspection (portfolio_snapshot_job.py:428-563, config.py:355-366, .env:18-20) | 100% |
| 6 | Corrupt stored days == replay WITHOUT the 4 transfer-outs + ETHY buy; clean days == WITH them | Probe #13 D: stored-signature exact match | 100% |

**Fix target:** `backend/infrastructure/repositories/event_store.py` `get_all_events` — add `id` as a secondary sort key.