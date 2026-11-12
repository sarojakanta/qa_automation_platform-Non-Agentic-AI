import os
import re
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
API_BASE = os.getenv("QA_API_BASE_URL", "http://127.0.0.1:8000")


def log_filename(run: dict) -> str:
    plan_name = run.get("plan_name") or "manual-selection"
    plan_slug = re.sub(r"[^a-z0-9]+", "-", plan_name.lower()).strip("-")
    return f"qa-{plan_slug}-run-{run['run_id']}.log"


st.set_page_config(page_title="QA Automation Platform", page_icon="🧪", layout="wide")
st.title("🧪 QA Automation & Test Execution Platform")
st.caption("Demo environment • FastAPI + Pytest + Playwright • Dummy telecom-style data only")

def api_get(path):
    try:
        response = requests.get(f"{API_BASE}{path}", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        st.error(f"Cannot reach FastAPI at {API_BASE}. Start the backend first. Details: {exc}")
        return None

def api_post(path, payload):
    response = requests.post(f"{API_BASE}{path}", json=payload, timeout=135)
    response.raise_for_status()
    return response.json()

with st.sidebar:
    st.subheader("Connection")
    st.code(API_BASE)
    if st.button("Refresh data", use_container_width=True):
        st.rerun()
    st.markdown("---")
    st.markdown("**Demo links**")
    st.markdown(f"[FastAPI Swagger docs]({API_BASE}/docs)")
    st.markdown(f"[Dummy Playwright page]({API_BASE}/demo-ui)")

cases = api_get("/api/test-cases")
plans = api_get("/api/test-plans")
simulator_profiles = api_get("/api/simulator-profiles")
if cases is None or plans is None or simulator_profiles is None:
    st.stop()

tab_run, tab_history, tab_demo, tab_calls = st.tabs(["▶ Test execution", "📜 Run history", "🧰 Demo data & logs", "☎ Simulated call lab"])

with tab_run:
    st.subheader("Choose a test plan or select individual cases")
    plan_options = {"No plan — choose cases manually": None}
    plan_options.update({f"{p['name']} ({p['plan_id']})": p for p in plans})

    def reset_test_case_selection():
        selected_plan = plan_options[st.session_state["selected_plan_label"]]
        st.session_state["test_case_selection"] = (
            selected_plan["test_ids"] if selected_plan else []
        )

    selected_plan_label = st.selectbox(
        "Test plan",
        list(plan_options.keys()),
        key="selected_plan_label",
        on_change=reset_test_case_selection,
    )
    selected_plan = plan_options[selected_plan_label]
    sip_profile_labels = simulator_profiles["sip"]
    api_profile_labels = simulator_profiles["api"]
    selected_sip_profile = st.selectbox(
        "SIP simulator profile",
        list(sip_profile_labels),
        format_func=lambda profile: sip_profile_labels[profile],
        help="Simulation profile only; all choices use the same in-memory call simulator.",
    )
    selected_api_profile = st.selectbox(
        "API simulator profile",
        list(api_profile_labels),
        format_func=lambda profile: api_profile_labels[profile],
        help="Simulation profile only; all choices use the same FastAPI demo service.",
    )

    cases_by_id = {case["test_id"]: case for case in cases}
    if selected_plan:
        plan_case_ids = [
            test_id for test_id in selected_plan["test_ids"] if test_id in cases_by_id
        ]
    else:
        plan_case_ids = list(cases_by_id)
    visible_cases = [cases_by_id[test_id] for test_id in plan_case_ids]
    if "test_case_selection" not in st.session_state:
        st.session_state["test_case_selection"] = (
            plan_case_ids if selected_plan else []
        )

    chosen_ids = st.multiselect(
        "Test cases",
        options=plan_case_ids,
        format_func=lambda test_id: f"{test_id} — {cases_by_id[test_id]['name']}",
        key="test_case_selection",
    )

    with st.expander("Test catalog", expanded=True):
        st.dataframe(
            [{"Test ID": c["test_id"], "Name": c["name"], "Category": c["category"],
              "Description": c["description"]} for c in visible_cases],
            use_container_width=True,
            hide_index=True,
        )

    run_clicked = st.button("Run selected tests", type="primary", disabled=not chosen_ids)
    if run_clicked:
        try:
            with st.spinner(f"Running {len(chosen_ids)} test(s)…"):
                result = api_post("/api/executions", {
                    "test_ids": chosen_ids,
                    "plan_id": selected_plan["plan_id"] if selected_plan else None,
                    "sip_profile": selected_sip_profile,
                    "api_profile": selected_api_profile,
                })
            st.session_state["last_run"] = result
        except requests.RequestException as exc:
            st.error(f"Execution request failed: {exc}")

    result = st.session_state.get("last_run")
    if result:
        st.markdown("### Latest execution")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Run ID", result["run_id"])
        c2.metric("Status", result["status"])
        c3.metric("Passed", result["passed"])
        c4.metric("Failed", result["failed"])
        st.caption(
            f"Plan: {result.get('plan_name') or 'Manual selection'} | "
            f"SIP profile: {sip_profile_labels.get(result.get('sip_profile'), 'Unknown')} | "
            f"API profile: {api_profile_labels.get(result.get('api_profile'), 'Unknown')}"
        )
        st.caption(f"Duration: {result['duration_seconds']} seconds | Cases: {', '.join(result['selected_ids'])}")
        if result["status"] == "PASSED":
            st.success("All selected tests passed.")
        else:
            st.error("One or more tests failed or execution did not complete successfully.")
        with st.expander("Execution output / errors", expanded=result["status"] != "PASSED"):
            output = result.get("output") or "(No output captured)"
            st.code(output, language="text")
            if result.get("output"):
                st.download_button(
                    "Download log file",
                    data=result["output"],
                    file_name=f"qa-run-{result['run_id']}.log",
                    mime="text/plain",
                    key=f"download-latest-run-{result['run_id']}",
                )
            else:
                st.info("No execution log was captured for this run.")

with tab_history:
    st.subheader("Recent executions")
    if st.button("Reload execution history"):
        st.rerun()
    history = api_get("/api/executions")
    if history is not None:
        plan_filters = {
            "All plans": None,
            **{plan["name"]: plan["plan_id"] for plan in plans},
            "Manual / unassigned": "__manual__",
        }
        selected_history_filter = st.selectbox("Filter run history by plan", list(plan_filters))
        selected_plan_filter = plan_filters[selected_history_filter]
        if selected_plan_filter == "__manual__":
            visible_history = [run for run in history if run.get("plan_id") is None]
        elif selected_plan_filter is None:
            visible_history = history
        else:
            visible_history = [
                run for run in history if run.get("plan_id") == selected_plan_filter
            ]
        if visible_history:
            st.dataframe(
                [{"Plan": r.get("plan_name") or "Manual / unassigned",
                  "Run ID": r["run_id"], "Created": r["created_at"], "Status": r["status"],
                  "Passed": r["passed"], "Failed": r["failed"],
                  "Duration (s)": r["duration_seconds"],
                  "SIP profile": sip_profile_labels.get(r.get("sip_profile"), r.get("sip_profile", "Unknown")),
                  "API profile": api_profile_labels.get(r.get("api_profile"), r.get("api_profile", "Unknown")),
                  "Log": "Available" if r.get("output") else "Not captured",
                  "Test IDs": ", ".join(r["selected_ids"])}
                 for r in visible_history],
                use_container_width=True,
                hide_index=True,
            )
            runs_by_id = {run["run_id"]: run for run in visible_history}
            run_ids = list(runs_by_id)
            selected_run_id = st.selectbox(
                "View execution output",
                run_ids,
                format_func=lambda run_id: (
                    f"{runs_by_id[run_id].get('plan_name') or 'Manual selection'} — "
                    f"Run #{run_id} — {runs_by_id[run_id]['created_at']} "
                    f"({runs_by_id[run_id]['status']})"
                ),
            )
            selected_run = next(r for r in visible_history if r["run_id"] == selected_run_id)
            with st.expander("Selected run output", expanded=True):
                output = selected_run.get("output") or "(No output captured)"
                st.code(output, language="text")
                if selected_run.get("output"):
                    run_plan = selected_run.get("plan_name") or "Manual selection"
                    st.caption(
                        f"Download belongs to **{run_plan}**, "
                        f"run **#{selected_run['run_id']}**."
                    )
                    st.download_button(
                        f"Download {run_plan} log (Run #{selected_run['run_id']})",
                        data=selected_run["output"],
                        file_name=log_filename(selected_run),
                        mime="text/plain",
                        key=f"download-history-run-{selected_run['run_id']}",
                    )
                else:
                    st.info("No execution log was captured for this run.")
        else:
            st.info("No executions match this plan. Run a test plan to add history.")

with tab_demo:
    st.subheader("Simulated service data")
    users_payload = api_get("/api/demo/users")
    if users_payload:
        st.markdown("**Dummy users**")
        st.dataframe(users_payload["users"], use_container_width=True, hide_index=True)
    if st.button("Generate a simulated error log"):
        try:
            result = api_post("/api/demo/log-error", {})
            st.info(result["message"])
        except requests.RequestException as exc:
            st.error(str(exc))
    logs_payload = api_get("/api/demo/logs")
    if logs_payload:
        st.markdown("**Recent demo logs**")
        if logs_payload["logs"]:
            st.dataframe(logs_payload["logs"], use_container_width=True, hide_index=True)
        else:
            st.info("No demo log entries yet. Run the negative test or generate a simulated error.")


with tab_calls:
    st.subheader("Python call-server simulator")
    st.warning(
        "Simulation only: this changes application call states but does not send SIP packets, "
        "create RTP/audio, or connect to a real phone/PBX."
    )
    endpoint_payload = api_get("/api/call-lab/endpoints")
    if endpoint_payload:
        st.dataframe(endpoint_payload["endpoints"], use_container_width=True, hide_index=True)

    st.markdown("#### Create an outgoing call")
    left, right = st.columns(2)
    with left:
        source_ext = st.selectbox("Calling extension", ["1001", "1002", "1003"], key="call_source")
    with right:
        destination_options = [ext for ext in ["1001", "1002", "1003"] if ext != source_ext]
        destination_ext = st.selectbox("Called extension", destination_options, key="call_destination")

    if st.button("Start call", type="primary"):
        try:
            new_call = api_post("/api/call-lab/calls", {
                "from_extension": source_ext,
                "to_extension": destination_ext,
            })
            st.session_state["active_simulated_call_id"] = new_call["call_id"]
            st.success(f"Call {new_call['call_id']} created. State: {new_call['state']}")
        except requests.RequestException as exc:
            st.error(f"Could not start simulated call: {exc}")

    call_list_payload = api_get("/api/call-lab/calls")
    call_rows = call_list_payload.get("calls", []) if call_list_payload else []
    if call_rows:
        st.markdown("#### Calls")
        st.dataframe(
            [{"Call ID": c["call_id"], "From": c["from_extension"], "To": c["to_extension"],
              "State": c["state"], "Media": c["media"]["mode"]} for c in call_rows],
            use_container_width=True, hide_index=True
        )
        call_ids = [c["call_id"] for c in call_rows]
        default_call = st.session_state.get("active_simulated_call_id")
        default_index = call_ids.index(default_call) if default_call in call_ids else 0
        chosen_call_id = st.selectbox("Select call", call_ids, index=default_index)
        detail = api_get(f"/api/call-lab/calls/{chosen_call_id}")
        if detail:
            st.metric("Current call state", detail["state"])
            action1, action2, action3 = st.columns(3)
            with action1:
                if st.button("Answer call", disabled=detail["state"] != "RINGING"):
                    try:
                        api_post(f"/api/call-lab/calls/{chosen_call_id}/answer", {})
                        st.rerun()
                    except requests.RequestException as exc:
                        st.error(str(exc))
            with action2:
                if st.button("Hang up", disabled=detail["state"] == "ENDED"):
                    try:
                        api_post(f"/api/call-lab/calls/{chosen_call_id}/hangup", {})
                        st.rerun()
                    except requests.RequestException as exc:
                        st.error(str(exc))
            with action3:
                if st.button("Refresh call state"):
                    st.rerun()
            events_payload = api_get(f"/api/call-lab/calls/{chosen_call_id}/events")
            if events_payload:
                st.markdown("#### Call event timeline")
                st.dataframe(events_payload["events"], use_container_width=True, hide_index=True)
