"""The one read tool. See docs/adr/0006: read-only is enforced twice — the connection
passed in must already be opened `mode=ro` (the real defence, in db.ro()), and here the
SQL text is rejected unless it is a single SELECT or WITH statement (turns a confused
write attempt into a clear error instead of relying solely on the connection)."""

import re
import sqlite3

_LEADING_COMMENT_OR_SPACE = re.compile(r"^\s*(--[^\n]*\n\s*)*", re.MULTILINE)
_ALLOWED_START = re.compile(r"^(select|with)\b", re.IGNORECASE)


def _strip_leading_comments(sql: str) -> str:
    prev = None
    stripped = sql
    while stripped != prev:
        prev = stripped
        stripped = _LEADING_COMMENT_OR_SPACE.sub("", stripped, count=1)
    return stripped


def query(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    statements = [s for s in sql.split(";") if s.strip()]
    if len(statements) != 1:
        raise ValueError("query must be a single statement")

    body = _strip_leading_comments(sql).lstrip()
    if not _ALLOWED_START.match(body):
        raise ValueError("query must be a single SELECT or WITH statement")

    return conn.execute(sql).fetchall()
