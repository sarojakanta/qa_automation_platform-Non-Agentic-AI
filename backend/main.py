from pathlib import Path
import html
import os
import subprocess
import sys
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend import db, call_engine

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Only these approved test node IDs may be triggered by the UI.
TEST_REGISTRY = {
    "TC-API-001": "tests/test_api.py::test_health_endpoint",
    "TC-API-002": "tests/test_api.py::test_list_demo_users",
    "TC-API-003": "tests/test_api.py::test_successful_migration_simulation",
    "TC-API-004": "tests/test_api.py::test_unknown_user_negative_case",
    "TC-LOG-001": "tests/test_logs.py::test_simulated_error_is_logged",
    "TC-UI-001": "tests/test_ui.py::test_demo_ui_smoke",
    "TC-CALL-001": "tests/test_call_engine.py::test_simulated_call_lifecycle",
    "TC-SIP-001": "tests/test_call_engine.py::test_simulated_call_media_boundary",
    "TC-SIP-002": "tests/test_call_engine.py::test_rejects_invalid_endpoints",
    "TC-SIP-003": "tests/test_call_engine.py::test_rejects_invalid_call_state_transitions",
}
SIP_SIMULATOR_PROFILES = {
    "generic": "Generic call simulator",
    "broadworks": "BroadWorks-style simulator",
    "teams": "Microsoft Teams-style simulator",
    "asterisk": "Asterisk-style simulator",
    "cucm": "CUCM-style simulator",
}
API_SIMULATOR_PROFILES = {
    "fastapi": "FastAPI demo server",
    "rest": "Generic REST API simulator",
}

app = FastAPI(
    title="QA Automation Platform API",
    description="Demo test management and execution API. All telecom data is simulated.",
    version="1.0.0",
)
_demo_logs: list[dict[str, str]] = []

class ExecutionRequest(BaseModel):
    test_ids: list[str] = Field(min_length=1, max_length=20)
    plan_id: str | None = None
    sip_profile: str = "generic"
    api_profile: str = "fastapi"

@app.on_event("startup")
def startup() -> None:
    db.init_db()

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "qa-automation-demo"}

@app.get("/api/test-cases")
def get_test_cases() -> list[dict[str, Any]]:
    return db.list_cases()

@app.get("/api/test-plans")
def get_test_plans() -> list[dict[str, Any]]:
    return db.list_plans()

@app.get("/api/simulator-profiles")
def get_simulator_profiles() -> dict[str, dict[str, str]]:
    return {
        "sip": SIP_SIMULATOR_PROFILES,
        "api": API_SIMULATOR_PROFILES,
    }

@app.get("/api/executions")
def get_executions() -> list[dict[str, Any]]:
    return db.list_executions()

@app.get("/api/executions/{run_id}")
def get_execution(run_id: int) -> dict[str, Any]:
    result = db.get_execution(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return result

@app.post("/api/executions")
def run_execution(request: ExecutionRequest) -> dict[str, Any]:
    db.init_db()
    if request.plan_id is not None and request.plan_id not in {
        plan["plan_id"] for plan in db.list_plans()
    }:
        raise HTTPException(status_code=400, detail=f"Unknown test plan: {request.plan_id}")
    if request.sip_profile not in SIP_SIMULATOR_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown SIP simulator profile: {request.sip_profile}")
    if request.api_profile not in API_SIMULATOR_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unknown API simulator profile: {request.api_profile}")

    # Preserve order while removing duplicate IDs.
    selected = list(dict.fromkeys(request.test_ids))
    unknown = [test_id for test_id in selected if test_id not in TEST_REGISTRY]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown test IDs: {', '.join(unknown)}")

    node_ids = [TEST_REGISTRY[test_id] for test_id in selected]
    report_path = REPORTS_DIR / f"junit-{int(time.time() * 1000)}.xml"
    command = [
        sys.executable, "-m", "pytest", "-q",
        *node_ids,
        f"--junitxml={report_path}",
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
        )
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        duration = round(time.monotonic() - started, 3)
        # Parse the JUnit report when available; fall back to pytest exit status.
        passed, failed = _parse_junit(report_path)
        if passed == 0 and failed == 0 and completed.returncode != 0:
            failed = len(selected)
        status = "PASSED" if completed.returncode == 0 else "FAILED"
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - started, 3)
        output = f"Execution timed out after 120 seconds.\n{exc}"
        passed, failed, status = 0, len(selected), "TIMEOUT"
    except Exception as exc:
        duration = round(time.monotonic() - started, 3)
        output = f"Execution could not start: {type(exc).__name__}: {exc}"
        passed, failed, status = 0, len(selected), "ERROR"

    run_id = db.create_execution(
        status,
        selected,
        passed,
        failed,
        duration,
        output,
        request.plan_id,
        request.sip_profile,
        request.api_profile,
    )
    return {
        "run_id": run_id,
        "status": status,
        "selected_ids": selected,
        "plan_id": request.plan_id,
        "plan_name": next(
            (plan["name"] for plan in db.list_plans() if plan["plan_id"] == request.plan_id),
            None,
        ),
        "sip_profile": request.sip_profile,
        "api_profile": request.api_profile,
        "passed": passed,
        "failed": failed,
        "duration_seconds": duration,
        "output": output[-12000:],
    }

