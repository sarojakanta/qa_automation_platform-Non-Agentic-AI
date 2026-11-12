# QA Automation & Test Execution Platform (Demo)

A runnable, simulated QA platform built with **FastAPI + Pytest + Playwright + Streamlit + GitHub Actions**.

It uses dummy telecom-style data only. It does **not** connect to Microsoft Teams, BroadWorks, CUCM, Mitel, SBCs, or recording servers.

## Features

- Streamlit dashboard to browse test cases and choose a test plan or individual cases.
- FastAPI backend for test catalog, plans, execution requests, run history, and reports.
- SQLite database created locally and seeded with demo test cases/plans.
- Pytest tests for API behavior, simulated logs/error handling, and a demo UI.
- Playwright browser test against a dummy web page served by FastAPI.
- Execution is restricted to an allowlisted test registry; the browser cannot submit arbitrary shell commands.
- GitHub Actions workflow runs the test suite and uploads JUnit XML as an artifact.

## Requirements

- Python 3.11 or 3.12 recommended
- Git (optional)
- Playwright Chromium browser for the browser test

## Quick start — Windows PowerShell

```powershell
cd qa_automation_platform
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
```

Terminal 1 — start the API:

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — start the portal:

```powershell
streamlit run frontend/dashboard.py
```

Open:
- Streamlit portal: http://localhost:8501
- FastAPI docs: http://localhost:8000/docs
- Dummy test page: http://localhost:8000/demo-ui
- API health: http://localhost:8000/health

In the portal, select a plan or individual test cases, then click **Run selected tests**. Refresh run history to see the outcome.

## Dashboard configuration

The dashboard loads configuration from a file named `.env` in the project root — the same folder as `requirements.txt` and `README.md`. If it does not exist (for example, after a fresh clone), create it with:

```dotenv
QA_API_BASE_URL=http://127.0.0.1:8000
```

`QA_API_BASE_URL` is the base URL of the FastAPI backend that the Streamlit dashboard calls. Set it to another reachable API only if that service implements the endpoints this dashboard uses. This setting does **not** configure a SIP server or a vendor simulator.

The dashboard uses `http://127.0.0.1:8000` if this setting is missing. A `QA_API_BASE_URL` already set in the process environment takes precedence over the `.env` value. Restart Streamlit after changing the configuration.

The `.env` file is excluded from Git by `.gitignore`, so it is not distributed with source changes. Do not put credentials or other secrets in a committed file.

## Quick start — Linux/macOS

```bash
cd qa_automation_platform
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
streamlit run frontend/dashboard.py
```

## Demo test catalog

| ID | Test | What it checks |
|---|---|---|
| TC-API-001 | Health endpoint | API returns healthy status |
| TC-API-002 | List demo users | Dummy users are returned |
| TC-API-003 | Successful migration simulation | Valid demo user can be "migrated" in memory |
| TC-API-004 | Unknown user negative test | Unknown user returns a controlled 404 |
| TC-LOG-001 | Error log capture | A simulated error is recorded in the demo log buffer |
| TC-UI-001 | Demo UI smoke test | Playwright opens the dummy page and validates its title and status |
| TC-SIP-001 | Simulated call media boundary | The simulator reports simulated media and no RTP/audio |
| TC-SIP-002 | Simulated SIP endpoint validation | The simulator rejects unknown or identical extensions |
| TC-SIP-003 | Simulated SIP call-state validation | The simulator rejects invalid answer and hang-up transitions |

Plans:
- **Smoke Test Plan**: health, users, demo UI
- **API Regression Plan**: health, users, successful migration, negative case, error log
- **SIP Test Plan (Simulated)**: call lifecycle, media boundary, endpoint validation, and call-state validation
- **Full Demo Regression**: all sample cases

Execution history is labeled and filterable by test plan; each run records the selected simulator profiles and whether a log is available. Existing runs are matched to a plan when their selected test IDs exactly match that plan.

The SIP and API simulator profile selectors are simulation labels only: all SIP profile choices use the same in-memory call simulator, and all API profile choices use the same FastAPI service. They do not connect to BroadWorks, Teams, Asterisk, CUCM, or a separate REST server. The SIP-named cases do not send SIP messages or test interoperability with a real PBX or phone. The demo UI smoke test requires the Playwright Chromium browser; if it is missing, install it in the active project environment with `python -m playwright install chromium`.

Execution output is available in the dashboard and can be downloaded as a `.log` file from the latest execution or run history. In run history, the output selector identifies each run by plan, run ID, timestamp, and status; the download button and filename also identify the plan and run ID.

## How execution works

1. Streamlit sends selected test IDs to FastAPI.
2. FastAPI validates each ID against the server-side registry.
3. FastAPI runs the mapped Pytest node IDs in a subprocess.
4. Pytest writes JUnit XML; FastAPI stores the execution summary in SQLite.
5. Streamlit displays the status, duration, selected tests, and output tail.

The demo execution endpoint is synchronous and has a 120-second timeout to keep the example simple. For a production-scale platform, move execution into a background worker or dispatch it to a self-hosted GitHub Actions runner.

## Important notes

- The SQLite file (`qa_demo.db`) is generated at first startup and can be deleted to reset the demo database.
- The migration and error-log scenarios are simulated; no real telecom configuration changes occur.
- The Playwright test requires the FastAPI server to be running at `http://127.0.0.1:8000`. Start the backend before running tests from the portal.
- GitHub-hosted Actions runners can run the dummy demo. Real telecom environments often require a secured self-hosted runner with network access.
- Do not use `--reload` for production. Add authentication, authorization, secrets management, audit logging, and a background worker before exposing this platform to a shared network.


## Simulated Python call server (new)

The project now includes an in-memory call lifecycle simulator and a Streamlit **Simulated call lab** tab.

- `GET /api/call-lab/endpoints` — list demo extensions (`1001`, `1002`, `1003`)
- `POST /api/call-lab/calls` — create a simulated call in `RINGING` state
- `POST /api/call-lab/calls/{call_id}/answer` — transition `RINGING` to `ESTABLISHED`
- `POST /api/call-lab/calls/{call_id}/hangup` — transition to `ENDED`
- `GET /api/call-lab/calls/{call_id}` — inspect call state
- `GET /api/call-lab/calls/{call_id}/events` — inspect the call event timeline

Example create-call request:

```json
{
  "from_extension": "1001",
  "to_extension": "1002"
}
```

This is intentionally **not a SIP implementation**: it sends no SIP messages, generates no RTP/audio, and cannot call real clients. It is a first step to develop and test the REST API, call orchestration, lifecycle validation, and dashboard. Later, the simulator can be replaced behind an adapter with Asterisk ARI, FreeSWITCH ESL, or a PBX-specific control interface.
