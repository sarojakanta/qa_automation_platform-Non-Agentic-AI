from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"

def test_demo_ui_smoke():
    # The FastAPI server must be running before this test is executed.
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(f"{BASE_URL}/demo-ui", wait_until="domcontentloaded", timeout=15000)
            assert page.title() == "QA Demo Application"
            assert page.get_by_role("heading", name="QA Demo Application").is_visible()
            assert page.locator("#environment").inner_text() == "Environment: SIMULATED"
            assert page.locator("#service-status").inner_text() == "Service status: READY"
            page.get_by_role("button", name="Check service").click()
            assert page.locator("#service-status").inner_text() == "Service status: CHECKED"
        finally:
            browser.close()
