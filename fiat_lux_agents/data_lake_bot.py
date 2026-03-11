"""
DataLakeBot — LLM-powered querying for any folder of Parquet/CSV files.

Given a directory of data files (optionally with README.md schema docs), the bot
lets you ask natural-language questions and returns pandas DataFrames.

The LLM generates DuckDB SQL; DuckDB executes it against the actual files.

Usage:
    bot = DataLakeBot(data_path="/path/to/Data")
    df = bot.query("What were median home prices by metro in 2023?")

    # With manual schema override:
    bot = DataLakeBot(data_path="/path/to/Data", schema="custom catalog text")

    # Direct load:
    df = bot.load("Price/FHFA/hpi_national_annual.parquet")
    df = bot.load("ACS_1Y/acs_1y.parquet", sql="SELECT YEAR, AVG(HHINCOME) FROM tbl GROUP BY YEAR")
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import duckdb
import pandas as pd

from .base import LLMBase, clean_json_string, DEFAULT_MODEL


class DataLakeBot(LLMBase):
    """
    Natural-language querying over a directory of Parquet/CSV files via DuckDB.

    On construction, the bot discovers available files and reads any README.md
    files to build a schema catalog. The LLM uses this catalog to generate
    DuckDB SQL that references the correct files.

    Args:
        data_path: Root directory containing data files (Parquet, CSV).
        schema: Optional manual schema string. Overrides auto-discovery.
        auto_discover: If True (default), walk data_path to build catalog.
        model: Claude model to use.
        max_tokens: Max tokens for SQL generation responses.
    """

    def __init__(
        self,
        data_path: str,
        schema: Optional[str] = None,
        auto_discover: bool = True,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 4000,
    ):
        super().__init__(model=model, max_tokens=max_tokens)
        self.data_path = Path(data_path).expanduser().resolve()
        if not self.data_path.exists():
            raise ValueError(f"data_path does not exist: {self.data_path}")

        if schema:
            self._catalog = schema
        elif auto_discover:
            self._catalog = self.discover_schema()
        else:
            self._catalog = f"Data directory: {self.data_path}"

        self.system_prompt = self._build_system_prompt()

    # ── Schema discovery ────────────────────────────────────────────────────

    def discover_schema(self) -> str:
        """
        Walk data_path, collect README.md contents and file listings,
        and return a consolidated schema catalog string.
        """
        sections = [f"# Data Lake: {self.data_path}\n"]

        # Collect all data files
        data_files: Dict[str, List[str]] = {}
        for ext in ("*.parquet", "*.csv"):
            for p in sorted(self.data_path.rglob(ext)):
                rel = str(p.relative_to(self.data_path))
                parent = str(p.parent.relative_to(self.data_path))
                data_files.setdefault(parent, []).append(rel)

        # Read README.md files, organized by directory
        readme_dirs = set()
        for readme in sorted(self.data_path.rglob("README.md")):
            rel_dir = str(readme.parent.relative_to(self.data_path))
            readme_dirs.add(rel_dir)
            try:
                content = readme.read_text(encoding="utf-8", errors="ignore")
                sections.append(f"## {rel_dir or 'Root'}\n\n{content.strip()}\n")
            except Exception:
                pass

        # List any data files NOT covered by a README
        uncovered = {d: files for d, files in data_files.items() if d not in readme_dirs}
        if uncovered:
            sections.append("## Additional files (no README)\n")
            for d, files in uncovered.items():
                sections.append(f"### {d or 'Root'}")
                for f in files:
                    sections.append(f"  - {f}")
            sections.append("")

        return "\n".join(sections)

    # ── System prompt ────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        return f"""You are a data analyst with access to a DuckDB data lake.

{self._catalog}

DATA PATH ROOT: {self.data_path}

Your job is to answer questions by generating DuckDB SQL.

RESPONSE FORMAT — return ONLY valid JSON with exactly 2 fields:
{{
  "sql": "SELECT ... FROM read_parquet('{self.data_path}/path/to/file.parquet') ...",
  "explanation": "One sentence describing what this query does."
}}

SQL RULES:
- Always use read_parquet() or read_csv_auto() with ABSOLUTE paths
- Absolute path = {self.data_path}/<relative_path>
- Example: read_parquet('{self.data_path}/ACS_1Y/acs_1y.parquet')
- For CSVs: read_csv_auto('{self.data_path}/Price/Zillow/Metro_zhvi_sfr_time_series.csv')
- To scan all files in a folder: read_parquet('{self.data_path}/Price/FHFA/*.parquet')
- JOIN across files using their absolute paths in subqueries or CTEs
- LIMIT results to at most 10000 rows unless aggregating
- Always aggregate large microdata files (ACS, CPS) — never SELECT * on them
- Use proper column names from the schema above

No import statements. No markdown. Return ONLY the JSON object."""

    # ── Query ────────────────────────────────────────────────────────────────

    def query(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
        return_sql: bool = False,
    ) -> pd.DataFrame:
        """
        Answer a natural-language question by generating and executing DuckDB SQL.

        Args:
            question: Natural language question about the data.
            history: Optional list of prior {"role", "content"} conversation turns.
            return_sql: If True, return (DataFrame, sql_string) tuple instead.

        Returns:
            pandas DataFrame with query results, or (DataFrame, sql) if return_sql=True.

        Raises:
            RuntimeError: On API error or SQL execution failure.
        """
        messages = []
        if history:
            for turn in history[-6:]:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": question})

        response_text = self.call_api(self.system_prompt, messages)

        try:
            cleaned = clean_json_string(response_text)
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            parsed = self.parse_json_response(response_text)

        sql = parsed.get("sql", "").strip()
        if not sql:
            raise RuntimeError("LLM returned no SQL")

        try:
            df = duckdb.sql(sql).df()
        except Exception as e:
            raise RuntimeError(f"DuckDB error: {e}\n\nSQL:\n{sql}")

        if return_sql:
            return df, sql
        return df

    # ── Direct load ─────────────────────────────────────────────────────────

    def load(
        self,
        relpath: str,
        sql: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Load a data file directly, with optional SQL filter/aggregation.

        Args:
            relpath: Relative path from data_path (e.g. "ACS_1Y/acs_1y.parquet").
            sql: Optional DuckDB SQL using 'tbl' as the table alias.
                 E.g. "SELECT YEAR, COUNT(*) as n FROM tbl GROUP BY YEAR"
            limit: Optional row limit for SELECT * reads (default 100k).

        Returns:
            pandas DataFrame.
        """
        full_path = self.data_path / relpath
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")

        ext = full_path.suffix.lower()
        if ext == ".parquet":
            read_fn = f"read_parquet('{full_path}')"
        elif ext in (".csv", ".tsv"):
            read_fn = f"read_csv_auto('{full_path}')"
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        if sql:
            # Replace 'tbl' placeholder with the actual read expression
            actual_sql = sql.replace("tbl", read_fn)
        else:
            cap = limit or 100_000
            actual_sql = f"SELECT * FROM {read_fn} LIMIT {cap}"

        return duckdb.sql(actual_sql).df()

    # ── Schema access ────────────────────────────────────────────────────────

    @property
    def catalog(self) -> str:
        """Return the schema catalog string."""
        return self._catalog

    def list_files(self) -> List[str]:
        """Return list of all data files relative to data_path."""
        files = []
        for ext in ("*.parquet", "*.csv"):
            for p in sorted(self.data_path.rglob(ext)):
                files.append(str(p.relative_to(self.data_path)))
        return files
