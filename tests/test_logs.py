import requests

BASE_URL = "http://127.0.0.1:8000"

def test_simulated_error_is_logged():
    before = requests.get(f"{BASE_URL}/api/demo/logs", timeout=5).json()["logs"]
    trigger = requests.post(f"{BASE_URL}/api/demo/log-error", json={}, timeout=5)
    assert trigger.status_code == 200
    after = requests.get(f"{BASE_URL}/api/demo/logs", timeout=5).json()["logs"]
    assert len(after) == len(before) + 1
    assert after[-1]["level"] == "ERROR"
    assert "SIMULATED_ERROR" in after[-1]["message"]
