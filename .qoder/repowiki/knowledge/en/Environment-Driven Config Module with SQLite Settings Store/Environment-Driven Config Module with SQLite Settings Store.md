---
kind: configuration_system
name: Environment-Driven Config Module with SQLite Settings Store
category: configuration_system
scope:
    - '**'
source_files:
    - fintech/config.py
    - app.py
---

# Configuration System

## Approach
FinViet Pro uses a minimal, code-first configuration approach centered on a single Python module (`fintech/config.py`). There is no external config file format (no `.env`, YAML, TOML, or JSON). Runtime values are read from environment variables via `os.environ.get` with hardcoded defaults. Application-level settings that users can change at runtime are persisted in the SQLite database under a key/value table.

## Key Files
- `fintech/config.py` — the sole configuration module: defines constants, env-driven overrides, default user settings, and domain data (universe groups, exchanges, signal labels).
- `app.py` — entry point that imports `DEBUG`, `HOST`, `PORT` from `fintech.config` and passes them to Flask's `app.run()`.
- `fintech/db.py` — provides the SQLite connection used by the settings store (see below).

## Architecture and Conventions

### Environment Variables
Three server-level settings are loaded from the environment with explicit defaults:
- `FINTECH_HOST` → defaults to `"127.0.0.1"`
- `FINTECH_PORT` → defaults to `5000`, coerced to `int`
- `FINTECH_DEBUG` → defaults to `"0"`; truthy only when exactly equal to `"1"`

These are imported directly by `app.py` and consumed by Flask's development server.

### Hardcoded Constants
All other application behavior is controlled by module-level constants in `fintech/config.py`:
- Data paths: `BASE_DIR`, `DATA_DIR`, `DB_PATH` (SQLite file at `data/fintech.db`).
- Cache lifetimes: `DEFAULT_HISTORY_DAYS=400`, `CACHE_HOURS=6`, `SYMBOLS_REFRESH_HOURS=72`, `FUNDAMENTALS_REFRESH_HOURS=24`.
- Signal thresholds: `SIGNAL_STRONG_BUY=62`, `SIGNAL_BUY=30`, `SIGNAL_SELL=-30`, `SIGNAL_STRONG_SELL=-62`.
- Domain tables: `UNIVERSE_GROUPS`, `EXCHANGES`, `INDEX_SYMBOLS`, `SIGNAL_META`.

The `DATA_DIR.mkdir(exist_ok=True)` call ensures the SQLite directory exists at import time.

### User Settings Store
`DEFAULT_SETTINGS` defines the schema of per-user settings stored in SQLite as key/value pairs. Keys include `equity`, `risk_pct`, `max_position_pct`, `kelly_mode`, `history_days`, `cache_hours`, `scan_minutes`, `min_avg_volume`, `lot`, `screener_max_symbols`. These are not loaded from files; they are seeded into the database and then read/written through the app's settings endpoints. The `kelly_mode` value is constrained to the string `"half"` (as documented in the comment) and `kelly_mode` is referenced elsewhere as part of the Kelly sizing logic.

### No Feature Flags or Secrets Management
There is no feature-flag framework, no secrets manager, and no encrypted config. API keys or tokens (if any) would need to be injected via environment variables using the same pattern as `FINTECH_*` — but none are currently defined beyond host/port/debug.

## Conventions and Constraints
- All server-level configuration goes through `os.environ.get` with an explicit default in `fintech/config.py`; nothing else reads environment variables for configuration.
- `FINTECH_DEBUG` is treated as a strict equality check against `"1"` (not a generic truthiness test), so only the literal string `"1"` enables debug mode.
- `FINTECH_PORT` is converted to `int` at load time; non-integer values will raise `ValueError` before the app starts.
- The SQLite database path is derived from `Path(__file__).resolve().parent.parent / "data" / "fintech.db"`, so it always resolves relative to the repo root regardless of the working directory.
- Default user settings are defined once in `DEFAULT_SETTINGS` and are the source of truth for the settings schema; consumers should not hardcode these keys elsewhere.
- Universe group codes in `UNIVERSE_GROUPS` are asserted to match the live Vietcap `getByGroup` endpoint (per the inline comment), making this list the canonical set of supported market segments.