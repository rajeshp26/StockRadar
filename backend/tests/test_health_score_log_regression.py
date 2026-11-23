"""REG-006-HLTH: 'Upserted 16/17' means 16 changed rows out of 17 evaluated.

Observed symptom: `[HLTH] Upserted 16/17 health-score rows` was read as a partial
failure. The 17th row was unchanged and deliberately skipped (tag-based dedupe).
The message must state changed-vs-total explicitly so operators stop treating a
successful, idempotent upsert as a failure.
"""
from __future__ import annotations

from application.jobs.derived_financial_metrics_job import health_score_summary


def test_summary_states_changed_vs_total_explicitly():
    message = health_score_summary(16, 17)

    assert "16 changed" in message
    assert "17" in message
    assert "1 unchanged" in message
    assert "skipped" in message


def test_summary_when_every_row_changed():
    message = health_score_summary(17, 17)

    assert "17 changed" in message
    assert "0 unchanged" in message
