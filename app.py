#!/usr/bin/env python3
"""Streamlit web app — DAAD International Programme Finder."""

import json
import os
import requests
import streamlit as st
from google import genai as google_genai

DAAD_BASE = "https://www2.daad.de"
DAAD_SEARCH_API = (
    f"{DAAD_BASE}/deutschland/studienangebote"
    "/international-programmes/en/result/search.json"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*",
    "Referer": (
        f"{DAAD_BASE}/deutschland/studienangebote"
        "/international-programmes/en/result/"
    ),
}
DEFAULT_PARAMS = {
    "cert": "", "admReq": "",
    "langExamPC": "", "langExamLC": "", "langExamSC": "",
    "degree[]": "", "subjectGroup[]": "",
}


# ── Data fetching (cached for 1 hour so repeat visitors are fast) ─────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_courses() -> tuple[list[dict], str | None]:
    """Returns (courses, error_message). error_message is None on success."""
    session = requests.Session()

    # Visit the main page first so the session picks up any required cookies
    try:
        session.get(
            f"{DAAD_BASE}/deutschland/studienangebote"
            "/international-programmes/en/result/",
            headers=HEADERS, timeout=15,
        )
    except Exception:
        pass  # non-fatal — continue without cookies

    all_courses: list[dict] = []
    page = 1

    while True:
        params = {**DEFAULT_PARAMS, "page": page, "limit": 100}
        try:
            resp = session.get(DAAD_SEARCH_API, params=params,
                               headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.HTTPError:
            return [], f"DAAD returned HTTP {resp.status_code}. The site may be blocking requests from this server."
        except requests.RequestException as exc:
            return [], f"Network error: {exc}"

        try:
            data = resp.json()
        except json.JSONDecodeError:
            return [], f"DAAD returned unexpected content (not JSON). Preview: {resp.text[:300]}"

        courses = (
            data.get("courses") or data.get("results") or
            data.get("items") or data.get("data") or []
        )
        if not courses:
            if not all_courses:
                return [], f"API responded but no courses found. Response keys: {list(data.keys())}"
            break

        all_courses.extend(courses)
        total = int(data.get("total") or data.get("numFound") or data.get("count") or 0)
        if (total and len(all_courses) >= total) or len(courses) < 100:
            break
        page += 1

    return all_courses, None


# ── AI matching ───────────────────────────────────────────────────────────────

def build_course_list(courses: list[dict]) -> str:
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
                     api_key: str, top_n: int) -> list[dict]:
    client = google_genai.Client(api_key=api_key)

    prompt = f"""You are a university admissions advisor helping a student find the most \
relevant English-taught international programmes at German universities.

STUDENT PROFILE:
{profile}

AVAILABLE PROGRAMMES (index|name|subject|institution, city|fees|link):
{build_course_list(courses)}

Select the {top_n} most relevant programmes for this student. Return ONLY a valid \
JSON array — no markdown, no explanation, just raw JSON:

[
  {{
    "rank": 1,
    "name": "Programme Name",
    "institution": "University Name",
    "city": "City",
    "why": "One sentence explaining why this fits the student's background and goals",
    "link": "https://full-url"
  }}
]

Be selective. Only include programmes with clear subject or career alignment."""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
    )
    raw = response.text.strip()

    # Strip markdown code fences if Gemini wraps the JSON
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.getenv("GEMINI_API_KEY", "")


# ── Page layout ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="DAAD Programme Finder",
    page_icon="🎓",
    layout="centered",
)

st.title("🎓 DAAD Programme Finder")
st.write(
    "Tell us about your academic background and we'll find the most relevant "
    "**English-taught programmes at German universities** for you."
)

st.divider()

profile = st.text_area(
    "Tell us about yourself",
    placeholder=(
        "Example: I have a Bachelor's in Business Administration with a focus on "
        "marketing and consumer behaviour. I'm interested in digital marketing, "
        "data analytics and sustainable business. I prefer a research-oriented programme."
    ),
    height=150,
)

top_n = st.slider(
    "How many recommendations would you like?",
    min_value=5, max_value=25, value=15,
)

st.divider()

search_clicked = st.button(
    "🔍 Find My Programmes",
    type="primary",
    use_container_width=True,
    disabled=not profile.strip(),
)

if search_clicked:
    api_key = get_api_key()
    if not api_key:
        st.error("This app is not configured yet. Please contact the app owner.")
        st.stop()

    with st.spinner("Fetching programmes from DAAD… (first load may take ~30 seconds)"):
        courses, fetch_error = fetch_all_courses()

    if fetch_error:
        st.error(f"Could not load programmes: {fetch_error}")
        st.stop()

    with st.spinner(f"AI is reading your profile and picking the best {top_n} matches…"):
        try:
            results = rank_with_gemini(courses, profile, api_key, top_n)
        except (json.JSONDecodeError, Exception) as e:
            st.error(f"Something went wrong with the AI response. Please try again. ({e})")
            st.stop()

    st.success(f"Done! Here are your top {len(results)} recommended programmes.")
    st.divider()

    for item in results:
        rank        = item.get("rank", "")
        name        = item.get("name", "Unknown")
        institution = item.get("institution", "")
        city        = item.get("city", "")
        why         = item.get("why", "")
        link        = item.get("link", "")

        st.subheader(f"{rank}. {name}")
        if institution or city:
            st.caption(f"📍 {institution}, {city}")
        if why:
            st.write(f"**Why it fits you:** {why}")
        if link:
            st.link_button("View Programme on DAAD →", link)
        st.divider()