class SimulatedCallRequest(BaseModel):
    from_extension: str = Field(min_length=1, max_length=20)
    to_extension: str = Field(min_length=1, max_length=20)


@app.get("/api/call-lab/endpoints")
def get_call_endpoints() -> dict[str, Any]:
    return {"mode": "SIMULATED", "endpoints": call_engine.list_endpoints()}


@app.get("/api/call-lab/calls")
def get_call_list() -> dict[str, Any]:
    return {"mode": "SIMULATED", "calls": call_engine.list_calls()}


@app.post("/api/call-lab/calls", status_code=201)
def start_simulated_call(request: SimulatedCallRequest) -> dict[str, Any]:
    try:
        result = call_engine.create_call(request.from_extension, request.to_extension)
        _demo_logs.append({"level": "INFO", "message": f"Simulated call {result['call_id']} created"})
        return result
    except ValueError as exc:
        _demo_logs.append({"level": "ERROR", "message": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/call-lab/calls/{call_id}")
def get_simulated_call(call_id: str) -> dict[str, Any]:
    result = call_engine.get_call(call_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return result


@app.post("/api/call-lab/calls/{call_id}/answer")
def answer_simulated_call(call_id: str) -> dict[str, Any]:
    try:
        return call_engine.answer_call(call_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/call-lab/calls/{call_id}/hangup")
def hangup_simulated_call(call_id: str) -> dict[str, Any]:
    try:
        return call_engine.hangup_call(call_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/call-lab/calls/{call_id}/events")
def get_simulated_call_events(call_id: str) -> dict[str, Any]:
    events = call_engine.get_events(call_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return {"call_id": call_id, "events": events}


@app.get("/api/demo/users")
def demo_users() -> dict[str, Any]:
    return {
        "users": [
            {"user_id": "demo-1001", "display_name": "Alex Morgan", "platform": "BroadWorks"},
            {"user_id": "demo-1002", "display_name": "Jamie Lee", "platform": "Teams"},
            {"user_id": "demo-1003", "display_name": "Taylor Singh", "platform": "Mitel"},
        ]
    }

@app.post("/api/demo/migrations/{user_id}")
def demo_migration(user_id: str) -> dict[str, Any]:
    allowed = {"demo-1001", "demo-1002", "demo-1003"}
    if user_id not in allowed:
        _demo_logs.append({"level": "ERROR", "message": f"Migration requested for unknown user: {user_id}"})
        raise HTTPException(status_code=404, detail="Demo user not found")
    result = {
        "operation_id": f"SIM-{user_id.upper()}",
        "user_id": user_id,
        "source": "simulated-source",
        "destination": "simulated-destination",
        "status": "COMPLETED",
        "note": "Simulation only; no real system was changed.",
    }
    _demo_logs.append({"level": "INFO", "message": f"Simulated migration completed for {user_id}"})
    return result

@app.post("/api/demo/log-error")
def simulate_error_log() -> dict[str, str]:
    _demo_logs.append({"level": "ERROR", "message": "SIMULATED_ERROR: sample validation failure"})
    return {"status": "recorded", "message": "A simulated error was added to the demo log buffer."}

@app.get("/api/demo/logs")
def get_demo_logs() -> dict[str, Any]:
    return {"logs": _demo_logs[-100:]}

@app.get("/demo-ui", response_class=HTMLResponse)
def demo_ui() -> str:
    # Static dummy page used by the Playwright test.
    return """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>QA Demo Application</title>
<style>body{font-family:Arial,sans-serif;margin:3rem;background:#f5f7fb;color:#172033}
main{max-width:720px;margin:auto;background:white;padding:2rem;border-radius:12px}
.status{padding:.7rem;background:#e4f8e9;color:#176534;border-radius:6px}
button{padding:.7rem 1rem;border:0;border-radius:6px;background:#2458c6;color:white;cursor:pointer}</style>
</head>
<body><main>
<h1>QA Demo Application</h1>
<p id="environment">Environment: SIMULATED</p>
<p class="status" id="service-status">Service status: READY</p>
<button id="check-button" onclick="document.getElementById('service-status').textContent='Service status: CHECKED'">Check service</button>
</main></body></html>"""

def _parse_junit(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        passed = failed = 0
        for suite in suites:
            tests = int(suite.attrib.get("tests", 0))
            failures = int(suite.attrib.get("failures", 0))
            errors = int(suite.attrib.get("errors", 0))
            skipped = int(suite.attrib.get("skipped", 0))
            passed += max(0, tests - failures - errors - skipped)
            failed += failures + errors
        return passed, failed
    except Exception:
        return 0, 0
