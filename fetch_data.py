#!/usr/bin/env python3
"""Run this locally whenever you want to refresh course data from DAAD."""

import json
import requests
from pathlib import Path

DAAD_BASE = "https://www2.daad.de"
DAAD_API = (
    f"{DAAD_BASE}/deutschland/studienangebote"
    "/international-programmes/api/solr/en/search.json"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, */*",
    "Referer": (
        f"{DAAD_BASE}/deutschland/studienangebote"
        "/international-programmes/en/result/"
    ),
}
# English-taught, on-site + hybrid, tuition ≤500 EUR/semester
BASE_PARAMS = {
    "cert": "", "admReq": "",
    "langExamPC": "", "langExamLC": "", "langExamSC": "",
    "langDeAvailable": "", "langEnAvailable": "",
    "lang[]": "2",           # 2 = English
    "modStd[]": ["7", "2"],  # 7 = fully on-site, 2 = hybrid
    "fee": "2",              # up to 500 EUR/semester
    "sort": "4",
    "dur": "", "q": "",
    "display": "list",
    "isElearning": "", "isSep": "",
    "limit": 100,
}


def fetch_all() -> list[dict]:
    all_courses: list[dict] = []
    offset = 0

    while True:
        params = {**BASE_PARAMS, "offset": offset}
        resp = requests.get(DAAD_API, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        body = resp.json()

        courses = body.get("courses") or []
        if not courses:
            break

        all_courses.extend(courses)
        total = int(body.get("numResults") or 0)
        print(f"  offset={offset}: {len(courses)} courses "
              f"(total so far: {len(all_courses)}" + (f" / {total}" if total else "") + ")")

        if total and len(all_courses) >= total:
            break
        if len(courses) < BASE_PARAMS["limit"]:
            break

        offset += BASE_PARAMS["limit"]

    return all_courses


if __name__ == "__main__":
    print("Fetching courses from DAAD…")
    courses = fetch_all()

    if not courses:
        print("No courses fetched. Check your internet connection or filters.")
        raise SystemExit(1)

    print(f"\nTotal: {len(courses)} courses fetched.")
    out = Path("courses.json")
    out.write_text(json.dumps(courses, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {out.absolute()}")
    print("Next: commit and push courses.json so the live app uses it.")
