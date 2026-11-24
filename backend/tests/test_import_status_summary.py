"""The import status endpoint must explain exactly what a repeat upload did.

A re-upload that adds 0 rows is a success, but only if the UI can tell the
user *why* (all rows were already imported) instead of showing a bare zero.
These tests pin the per-category breakdown and the counters behind it.
"""

import uuid
from unittest.mock import MagicMock

from api.portfolio import _import_status_summary
from infrastructure.repositories.portfolio_repository import PortfolioRepository


class TestImportStatusSummary:
    def test_exact_reupload_reports_every_row_as_already_imported(self):
        job = {
            "total_rows": 2488,
            "rows_parsed": 2463,
            "imported_rows": 0,
            "duplicate_rows": 2463,
            "error_rows": 25,
        }

        assert _import_status_summary(job) == {
            "new_entries": 0,
            "already_imported": 2463,
            "skipped_rows": 25,
            "accounts_created": 0,
            "accounts_updated": 0,
            "symbols_created": 0,
        }

    def test_partial_import_reports_new_duplicate_and_skipped(self):
        job = {
            "total_rows": 100,
            "rows_parsed": 95,
            "imported_rows": 3,
            "duplicate_rows": 92,
            "error_rows": 5,
            "accounts_created": 1,
            "accounts_updated": 4,
            "symbols_created": 2,
        }

        assert _import_status_summary(job) == {
            "new_entries": 3,
            "already_imported": 92,
            "skipped_rows": 5,
            "accounts_created": 1,
            "accounts_updated": 4,
            "symbols_created": 2,
        }

    def test_legacy_job_without_counters_derives_them_from_row_pipeline(self):
        # Jobs written before the counters existed still need to explain a
        # repeat upload: total -> parsed (skipped) -> inserted (duplicates).
        job = {
            "total_rows": 2488,
            "rows_parsed": 2463,
            "imported_rows": 0,
        }

        assert _import_status_summary(job)["already_imported"] == 2463
        assert _import_status_summary(job)["skipped_rows"] == 25


class TestImportProgressCounters:
    def test_completion_persists_the_categories_the_ui_displays(self):
        client = MagicMock()
        repo = PortfolioRepository(client=client)

        repo.update_import_progress(
            uuid.uuid4(),
            status="completed",
            rows_parsed=2463,
            rows_inserted=0,
            duplicate_rows=2463,
            skipped_rows=25,
            accounts_created=0,
            accounts_updated=4,
            symbols_created=0,
        )

        payload = client.table.return_value.update.call_args.args[0]
        assert payload["duplicate_rows"] == 2463
        assert payload["error_rows"] == 25
        assert payload["accounts_updated"] == 4
        assert payload["imported_rows"] == 0
        assert payload["status"] == "completed"
