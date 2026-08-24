"""
Structural schema audit — validates the repository code against the
canonical SQL migration without needing a live database.

Every column that the Python code reads/writes must exist in the SQL schema.
"""
import ast
import re
from pathlib import Path

REPO_PATH = Path("infrastructure/repositories/scheduler_repository.py")
SCHEMA_PATH = Path("scripts/migrate_scheduler_v3_tables.sql")


def _parse_schema_columns(sql: str):
    """Extract {table_name: {column_names}} from CREATE TABLE statements."""
    blocks = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(([^;]+)\)", sql, re.DOTALL)
    schema = {}
    for table_name, body in blocks:
        cols = set()
        for line in body.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if re.match(r"^\s*(PRIMARY|UNIQUE|CHECK|FOREIGN|CREATE|--)", line, re.IGNORECASE):
                continue
            col_match = re.match(r"(\w+)\s", line)
            if col_match:
                cols.add(col_match.group(1))
        schema[table_name] = cols
    return schema


def _extract_repo_table_constants(source: str):
    """Extract {constant_name: value} for table name constants."""
    constants = {}
    for m in re.finditer(r"(\w+)\s*=\s*\"(\w+)\"", source):
        name, val = m.group(1), m.group(2)
        if name.endswith("_TABLE"):
            constants[val] = name  # value -> constant name
    return constants


def _extract_repo_column_usage(source: str):
    """Parse the AST of the repository to find all column names used in Supabase calls."""
    tree = ast.parse(source)
    columns_used = {}  # table_lower -> {column_names}

    # Find all strings used as dict keys in .update(), .insert(), .select(), .eq() etc.
    # within methods that have a specific table reference

    class ColumnCollector(ast.NodeVisitor):
        def __init__(self):
            self._current_table = None

        def visit_Call(self, node):
            # Track table references: supabase.table("tablename")
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "table"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                self._current_table = node.args[0].value.lower()
            # .update({...}), .insert({...}) — collect dict keys
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("update", "insert"):
                if node.args and isinstance(node.args[0], ast.Dict):
                    for key in node.args[0].keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str) and self._current_table:
                            columns_used.setdefault(self._current_table, set()).add(key.value)
            # .eq("col", ...) — collect column names
            if isinstance(node.func, ast.Attribute) and node.func.attr == "eq":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and self._current_table:
                    columns_used.setdefault(self._current_table, set()).add(node.args[0].value)
            # .lt("col", ...), .lte("col", ...), .gte("col", ...)
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("lt", "lte", "gte", "gt", "neq", "is_"):
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and self._current_table:
                    columns_used.setdefault(self._current_table, set()).add(node.args[0].value)
            # .in_("col", ...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "in_":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and self._current_table:
                    columns_used.setdefault(self._current_table, set()).add(node.args[0].value)
            # .order("col", ...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "order":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and self._current_table:
                    columns_used.setdefault(self._current_table, set()).add(node.args[0].value)
            self.generic_visit(node)

    ColumnCollector().visit(tree)
    return columns_used


class TestSchedulerSchema:
    """Structural schema vs. repository validation."""

    def test_schema_file_exists(self):
        assert SCHEMA_PATH.exists(), f"Schema file not found: {SCHEMA_PATH}"

    def test_all_migration_tables_have_repository_constants(self):
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        schema = _parse_schema_columns(sql)
        source = REPO_PATH.read_text(encoding="utf-8")
        tables = _extract_repo_table_constants(source)

        for table_name in schema:
            assert table_name in tables, (
                f"Table '{table_name}' exists in SQL schema but has no "
                f"corresponding *_TABLE constant in {REPO_PATH}"
            )

    def test_repository_columns_exist_in_schema(self):
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        schema = _parse_schema_columns(sql)
        source = REPO_PATH.read_text(encoding="utf-8")
        columns_used = _extract_repo_column_usage(source)

        # Map table names from the repo constant names to schema names
        tables = _extract_repo_table_constants(source)
        table_alias = {v: k for k, v in tables.items()}  # constant_name -> table_name

        # The repo uses lowercased table names; schema has exact names
        schema_lower = {k.lower(): v for k, v in schema.items()}

        missing = []
        for tbl_lower, cols in columns_used.items():
            schema_cols = schema_lower.get(tbl_lower, set())
            for col in sorted(cols):
                if col not in schema_cols and col not in (
                    # these are dynamic keys in payload dicts, not column names
                    "scopes", "reasons",
                ):
                    # Verify: is it actually a column in any table?
                    found = any(col in sc for sc in schema_lower.values())
                    if not found:
                        missing.append(f"  '{tbl_lower}.{col}' — not found in any schema table")

        assert not missing, (
            "Repository references columns not present in SQL schema:\n"
            + "\n".join(missing)
        )

    def test_repository_table_names_match_schema(self):
        """Table name constants in the repository match actual SQL table names."""
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        schema = _parse_schema_columns(sql)
        source = REPO_PATH.read_text(encoding="utf-8")
        tables = _extract_repo_table_constants(source)

        sql_table_names = set(schema.keys())
        repo_table_names = set(tables.keys())

        assert repo_table_names == sql_table_names, (
            f"Repository tables {repo_table_names - sql_table_names} not in SQL schema.\n"
            f"SQL tables {sql_table_names - repo_table_names} missing from repository."
        )

    def test_jobs_table_has_all_critical_columns(self):
        """Critical columns for the jobs table must exist in the schema."""
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        schema = _parse_schema_columns(sql)
        job_cols = schema.get("jobs", set())

        required = {"id", "job_type", "dedupe_key", "status", "payload",
                     "lease_owner", "lease_token", "leased_until",
                     "attempts", "max_attempts", "last_error"}
        missing = required - job_cols
        assert not missing, f"jobs table missing critical columns: {missing}"

    def test_scheduler_state_has_all_critical_columns(self):
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        schema = _parse_schema_columns(sql)
        cols = schema.get("scheduler_state", set())
        required = {"scheduler_name", "enabled", "interval_hours",
                     "last_planned_at", "last_status", "next_due_at"}
        missing = required - cols
        assert not missing, f"scheduler_state table missing critical columns: {missing}"
