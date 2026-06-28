import requests, json

DAAD_API = (
    "https://www2.daad.de/deutschland/studienangebote"
    "/international-programmes/api/solr/en/search.json"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://www2.daad.de/deutschland/studienangebote/international-programmes/en/result/",
}

params = {
    "cert": "", "admReq": "",
    "langExamPC": "", "langExamLC": "", "langExamSC": "",
    "langDeAvailable": "", "langEnAvailable": "",
    "lang[]": "2",
    "modStd[]": ["7", "2"],
    "fee": "2",
    "sort": "4", "dur": "", "q": "",
    "display": "list", "isElearning": "", "isSep": "",
    "limit": 5, "offset": 0,
}

resp = requests.get(DAAD_API, params=params, headers=HEADERS, timeout=30)
data = resp.json()

print("numResults:", data.get("numResults"))
courses = data.get("courses", [])
print("courses in response:", len(courses))
if courses:
    print("First course:", json.dumps(courses[0], indent=2)[:600])
else:
    print("Raw response sample:", json.dumps(data)[:600])
