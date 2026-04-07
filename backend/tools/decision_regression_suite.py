"""DecisionOS production regression suite.

Runs scenario-based checks against /api/decide SSE output and validates:
- decision payload is returned
- no forbidden generic phrasing
- concrete decision text includes expected keywords
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import List

import requests

API_URL = "http://127.0.0.1:8001/api/decide"
USER_ID = "regression_user"
FORBIDDEN = [
    "lower-value task",
    "lower-value conflict",
    "adjust schedule",
    "optimize time",
    "you may",
    "might be better",
    "perhaps",
    "balance both",
]
ACTIONS = ["attend", "skip", "leave", "cancel", "reschedule", "start", "stop"]


@dataclass
class Scenario:
    name: str
    message: str
    expected_keywords: List[str]


SCENARIOS = [
    Scenario("S1 exam vs gym", "Calendar: exam at 10 AM, gym at 10 AM. Todos: none.", ["exam", "gym"]),
    Scenario("S2 meeting before exam", "Calendar: meeting at 4 PM, exam at 5 PM. Todos: revise syllabus not started.", ["exam", "meeting", "revise"]),
    Scenario("S3 assignment vs youtube", "Calendar: no events. Todos: assignment due tonight, watch youtube.", ["assignment", "youtube"]),
    Scenario("S4 deadline vs back-to-back meetings", "Calendar: 3 meetings back-to-back. Todos: project deadline tomorrow not started.", ["project", "meeting", "deadline"]),
    Scenario("S5 interview prep vs gym", "Calendar: gym at 6 PM. Todos: prepare for interview tomorrow.", ["interview", "gym"]),
    Scenario("S6 exam tomorrow vs hangout", "Calendar: exam tomorrow morning. Todos: hangout with friends tonight.", ["exam", "hangout"]),
    Scenario("S7 coding due today", "Calendar: meeting at 2 PM. Todos: low priority reading, important coding task due today.", ["coding", "meeting"]),
    Scenario("S8 free day nothing urgent", "Calendar: free whole day. Todos: nothing urgent.", ["start", "task"]),
    Scenario("S9 overlapping meetings", "Calendar: two overlapping meetings. Todos: none.", ["meeting", "cancel"]),
    Scenario("S10 exam discipline", "Calendar: exam at 9 AM. Todos: sleep late at night, scroll social media.", ["exam", "social", "sleep"]),
    Scenario("S11 hard deadline", "Calendar: deadline today 11 PM. Todos: half completed project, gym.", ["deadline", "project", "gym"]),
    Scenario("S12 urgent bug", "Calendar: meeting at 3 PM. Todos: urgent bug fix affecting users.", ["bug", "meeting"]),
    Scenario("S13 high impact task", "Calendar: no events. Todos: 5 small tasks, 1 high-impact task.", ["high-impact", "task"]),
    Scenario("S14 exam in 2h", "Calendar: exam in 2 hours. Todos: watch series, light revision.", ["exam", "revision", "series"]),
    Scenario("S15 assignment due tomorrow", "Calendar: gym plus meeting plus practice session. Todos: assignment due tomorrow not started.", ["assignment", "meeting", "gym", "practice"]),
    Scenario("S16 interview now", "Calendar: interview in 1 hour, team sync now. Todos: finalize portfolio.", ["interview", "portfolio"]),
    Scenario("S17 outage", "Calendar: demo at 5 PM. Todos: production outage affecting payments.", ["outage", "demo"]),
    Scenario("S18 no conflict high work", "Calendar: gym at 9 PM. Todos: publish critical release notes by tonight.", ["release", "gym"]),
    Scenario("S19 class overlap", "Calendar: class at 11 AM, meeting at 11 AM. Todos: none.", ["class", "meeting"]),
    Scenario("S20 deadline and distractions", "Calendar: no events. Todos: submission deadline in 5 hours, gaming session.", ["deadline", "submission", "gaming"]),
]


def parse_sse_decision(resp: requests.Response):
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data: "):
            continue
        try:
            payload = json.loads(raw[6:])
        except json.JSONDecodeError:
            continue
        if payload.get("error"):
            return None, payload.get("error")
        if payload.get("decision"):
            return payload["decision"], None
    return None, "No decision event in stream"


def check_decision(decision: dict, scenario: Scenario) -> List[str]:
    issues: List[str] = []
    decision_text = str(decision.get("decision_text", "")).lower()
    reasoning = str(decision.get("reasoning", "")).lower()
    consequence = str(decision.get("consequence", "")).lower()

    if not decision_text:
        issues.append("missing decision_text")

    if not any(decision_text.startswith(verb) for verb in ACTIONS):
        issues.append("decision_text does not start with a real-world action verb")

    joined = " | ".join([decision_text, reasoning, consequence])
    for phrase in FORBIDDEN:
        if phrase in joined:
            issues.append(f"forbidden phrase present: {phrase}")

    keyword_hits = [k for k in scenario.expected_keywords if k.lower() in joined]
    if len(keyword_hits) == 0:
        issues.append("no expected scenario keyword found in output")

    if "fixed_events" in joined or "flexible_events" in joined:
        issues.append("internal variable leaked in output")

    return issues


def main() -> int:
    print(f"Running {len(SCENARIOS)} regression scenarios against {API_URL}\n")

    failures = 0
    for idx, scenario in enumerate(SCENARIOS, start=1):
        payload = {"user_id": USER_ID, "message": scenario.message}
        try:
            resp = requests.post(API_URL, json=payload, stream=True, timeout=60)
        except Exception as exc:  # noqa: BLE001
            print(f"[{idx:02d}] {scenario.name}: FAIL (request error: {exc})")
            failures += 1
            continue

        if resp.status_code != 200:
            print(f"[{idx:02d}] {scenario.name}: FAIL (status {resp.status_code})")
            failures += 1
            continue

        decision, error = parse_sse_decision(resp)
        if error:
            print(f"[{idx:02d}] {scenario.name}: FAIL ({error})")
            failures += 1
            continue

        issues = check_decision(decision, scenario)
        if issues:
            print(f"[{idx:02d}] {scenario.name}: FAIL")
            for issue in issues:
                print(f"      - {issue}")
            print(f"      decision_text: {decision.get('decision_text')}")
            failures += 1
        else:
            print(f"[{idx:02d}] {scenario.name}: PASS | {decision.get('decision_text')}")

    print("\nSummary:")
    print(f"  Total: {len(SCENARIOS)}")
    print(f"  Failed: {failures}")
    print(f"  Passed: {len(SCENARIOS) - failures}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
