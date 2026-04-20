import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent.application.ports.outbound.analytics_db_interface import AnalyticsDB


class SQLiteAnalyticsAdapter(AnalyticsDB):
    def __init__(self, path: str | Path):
        db_path = Path(path)
        if db_path.is_dir() or db_path.suffix == "":
            db_path = db_path / "analytics.sqlite3"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    initial_prompt TEXT NOT NULL,
                    global_goal TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    latency_ms INTEGER,
                    status TEXT NOT NULL DEFAULT 'running',
                    goal_achieved INTEGER NOT NULL DEFAULT 0,
                    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    total_nodes INTEGER NOT NULL DEFAULT 0,
                    cached_node_count INTEGER NOT NULL DEFAULT 0,
                    new_node_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            existing_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(agent_runs)").fetchall()
            }
            missing_columns = {
                "goal_achieved": "INTEGER NOT NULL DEFAULT 0",
                "total_nodes": "INTEGER NOT NULL DEFAULT 0",
                "cached_node_count": "INTEGER NOT NULL DEFAULT 0",
                "new_node_count": "INTEGER NOT NULL DEFAULT 0",
            }
            for column_name, column_type in missing_columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE agent_runs ADD COLUMN {column_name} {column_type}"
                    )

            existing_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(agent_runs)").fetchall()
            }
            if "plan_node_count" in existing_columns and "total_nodes" in existing_columns:
                connection.execute(
                    """
                    UPDATE agent_runs
                    SET total_nodes = plan_node_count
                    WHERE total_nodes = 0 AND plan_node_count > 0
                    """
                )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_call_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
                )
                """
            )
            connection.commit()

    def _to_iso(self, value: datetime) -> str:
        return value.isoformat(timespec="seconds")

    def save_run_start(
        self,
        run_id: str,
        initial_prompt: str,
        global_goal: str,
        started_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO agent_runs (
                    run_id,
                    initial_prompt,
                    global_goal,
                    started_at,
                    status,
                    goal_achieved,
                    total_prompt_tokens,
                    total_completion_tokens,
                    total_tokens
                ) VALUES (?, ?, ?, ?, 'running', 0, 0, 0, 0)
                """,
                (run_id, initial_prompt, global_goal, self._to_iso(started_at)),
            )
            connection.commit()

    def save_call(
        self,
        run_id: str,
        phase: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        created_at: datetime,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_call_analytics (
                    run_id,
                    phase,
                    model,
                    provider,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    phase,
                    model,
                    provider,
                    int(prompt_tokens),
                    int(completion_tokens),
                    int(total_tokens),
                    self._to_iso(created_at),
                ),
            )
            connection.commit()

    def save_run_finish(
        self,
        run_id: str,
        finished_at: datetime,
        latency_ms: int,
        total_prompt_tokens: int,
        total_completion_tokens: int,
        total_tokens: int,
        total_nodes: int,
        cached_node_count: int,
        new_node_count: int,
        status: str = "completed",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET finished_at = ?,
                    latency_ms = ?,
                    status = ?,
                    total_prompt_tokens = ?,
                    total_completion_tokens = ?,
                    total_tokens = ?,
                    total_nodes = ?,
                    cached_node_count = ?,
                    new_node_count = ?
                WHERE run_id = ?
                """,
                (
                    self._to_iso(finished_at),
                    int(latency_ms),
                    status,
                    int(total_prompt_tokens),
                    int(total_completion_tokens),
                    int(total_tokens),
                    int(total_nodes),
                    int(cached_node_count),
                    int(new_node_count),
                    run_id,
                ),
            )
            connection.commit()

    def mark_goal_achieved(self, run_id: str, goal_achieved: bool = True) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET goal_achieved = ?
                WHERE run_id = ?
                """,
                (1 if goal_achieved else 0, run_id),
            )
            connection.commit()
