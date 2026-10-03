import os

import requests


BASE_URL = os.getenv("VULNBANK_URL", "http://127.0.0.1:5000")


def test_env_files_are_not_exposed():
    for filename in [".env", ".env.bak"]:
        response = requests.get(
            f"{BASE_URL}/{filename}",
            timeout=10,
        )

        assert response.status_code == 404, (
            f"SENSITIVE FILE EXPOSED: /{filename} returned "
            f"HTTP {response.status_code}"
        )
