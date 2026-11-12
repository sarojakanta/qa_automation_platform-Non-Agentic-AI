import requests

BASE_URL = "http://127.0.0.1:8000"

def test_health_endpoint():
    response = requests.get(f"{BASE_URL}/health", timeout=5)
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_list_demo_users():
    response = requests.get(f"{BASE_URL}/api/demo/users", timeout=5)
    assert response.status_code == 200
    users = response.json()["users"]
    assert len(users) >= 3
    assert any(user["user_id"] == "demo-1001" for user in users)

def test_simulator_profiles_are_available():
    response = requests.get(f"{BASE_URL}/api/simulator-profiles", timeout=5)
    assert response.status_code == 200
    profiles = response.json()
    assert set(profiles["sip"]) == {"generic", "broadworks", "teams", "asterisk", "cucm"}
    assert set(profiles["api"]) == {"fastapi", "rest"}

def test_successful_migration_simulation():
    response = requests.post(f"{BASE_URL}/api/demo/migrations/demo-1001", timeout=5)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["note"].startswith("Simulation only")

def test_unknown_user_negative_case():
    response = requests.post(f"{BASE_URL}/api/demo/migrations/unknown-user", timeout=5)
    assert response.status_code == 404
    assert response.json()["detail"] == "Demo user not found"
