from pathlib import Path
import sqlite3
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "qa_demo.db"

TEST_CASES = [
    ("TC-API-001", "Health endpoint", "API", "Checks that the demo API is healthy."),
    ("TC-API-002", "List demo users", "API", "Checks that seeded dummy users are returned."),
    ("TC-API-003", "Successful migration simulation", "E2E", "Simulates a user migration without changing a real system."),
    ("TC-API-004", "Unknown user negative test", "Negative", "Checks controlled handling of an unknown user."),
    ("TC-LOG-001", "Error log capture", "Logging", "Checks that a simulated error is recorded."),
    ("TC-UI-001", "Demo UI smoke test", "UI", "Uses Playwright to validate the dummy web page."),
    ("TC-CALL-001", "Simulated call lifecycle", "Calling", "Validates create, answer, established and hang-up states in the Python call simulator."),
    ("TC-SIP-001", "Simulated call media boundary", "SIP (simulated)", "Checks the in-memory simulator reports simulated media and does not generate RTP or audio."),
    ("TC-SIP-002", "Simulated SIP endpoint validation", "SIP (simulated)", "Checks unknown and identical extensions are rejected by the in-memory call simulator."),
    ("TC-SIP-003", "Simulated SIP call-state validation", "SIP (simulated)", "Checks invalid answer and hang-up state transitions are rejected by the in-memory call simulator."),
]
PLANS = [
    ("PLAN-SMOKE", "Smoke Test Plan", "Quick API and browser smoke checks."),
    ("PLAN-API-REG", "API Regression Plan", "API behavior, negative handling, and log checks."),
    ("PLAN-SIP", "SIP Test Plan (Simulated)", "Simulated call lifecycle, media boundary, endpoint validation, and call-state validation; does not send SIP traffic."),
    ("PLAN-FULL", "Full Demo Regression", "All available demo test cases."),
]
PLAN_CASES = {
    "PLAN-SMOKE": ["TC-API-001", "TC-API-002", "TC-UI-001"],
    "PLAN-API-REG": ["TC-API-001", "TC-API-002", "TC-API-003", "TC-API-004", "TC-LOG-001"],
    "PLAN-SIP": ["TC-CALL-001", "TC-SIP-001", "TC-SIP-002", "TC-SIP-003"],
    "PLAN-FULL": [row[0] for row in TEST_CASES],
}

def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con

def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS test_cases (
                test_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS test_plans (
                plan_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS plan_cases (
                plan_id TEXT NOT NULL,
                test_id TEXT NOT NULL,
                PRIMARY KEY (plan_id, test_id)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                selected_ids TEXT NOT NULL,
                plan_id TEXT,
                sip_profile TEXT NOT NULL DEFAULT 'generic',
                api_profile TEXT NOT NULL DEFAULT 'fastapi',
                passed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                duration_seconds REAL NOT NULL DEFAULT 0,
                output TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        execution_columns = {
            row["name"] for row in con.execute("PRAGMA table_info(executions)")
        }
        for column_name, definition in (
            ("plan_id", "TEXT"),
            ("sip_profile", "TEXT NOT NULL DEFAULT 'generic'"),
            ("api_profile", "TEXT NOT NULL DEFAULT 'fastapi'"),
        ):
            if column_name not in execution_columns:
                con.execute(f"ALTER TABLE executions ADD COLUMN {column_name} {definition}")
        for row in TEST_CASES:
            con.execute("INSERT OR IGNORE INTO test_cases VALUES (?, ?, ?, ?)", row)
        for row in PLANS:
            con.execute("INSERT OR IGNORE INTO test_plans VALUES (?, ?, ?)", row)
        for plan_id, ids in PLAN_CASES.items():
            for test_id in ids:
                con.execute(
                    "INSERT OR IGNORE INTO plan_cases (plan_id, test_id) VALUES (?, ?)",
                    (plan_id, test_id),
                )
        _backfill_execution_plans(con)


def _backfill_execution_plans(con: sqlite3.Connection) -> None:
    import json

    plans = {
        row["plan_id"]: {
            case["test_id"]
            for case in con.execute(
                "SELECT test_id FROM plan_cases WHERE plan_id = ?", (row["plan_id"],)
            )
        }
        for row in con.execute("SELECT plan_id FROM test_plans ORDER BY plan_id")
    }
    executions = con.execute(
        "SELECT run_id, selected_ids FROM executions WHERE plan_id IS NULL"
    ).fetchall()
    for execution in executions:
        selected_ids = set(json.loads(execution["selected_ids"]))
        matching_plan = next(
            (plan_id for plan_id, case_ids in plans.items() if case_ids == selected_ids),
            None,
        )
        if matching_plan is not None:
            con.execute(
                "UPDATE executions SET plan_id = ? WHERE run_id = ?",
                (matching_plan, execution["run_id"]),
            )

def list_cases() -> list[dict[str, Any]]:
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM test_cases ORDER BY test_id")]

def list_plans() -> list[dict[str, Any]]:
    with connect() as con:
        plans = [dict(r) for r in con.execute("SELECT * FROM test_plans ORDER BY plan_id")]
        for plan in plans:
            rows = con.execute(
                "SELECT test_id FROM plan_cases WHERE plan_id = ? ORDER BY test_id",
                (plan["plan_id"],),
            ).fetchall()
            plan["test_ids"] = [r["test_id"] for r in rows]
        return plans

def create_execution(
    status: str,
    selected_ids: list[str],
    passed: int,
    failed: int,
    duration_seconds: float,
    output: str,
    plan_id: str | None,
    sip_profile: str,
    api_profile: str,
) -> int:
    import json
    with connect() as con:
        cur = con.execute(
            """INSERT INTO executions
               (status, selected_ids, plan_id, sip_profile, api_profile, passed, failed,
                duration_seconds, output)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                status,
                json.dumps(selected_ids),
                plan_id,
                sip_profile,
                api_profile,
                passed,
                failed,
                duration_seconds,
                output[-12000:],
            ),
        )
        return int(cur.lastrowid)

def list_executions(limit: int = 20) -> list[dict[str, Any]]:
    import json
    with connect() as con:
        rows = [dict(r) for r in con.execute(
            """SELECT executions.*, test_plans.name AS plan_name
               FROM executions
               LEFT JOIN test_plans USING (plan_id)
               ORDER BY run_id DESC LIMIT ?""",
            (limit,),
        )]
    for row in rows:
        row["selected_ids"] = json.loads(row["selected_ids"])
    return rows

def get_execution(run_id: int) -> dict[str, Any] | None:
    import json
    with connect() as con:
        row = con.execute(
            """SELECT executions.*, test_plans.name AS plan_name
               FROM executions
               LEFT JOIN test_plans USING (plan_id)
               WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["selected_ids"] = json.loads(result["selected_ids"])
    return result
