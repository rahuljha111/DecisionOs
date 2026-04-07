import json
import os
import sys

import requests


BASE_URL = os.getenv("DECISIONOS_BASE_URL", "https://decisionos-837202638935.asia-south1.run.app")
USER_ID = os.getenv("DECISIONOS_USER_ID", "testuser")
HOURS = int(os.getenv("DECISIONOS_HOURS", "168"))
TIMEOUT = 30
REQUIRE_AUTH = os.getenv("DECISIONOS_REQUIRE_AUTH", "0") == "1"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    response = requests.get(url, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        fail(f"{path} returned {response.status_code}: {response.text}")
    try:
        return response.json()
    except Exception as exc:
        fail(f"{path} returned non-JSON response: {exc}")


def main() -> None:
    print(f"Smoke test target: {BASE_URL}")
    print(f"Smoke test user: {USER_ID}")

    health = get("/api/health")
    print("Health OK")

    status = get("/api/calendar/status", {"user_id": USER_ID})
    print("Calendar status:")
    print(json.dumps(status, indent=2))

    if not status.get("google_calendar_available"):
        fail("google_calendar_available is false")
    if REQUIRE_AUTH and not status.get("authenticated"):
        fail("authenticated is false for smoke test user while DECISIONOS_REQUIRE_AUTH=1")

    events = get("/api/calendar/events", {"user_id": USER_ID, "hours": HOURS})
    print("Calendar events payload:")
    print(json.dumps(events, indent=2))

    if "events" not in events or "count" not in events or "source" not in events:
        fail("calendar/events response missing expected keys")
    if events.get("source") not in {"google_calendar", "database"}:
        fail(f"unexpected source value: {events.get('source')}")
    if not isinstance(events.get("events"), list):
        fail("events is not a list")
    if events.get("count") != len(events.get("events", [])):
        fail("count does not match events list length")

    print("PASS: production calendar smoke test completed")


if __name__ == "__main__":
    main()