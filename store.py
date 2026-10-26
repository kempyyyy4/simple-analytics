"""Local storage: the last pull (SQLite) and the editable targets and diagnosis files (JSON)."""
import json
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULTS = HERE / "defaults"
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Rupert Analytics"
DB_PATH = DATA_DIR / "cache.db"


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("targets.json", "diagnosis.json"):
        if not (DATA_DIR / name).exists():
            shutil.copyfile(DEFAULTS / name, DATA_DIR / name)


def _db():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    return conn


def load_snapshot():
    """The last successful pull, or None if there isn't one yet."""
    try:
        with closing(_db()) as db:
            row = db.execute("SELECT v FROM kv WHERE k = 'snapshot'").fetchone()
    except (OSError, sqlite3.Error, ValueError):
        return None
    return json.loads(row[0]) if row else None


def save_snapshot(raw):
    with closing(_db()) as db:
        db.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('snapshot', ?)", (json.dumps(raw),))
        db.commit()


def load_config(name):
    """Returns (data, warning). Falls back to the shipped defaults if the user's copy can't be read."""
    _ensure_dir()
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8")), None
    except (OSError, ValueError) as e:
        data = json.loads((DEFAULTS / name).read_text(encoding="utf-8"))
        return data, f"{name} couldn't be read ({e}), so the built-in defaults are in use. Fix the file in {DATA_DIR}."


def save_targets(targets):
    _ensure_dir()
    (DATA_DIR / "targets.json").write_text(json.dumps(targets, indent=2), encoding="utf-8")
