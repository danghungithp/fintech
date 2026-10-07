---
kind: error_handling
name: Flask Route-Level try/except with Localized JSON Error Responses
category: error_handling
scope:
    - '**'
source_files:
    - fintech/routes.py
    - fintech/market.py
    - fintech/db.py
    - fintech/config.py
    - fintech/kelly.py
    - app.py
---

## Approach

FinViet Pro uses a **route-level, exception-catch pattern** rather than a centralized error middleware or custom exception hierarchy. Each Flask route wraps its body in `try` / `except` blocks and converts caught exceptions into JSON via a local helper.

- The only HTTP entry point is `app.py`, which calls `fintech.create_app()` (from `fintech/__init__.py`) and runs the Flask dev server; no global `@app.errorhandler` decorators are registered there.
- There is no dedicated `errors/` package, no sentinel error classes defined in this repo, and no `panic`/`recover` equivalent — Python exceptions are used directly.

## Key Files

- `fintech/routes.py` — defines the `api_error(message, status=400)` helper and all route handlers that catch and translate exceptions.
- `fintech/market.py` — catches `vietcap.VietcapError` from the external Vietcap client and either falls back to SQLite cache or raises domain `ValueError`s.
- `fintech/db.py` — uses a `get_db()` context manager that commits on success and rolls back on any exception before re-raising.
- `fintech/config.py` — catches `OSError` when probing the filesystem for Vercel compatibility.
- `fintech/kelly.py` — catches `(TypeError, ValueError)` around numeric parsing.

## Architecture & Conventions Observed

1. **Local JSON error helper.**
   `routes.api_error(message, status=400)` returns `(jsonify({"error": str(message)}), status)`. Every route that can fail returns an `api_error(...)` response instead of raising.

2. **Exception-to-HTTP mapping per route.**
   Routes distinguish between expected input errors and unexpected failures:
   - `ValueError` → typically mapped to `400` (e.g. missing `symbol`, invalid Kelly parameters).
   - `vietcap.VietcapError` → mapped to `502` (external data source failure).
   - Catch-all `Exception` → mapped to `500` (or `502` for symbol listing refresh).
   Example patterns from `routes.py`:
   ```python
   except (ValueError, vietcap.VietcapError) as exc:
       return api_error(str(exc), 400 if isinstance(exc, ValueError) else 502)
   except Exception as exc:  # noqa: BLE001
       return api_error(f"Lỗi phân tích: {exc}", 500)
   ```

3. **Localized error messages.**
   Error strings are written in Vietnamese (e.g. `"Không tải được danh sách mã: {exc}"`, `"Thiếu tham số symbol"`, `"Giá cắt lỗ phải thấp hơn giá vào lệnh"`). This is a consistent convention across routes.

4. **Best-effort fallbacks at the service layer.**
   `market.get_candles` catches `vietcap.VietcapError` and returns cached data when available, otherwise raises a descriptive `ValueError("Không lấy được dữ liệu giá cho {symbol}")`. `get_fundamentals` and `dividend_events` swallow `vietcap.VietcapError` and fall back to the local SQLite cache. `index_summary` swallows `(vietcap.VietcapError, ValueError, OSError)` and emits a row with `None` fields.

5. **Database transaction safety via context manager.**
   `db.get_db()` (`contextmanager`) commits on success, rolls back on any exception, then closes the connection and re-raises. All SQL helpers (`query`, `execute`, `executemany`) go through it.

6. **Input validation is inline and silent.**
   Numeric query-string parsing uses `_int_arg(name, default)` which silently returns the default on `(TypeError, ValueError)`. Settings POSTing silently skips keys not in `ALLOWED_SETTINGS` and silently ignores non-numeric or negative values. No explicit 4xx is returned for these cases — they are treated as no-op updates.

7. **Suppressed broad exceptions carry a linter directive.**
   Catch-all `except Exception` blocks are annotated with `# noqa: BLE001` (flake8-bugbear), indicating awareness that broad exception catching is intentional but flagged by lint rules.

8. **No global error handler.**
   `app.py` does not register `@app.errorhandler`; unhandled exceptions will propagate to Flask's default 500 page. The codebase relies on each route swallowing and translating exceptions rather than centralizing that logic.

9. **External library errors are handled at the boundary.**
   `vietcap.VietcapError` is caught wherever the external Vietcap client is called (`market.py`, `routes.py`); application code above never sees it. `OSError` is also caught alongside it where filesystem/network I/O may fail.

## Constraints / Rules

- There is no repository-defined exception class hierarchy — the only custom exception type referenced is `vietcap.VietcapError` from the third-party `vietcap` package.
- Routes consistently map `ValueError` → 4xx (usually 400) and `vietcap.VietcapError` → 502; catch-all `Exception` → 500/502. This is an observed convention enforced by the route bodies themselves, not by a decorator or framework rule.
- Database mutations always go through `get_db()`, which enforces commit-on-success / rollback-on-exception semantics.
- No `raise ... from` chaining is used; caught exceptions are converted to strings in error responses.
- No `try/finally` blocks outside the `get_db()` context manager are present for resource cleanup.