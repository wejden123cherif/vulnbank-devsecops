import os
from pathlib import Path

import requests


BASE_URL = os.getenv("VULNBANK_URL", "http://127.0.0.1:5000")

TEST_USERNAME = "security_test"
TEST_PASSWORD = os.getenv("SECURITY_TEST_PASSWORD", "test123")

XSS_PAYLOAD = "<img src=x onerror=\"alert('XSS_TEST')\">"


def get_auth_token():
    response = requests.post(
        f"{BASE_URL}/login",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD,
        },
        timeout=10,
    )

    assert response.status_code == 200, (
        f"Test user login failed: {response.status_code} {response.text}"
    )

    token = response.cookies.get("token")

    assert token, "Login did not return an authentication token"

    return token


def test_stored_xss_payload_is_not_executable():
    """
    Regression test for V3.

    The application may store the supplied bio, but the frontend
    must render it as text rather than HTML.
    """

    token = get_auth_token()

    response = requests.post(
        f"{BASE_URL}/update_bio",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "bio": XSS_PAYLOAD,
        },
        timeout=10,
    )

    assert response.status_code == 200, (
        f"Bio update failed: {response.status_code} {response.text}"
    )

    data = response.json()

    assert data.get("status") == "success", (
        f"Bio update was not successful: {data}"
    )

    # Verify the frontend uses a safe DOM sink.
    dashboard_js = Path("static/dashboard.js").read_text()

    assert "bioDisplay.textContent = bio" in dashboard_js, (
        "XSS protection missing: bio must be rendered with textContent."
    )

    assert "bioDisplay.innerHTML = bio" not in dashboard_js, (
        "STORED XSS: bio is rendered using innerHTML."
    )
