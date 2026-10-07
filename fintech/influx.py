"""InfluxDB 3 (Cloud Serverless) client wrapper.

Single lazy client shared by the storage layer. All application queries are
SQL through the Flight endpoint; writes use ``influxdb_client_3.Point``.
"""
from __future__ import annotations

import re
import threading
from typing import Any

from .config import INFLUX_BUCKET, INFLUX_HOST, INFLUX_ORG, INFLUX_TOKEN

_lock = threading.Lock()
_client = None

# A query against a measurement that has never been written returns a planning
# error (``table 'public.iox.x' not found``) instead of an empty result set.
_MISSING_TABLE = re.compile(r"table '[^']*' not found")


def configured() -> bool:
    return bool(INFLUX_TOKEN and INFLUX_HOST and INFLUX_ORG and INFLUX_BUCKET)


def _get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                from influxdb_client_3 import InfluxDBClient3

                _client = InfluxDBClient3(
                    host=INFLUX_HOST,
                    token=INFLUX_TOKEN,
                    org=INFLUX_ORG,
                    database=INFLUX_BUCKET,
                )
    return _client


def write_points(points: list) -> None:
    """Write a batch of ``Point`` objects (no-op for an empty batch)."""
    if not points:
        return
    _get_client().write(record=points, database=INFLUX_BUCKET)


def sql(statement: str) -> list[dict]:
    """Run a SQL query and return rows as plain dicts."""
    table = _get_client().query(query=statement, language="sql")
    return table.to_pylist()


def fetch(statement: str) -> list[dict]:
    """Like ``sql`` but treats a missing measurement (fresh bucket) as empty."""
    try:
        return sql(statement)
    except Exception as exc:  # noqa: BLE001 - only the missing-table case is swallowed
        if _MISSING_TABLE.search(str(exc)):
            return []
        raise


def sql_str(value: Any) -> str:
    """Render a value as a SQL string literal (single quotes doubled)."""
    return "'" + str(value).replace("'", "''") + "'"


def ensure_ready() -> None:
    """Fail fast with a clear message when the connection is not configured."""
    if not configured():
        raise RuntimeError(
            "InfluxDB chưa được cấu hình — đặt INFLUXDB_TOKEN (và HOST/ORG/BUCKET) "
            "trong biến môi trường hoặc file .env (xem .env.example)."
        )
    _get_client()


def client_info() -> dict:
    return {
        "host": INFLUX_HOST,
        "org": INFLUX_ORG,
        "bucket": INFLUX_BUCKET,
        "token_set": bool(INFLUX_TOKEN),
    }
