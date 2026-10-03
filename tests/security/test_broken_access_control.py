import os

import pytest
import requests


BASE_URL = os.getenv("VULNBANK_URL", "http://127.0.0.1:5000")

TEST_USERNAME = "security_test"
TEST_PASSWORD = os.getenv("SECURITY_TEST_PASSWORD")

TARGET_ACCOUNT = "ADMIN001"


def test_user_cannot_access_another_users_balance():
    """
    V2 - Broken Access Control

    A normal authenticated user must not be able to access
    another user's account balance by changing the account_number
    in the URL.
    """

    assert TEST_PASSWORD, (
        "SECURITY_TEST_PASSWORD environment variable is required"
    )

    # ---------------------------------------------------------
    # 1. Login as the normal security-test user
    # ---------------------------------------------------------
    try:
        login_response = requests.post(
            f"{BASE_URL}/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        pytest.fail(
            f"Could not connect to VulnBank at {BASE_URL}: {exc}"
        )

    assert login_response.status_code == 200, (
        f"Security test user could not log in. "
        f"Status: {login_response.status_code}, "
        f"Response: {login_response.text}"
    )

    # ---------------------------------------------------------
    # 2. Extract JWT from the HttpOnly authentication cookie
    # ---------------------------------------------------------
    token = login_response.cookies.get("token")

    assert token, (
        "Login response does not contain the authentication "
        f"cookie 'token'. Cookies received: {login_response.cookies}"
    )

    # ---------------------------------------------------------
    # 3. Attempt to access another user's account
    # ---------------------------------------------------------
    try:
        response = requests.get(
            f"{BASE_URL}/check_balance/{TARGET_ACCOUNT}",
            headers={
                "Authorization": f"Bearer {token}",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        pytest.fail(
            f"Could not access the balance endpoint: {exc}"
        )

    # ---------------------------------------------------------
    # 4. Verify authorization is enforced
    # ---------------------------------------------------------
    assert response.status_code == 403, (
        "BROKEN ACCESS CONTROL: a normal user was able to "
        f"access another user's account {TARGET_ACCOUNT}. "
        f"Status: {response.status_code}, "
        f"Response: {response.text}"
    )

    data = response.json()

    assert data.get("status") == "error", (
        f"Unexpected response status: {data}"
    )

    assert data.get("message") == "Forbidden", (
        f"Expected 'Forbidden' but received: {data}"
    )
