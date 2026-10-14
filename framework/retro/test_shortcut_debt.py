"""Tests for the shortcut-debt harvester (framework/retro/shortcut_debt.py).

The marker is assembled from two strings so this test file does not itself
contain a harvestable marker (which would pollute the repository's own ledger).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).with_name("shortcut_debt.py")
M = "# " + "shortcut: "
P = "// " + "ponytail: "


def run(root, *args):
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_clean_tree_is_exit_0_and_clean_ledger(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    rc, out, _ = run(tmp_path)
    assert rc == 0
    assert "Clean ledger" in out
    assert "0 markers" not in out


def test_marker_with_trigger(tmp_path):
    (tmp_path / "worker.py").write_text(
        f"def spawn():\n    x = 1  {M}single-process only, add a second worker process\n",
        encoding="utf-8",
    )
    rc, out, _ = run(tmp_path)
    assert rc == 0
    assert 'ceiling="single-process only"' in out
    assert 'upgrade="add a second worker process"' in out
    assert "1 markers, 0 with no trigger." in out


def test_marker_without_trigger_is_exit_1(tmp_path):
    (tmp_path / "tz.py").write_text(f"TZ = 'UTC'  {M}UTC only\n", encoding="utf-8")
    rc, out, _ = run(tmp_path)
    assert rc == 1
    assert 'upgrade="MISSING"' in out
    assert "1 markers, 1 with no trigger." in out


def test_empty_upgrade_is_no_trigger(tmp_path):
    (tmp_path / "a.py").write_text(f"x = 1  {M}UTC only,\n", encoding="utf-8")
    rc, out, _ = run(tmp_path)
    assert rc == 1
    assert "1 with no trigger." in out


def test_legacy_ponytail_marker(tmp_path):
    (tmp_path / "a.js").write_text(
        f"{P}no retry, when the vendor adds a health endpoint\n", encoding="utf-8"
    )
    rc, out, _ = run(tmp_path)
    assert rc == 0
    assert 'ceiling="no retry"' in out


def test_prose_is_not_a_marker(tmp_path):
    (tmp_path / "notes.md").write_text(
        "- Keyboard shortcut: Ctrl+S\n"
        "Four steps, in order, no shortcut:\n"
        "See the shortcut: convention in the rules.\n",
        encoding="utf-8",
    )
    rc, out, _ = run(tmp_path)
    assert rc == 0
    assert "Clean ledger" in out


def test_gitignore_is_respected_in_a_git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "b.py").write_text(f"x = 1  {M}no trigger here\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text(
        f"x = 1  {M}slow path, upgrade above 10k rows\n", encoding="utf-8"
    )
    rc, out, _ = run(tmp_path)
    assert rc == 0
    assert "kept.py" in out
    assert "ignored/" not in out
    assert "1 markers, 0 with no trigger." in out


def test_json_output(tmp_path):
    (tmp_path / "a.py").write_text(
        f"x = 1  {M}O(n^2), when rows exceed 10k\n", encoding="utf-8"
    )
    rc, out, _ = run(tmp_path, "--json")
    assert rc == 0
    payload = json.loads(out)
    assert payload["count"] == 1
    assert payload["no_trigger"] == 0
    row = payload["markers"][0]
    assert row["file"] == "a.py"
    assert row["has_trigger"] is True


def test_bare_marker_without_ceiling_is_ignored(tmp_path):
    # a comment that merely mentions the marker, with nothing after it
    (tmp_path / "a.py").write_text("# " + "shortcut:\n", encoding="utf-8")
    rc, out, _ = run(tmp_path)
    assert rc == 0
    assert "Clean ledger" in out


def test_missing_root_is_usage_error():
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--root", "does-not-exist-xyz"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "not a directory" in proc.stderr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
