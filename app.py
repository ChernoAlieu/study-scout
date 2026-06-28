#!/usr/bin/env python3
"""Streamlit web app — DAAD International Programme Finder."""

import json
import os
from pathlib import Path
import requests
import streamlit as st

DAAD_BASE = "https://www2.daad.de"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def get_gemini_model(api_key: str) -> str:
    resp = requests.get(f"{GEMINI_BASE}/models?key={api_key}", timeout=10)
    if resp.ok:
        models = [
            m["name"].split("/")[-1]
            for m in resp.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "flash" in m["name"]
        ]
        if models:
            return models[0]
    return "gemini-2.0-flash"


# ── Course loading (from pre-fetched JSON file) ───────────────────────────────

@st.cache_data(show_spinner=False)
def load_courses() -> tuple[list[dict], str | None]:
    courses_file = Path(__file__).parent / "courses.json"
    if not courses_file.exists():
        return [], (
            "Course data not found. Please run `python fetch_data.py` locally "
            "and push courses.json to the repository."
        )
    try:
        data = json.loads(courses_file.read_text(encoding="utf-8"))
        return data, None
    except Exception as exc:
        return [], f"Could not read courses.json: {exc}"


# ── AI matching (direct HTTP — no SDK required) ───────────────────────────────

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
    prompt = f"""You are a university admissions advisor helping a student find the most \
relevant English-taught international programmes at German universities.

STUDENT PROFILE:
{profile}

AVAILABLE PROGRAMMES (index|name|subject|institution, city|fees|link):
{build_course_list(courses)}

Select the {top_n} most relevant programmes for this student. Return ONLY a valid \
JSON array — no markdown, no extra text, just raw JSON:

[
  {{
    "rank": 1,
    "name": "Programme Name",
    "institution": "University Name",
    "city": "City",
    "why": "One sentence explaining why this fits the student",
    "link": "https://full-url"
  }}
]

Be selective. Only include programmes with clear subject or career alignment."""

    model = get_gemini_model(api_key)
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    resp = requests.post(
        f"{url}?key={api_key}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        },
        timeout=90,
    )
    resp.raise_for_status()
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.getenv("GEMINI_API_KEY", "")


# ── Page ──────────────────────────────────────────────────────────────────────

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

if st.button("🔍 Find My Programmes", type="primary",
             use_container_width=True, disabled=not profile.strip()):

    api_key = get_api_key()
    if not api_key:
        st.error("This app is not configured yet. Please contact the app owner.")
        st.stop()

    courses, load_error = load_courses()
    if load_error:
        st.error(load_error)
        st.stop()

    with st.spinner(f"AI is reading your profile and picking the best {top_n} matches…"):
        try:
            results = rank_with_gemini(courses, profile, api_key, top_n)
        except requests.HTTPError as exc:
            code = exc.response.status_code
            if code == 429:
                st.error("Gemini API error: 429 — rate limit exceeded. Wait a moment and try again, or set up billing in Google AI Studio for higher limits.")
            elif code in (401, 403):
                st.error(f"Gemini API error: {code} — invalid or unauthorised API key. Check your Streamlit secret.")
            else:
                detail = exc.response.text[:500] if exc.response.text else "no body"
                st.error(f"Gemini API error: {code}. Details: {detail}")
            st.stop()
        except (json.JSONDecodeError, KeyError):
            st.error("AI returned an unexpected response. Please try again.")
            st.stop()

    st.success(f"Done! Here are your top {len(results)} recommended programmes.")
    st.divider()

    for item in results:
        st.subheader(f"{item.get('rank', '')}. {item.get('name', 'Unknown')}")
        institution = item.get("institution", "")
        city = item.get("city", "")
        if institution or city:
            st.caption(f"📍 {institution}, {city}")
        if item.get("why"):
            st.write(f"**Why it fits you:** {item['why']}")
        if item.get("link"):
            st.link_button("View Programme on DAAD →", item["link"])
        st.divider()
