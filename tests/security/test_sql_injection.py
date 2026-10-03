import os

import requests


BASE_URL = os.getenv("VULNBANK_URL", "http://127.0.0.1:5000")

SQLI_USERNAME = "' OR 1=1 --"
SQLI_PASSWORD = "anything"


def test_sql_injection_login_is_blocked():
    response = requests.post(
        f"{BASE_URL}/login",
        json={
            "username": SQLI_USERNAME,
            "password": SQLI_PASSWORD,
        },
        timeout=10,
    )

    # The SQL injection must NOT authenticate successfully.
    assert response.status_code in (400, 401, 403)

    data = response.json()

    # We should not receive a successful authentication response/token.
    assert "token" not in data
    assert data.get("status") != "success"
