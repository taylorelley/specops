"""SQLite database for admin data (teams, agents, users, plans)."""

import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

SCHEMA_SQL = """
-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    color TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    status TEXT DEFAULT 'stopped',
    base_path TEXT NOT NULL,
    agent_token TEXT NOT NULL,
    mode TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_agents_token ON agents(agent_token);

-- Plans table
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Plan columns (composite PK: same column IDs reused across plans)
CREATE TABLE IF NOT EXISTS plan_columns (
    id TEXT NOT NULL,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    position INTEGER DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'standard',
    PRIMARY KEY (id, plan_id)
);

CREATE INDEX IF NOT EXISTS idx_plan_columns_plan_id ON plan_columns(plan_id);

-- Plan tasks (column_id no FK to allow empty string before column assign)
CREATE TABLE IF NOT EXISTS plan_tasks (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    column_id TEXT DEFAULT '',
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    position INTEGER DEFAULT 0,
    requires_review INTEGER NOT NULL DEFAULT 1,
    review_status TEXT,
    reviewed_by TEXT DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    review_note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_tasks_plan_id ON plan_tasks(plan_id);

-- Task comments (human or agent)
CREATE TABLE IF NOT EXISTS task_comments (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES plan_tasks(id) ON DELETE CASCADE,
    author_type TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_comments_task_id ON task_comments(task_id);
CREATE INDEX IF NOT EXISTS idx_task_comments_plan_id ON task_comments(plan_id);

-- Plan-agent assignments (many-to-many)
CREATE TABLE IF NOT EXISTS plan_agents (
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    PRIMARY KEY (plan_id, agent_id)
);

-- Plan artifacts (metadata in SQLite; binary content in project_data/)
CREATE TABLE IF NOT EXISTS plan_artifacts (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    task_id TEXT DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    content_type TEXT DEFAULT 'text/plain',
    content TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    size INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_artifacts_plan_id ON plan_artifacts(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_artifacts_task_id ON plan_artifacts(plan_id, task_id);

-- Agent config (full config including secrets; single encrypted JSON blob)
CREATE TABLE IF NOT EXISTS agent_config (
    agent_id TEXT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

-- Agent variables (env vars for process/container; maps to Variables tab)
CREATE TABLE IF NOT EXISTS agent_variables (
    agent_id TEXT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    variables_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

-- Activity events (audit log; persisted when received from agents)
CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    channel TEXT DEFAULT '',
    content TEXT DEFAULT '',
    plan_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    tool_name TEXT,
    result_status TEXT,
    duration_ms INTEGER,
    event_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activity_events_agent_id ON activity_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_activity_events_agent_created ON activity_events(agent_id, id);
CREATE INDEX IF NOT EXISTS idx_activity_events_plan ON activity_events(agent_id, plan_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_events_agent_event_id ON activity_events(agent_id, event_id) WHERE event_id IS NOT NULL;

-- Agent shares (per-user access grants on an agent)
CREATE TABLE IF NOT EXISTS agent_shares (
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission TEXT NOT NULL CHECK (permission IN ('viewer', 'editor', 'manager')),
    granted_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (agent_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_shares_user_id ON agent_shares(user_id);

-- Plan shares (per-user access grants on a plan)
CREATE TABLE IF NOT EXISTS plan_shares (
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission TEXT NOT NULL CHECK (permission IN ('viewer', 'editor', 'manager')),
    granted_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (plan_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_plan_shares_user_id ON plan_shares(user_id);
"""


class Database:
    """SQLite database with schema creation and transaction support."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connection(self):
        """Context manager yielding a connection with foreign keys enabled and auto-commit on success."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Run schema migrations for existing databases."""
        # Add onboarding_completed to agents if missing
        agent_cols = {r[1] for r in conn.execute("PRAGMA table_info(agents)").fetchall()}
        if "onboarding_completed" not in agent_cols:
            conn.execute("ALTER TABLE agents ADD COLUMN onboarding_completed INTEGER DEFAULT 0")

        # Add owner_user_id to plans if missing, then backfill to the first admin.
        plan_cols = {r[1] for r in conn.execute("PRAGMA table_info(plans)").fetchall()}
        if "owner_user_id" not in plan_cols:
            conn.execute("ALTER TABLE plans ADD COLUMN owner_user_id TEXT DEFAULT ''")

        # Add kind to plan_columns (review-gate opt-in); existing rows default to 'standard'.
        plan_column_cols = {r[1] for r in conn.execute("PRAGMA table_info(plan_columns)").fetchall()}
        if "kind" not in plan_column_cols:
            conn.execute(
                "ALTER TABLE plan_columns ADD COLUMN kind TEXT NOT NULL DEFAULT 'standard'"
            )

        # Add review tracking fields to plan_tasks; existing rows default to
        # requires_review=1 so they respect any review column added later.
        plan_task_cols = {r[1] for r in conn.execute("PRAGMA table_info(plan_tasks)").fetchall()}
        if "requires_review" not in plan_task_cols:
            conn.execute(
                "ALTER TABLE plan_tasks ADD COLUMN requires_review INTEGER NOT NULL DEFAULT 1"
            )
        if "review_status" not in plan_task_cols:
            conn.execute("ALTER TABLE plan_tasks ADD COLUMN review_status TEXT")
        if "reviewed_by" not in plan_task_cols:
            conn.execute("ALTER TABLE plan_tasks ADD COLUMN reviewed_by TEXT DEFAULT ''")
        if "reviewed_at" not in plan_task_cols:
            conn.execute("ALTER TABLE plan_tasks ADD COLUMN reviewed_at TEXT DEFAULT ''")
        if "review_note" not in plan_task_cols:
            conn.execute("ALTER TABLE plan_tasks ADD COLUMN review_note TEXT DEFAULT ''")
        seed_admin = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if seed_admin is not None:
            admin_id = seed_admin["id"]
            conn.execute(
                "UPDATE plans SET owner_user_id = ? WHERE owner_user_id IS NULL OR owner_user_id = ''",
                (admin_id,),
            )
            conn.execute(
                "UPDATE agents SET owner_user_id = ? WHERE owner_user_id IS NULL OR owner_user_id = ''",
                (admin_id,),
            )


@lru_cache(maxsize=1)
def get_database() -> Database:
    """Return the shared SQLite database at storage root (cached)."""
    from specops_lib.storage import get_storage_backend, get_storage_root

    storage = get_storage_backend()
    root = get_storage_root(storage)
    return Database(root / "admin" / "admin.db")
