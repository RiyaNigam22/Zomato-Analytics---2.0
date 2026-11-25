"""Initialize PostgreSQL schema from sql/schema.sql or SQLAlchemy metadata."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.connection import get_engine
from src.db.models import Base


def _split_sql_statements(sql_text: str) -> list[str]:
    """Strip UTF-8 BOM and -- line comments, then split on semicolons."""
    cleaned_lines: list[str] = []
    for line in sql_text.lstrip("\ufeff").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned_sql = "\n".join(cleaned_lines)
    return [stmt.strip() for stmt in cleaned_sql.split(";") if stmt.strip()]


def apply_sql_schema(schema_path: Path, database_url: str | None = None) -> None:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    sql_text = schema_path.read_text(encoding="utf-8-sig")
    engine = get_engine(database_url)
    with engine.begin() as conn:
        for statement in _split_sql_statements(sql_text):
            conn.execute(text(statement))


def create_all_orm_tables(database_url: str | None = None) -> None:
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize Zomato Analytics 2.0 PostgreSQL schema.")
    parser.add_argument(
        "--schema-file",
        type=Path,
        default=PROJECT_ROOT / "sql" / "schema.sql",
        help="Path to SQL schema file",
    )
    parser.add_argument(
        "--use-orm",
        action="store_true",
        help="Create tables via SQLAlchemy Base.metadata instead of executing schema.sql",
    )
    args = parser.parse_args()
    if args.use_orm:
        create_all_orm_tables()
    else:
        apply_sql_schema(args.schema_file)
    print("PostgreSQL schema initialized successfully.")


if __name__ == "__main__":
    main()
