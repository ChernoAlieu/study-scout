#!/usr/bin/env python3
"""DAAD International Programmes scraper with Gemini AI matching."""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
import google.generativeai as genai

DAAD_BASE = "https://www2.daad.de"
DAAD_SEARCH_API = (
    f"{DAAD_BASE}/deutschland/studienangebote"
    "/international-programmes/en/result/search.json"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Referer": f"{DAAD_BASE}/deutschland/studienangebote/international-programmes/en/result/",
}


def extract_params_from_url(page_url: str) -> dict:
    """Parse query params from a DAAD results page URL."""
    if not page_url.startswith("http"):
        page_url = "https://" + page_url
    parsed = urlparse(page_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    # parse_qs wraps everything in lists — flatten single-value entries
    return {k: (v[0] if len(v) == 1 else v) for k, v in params.items()}


def fetch_all_courses(base_params: dict) -> list[dict]:
    """Page through the DAAD search API and collect all course records."""
    all_courses: list[dict] = []
    page = 1

    while True:
        params = {**base_params, "page": page, "limit": 100}
        try:
            resp = requests.get(DAAD_SEARCH_API, params=params,
                                headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            print(f"  Network error on page {page}: {exc}")
            break
        except json.JSONDecodeError:
            print(f"  Unexpected non-JSON response on page {page}")
            break

        # The API may use different keys depending on version
        courses = (
            data.get("courses")
            or data.get("results")
            or data.get("items")
            or data.get("data")
            or []
        )

        if not courses:
            break

        all_courses.extend(courses)
        total = int(data.get("total") or data.get("numFound") or data.get("count") or 0)
        print(f"  Page {page}: {len(courses)} courses  (running total: {len(all_courses)}"
              + (f" / {total}" if total else "") + ")")

        if (total and len(all_courses) >= total) or len(courses) < 100:
            break

        page += 1

    return all_courses


def build_course_list(courses: list[dict]) -> str:
    """Format courses as a compact numbered list for the AI prompt."""
    lines = []
    for i, c in enumerate(courses, 1):
        name    = c.get("courseName") or c.get("name") or "Unknown"
        subject = c.get("subject") or ""
        academy = c.get("academy") or c.get("institution") or ""
        city    = c.get("city") or ""
        fees    = c.get("tuitionFees") or c.get("costString") or ""
        link    = c.get("link") or ""
        if link and not link.startswith("http"):
            link = DAAD_BASE + link
        lines.append(f"{i}|{name}|{subject}|{academy}, {city}|fees:{fees}|{link}")

    return "\n".join(lines)


def rank_with_gemini(courses: list[dict], profile: str,
                     api_key: str, top_n: int = 20) -> str:
    """Ask Gemini to pick and rank the most relevant programmes."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    course_list = build_course_list(courses)

    prompt = f"""You are a university admissions advisor helping a student find the best-fit \
international Master's programmes in Germany.

STUDENT PROFILE:
{profile}

AVAILABLE PROGRAMMES (pipe-separated: index|name|subject|institution, city|fees|link):
{course_list}

TASK:
Select the {top_n} most relevant programmes for this student and rank them from most \
to least relevant. Consider subject alignment, career goals, and programme focus \
(research vs. applied).

For each programme output EXACTLY this format:

RANK. Programme Name
   Institution, City
   Why: [one sentence explaining the fit]
   Link: [full URL]

Include only genuinely relevant programmes. Be selective."""

    response = model.generate_content(prompt)
    return response.text


def save_html(text: str, courses: list[dict], path: Path) -> None:
    """Save results as a simple HTML file with clickable links."""
    # Convert plain-text links to anchor tags
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Link:"):
            url = stripped[5:].strip()
            lines.append(f'   Link: <a href="{url}" target="_blank">{url}</a>')
        else:
            lines.append(line)
    body = "\n".join(lines)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DAAD Programme Recommendations</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; line-height: 1.6; }}
  pre {{ white-space: pre-wrap; word-break: break-word; }}
  a {{ color: #0057a8; }}
</style>
</head>
<body>
<h1>DAAD Programme Recommendations</h1>
<p><em>{len(courses)} programmes fetched &amp; ranked by Gemini 1.5 Flash</em></p>
<pre>{body}</pre>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


def main() -> None:
    print("╔════════════════════════════════════════╗")
    print("║    DAAD Programme Matcher (Gemini)     ║")
    print("╚════════════════════════════════════════╝\n")

    # --- Gemini API key ---
    api_key = os.getenv("GEMINI_API_KEY") or input(
        "Gemini API key (free at aistudio.google.com/apikey): "
    ).strip()
    if not api_key:
        sys.exit("No API key provided.")

    # --- DAAD URL ---
    print(
        "\nPaste the DAAD results page URL with your filters already set in the browser."
        "\n(Set filters on the site, copy the URL, paste it here.)"
        "\nOr press Enter to fetch ALL English-language programmes with no extra filters.\n"
    )
    page_url = input("DAAD URL: ").strip()

    if page_url:
        base_params = extract_params_from_url(page_url)
        print(f"  Parsed {len(base_params)} filter parameters from URL.")
    else:
        # Minimal defaults: matches the applied filters visible in the screenshots
        base_params = {
            "cert": "", "admReq": "",
            "langExamPC": "", "langExamLC": "", "langExamSC": "",
            "degree[]": "", "subjectGroup[]": "",
        }

    # --- User profile ---
    print(
        "\nDescribe your background and what you're looking for."
        "\nExample: 'BSc Computer Science, passionate about AI and data science,"
        " looking for a research-oriented Master's.'\n"
    )
    profile = input("Your profile: ").strip()
    if not profile:
        sys.exit("No profile provided.")

    top_n = 20
    raw = input(f"\nHow many top recommendations? (default {top_n}): ").strip()
    if raw.isdigit():
        top_n = int(raw)

    # --- Fetch ---
    print(f"\nFetching courses from DAAD…")
    courses = fetch_all_courses(base_params)

    if not courses:
        print(
            "\nNo courses returned. Possible reasons:\n"
            "  - The API URL changed (check Network tab for the current search.json URL)\n"
            "  - The filter parameters need updating\n"
        )
        sys.exit(1)

    print(f"\nTotal fetched: {len(courses)} programmes")

    # --- Rank ---
    print(f"\nAsking Gemini to pick the top {top_n} matches for your profile…")
    results = rank_with_gemini(courses, profile, api_key, top_n)

    # --- Output ---
    print("\n" + "═" * 52)
    print(f"  TOP {top_n} RECOMMENDED PROGRAMMES")
    print("═" * 52 + "\n")
    print(results)

    txt_path  = Path("recommendations.txt")
    html_path = Path("recommendations.html")

    txt_path.write_text(results, encoding="utf-8")
    save_html(results, courses, html_path)

    print(f"\nSaved:")
    print(f"  {txt_path.absolute()}")
    print(f"  {html_path.absolute()}  ← open this for clickable links")


if __name__ == "__main__":
    main()
