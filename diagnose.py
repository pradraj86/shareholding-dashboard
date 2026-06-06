"""
diagnose.py  —  run this to identify why financials aren't loading
Usage:  python diagnose.py TRENT
"""
import re, sys, requests
from bs4 import BeautifulSoup

SESSION_ID = "kwe6vuy1vx4jsbxl04k7go2tm5et27f7"
SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else "TRENT"

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.screener.in/",
})
s.cookies.set("sessionid", SESSION_ID, domain="www.screener.in")

# ── 1. Fetch HTML ─────────────────────────────────────────────────────────────
html = None
for url in [
    f"https://www.screener.in/company/{SYMBOL}/consolidated/",
    f"https://www.screener.in/company/{SYMBOL}/",
]:
    r = s.get(url, timeout=20)
    print(f"HTML fetch: {url}  →  HTTP {r.status_code}  ({len(r.text):,} chars)")
    if r.status_code == 200:
        html = r.text
        fetched_url = url
        break

if not html:
    print("FAILED — could not fetch any page. Check session cookie.")
    sys.exit(1)

soup = BeautifulSoup(html, "lxml")

# ── 2. List all sections ──────────────────────────────────────────────────────
print("\n=== Sections found in page ===")
for sec in soup.find_all("section"):
    sid    = sec.get("id", "(no id)")
    tables = sec.find_all("table")
    rows   = sum(len(t.find_all("tr")) for t in tables)
    first_row_cells = 0
    if tables:
        fr = tables[0].find("tr")
        if fr:
            first_row_cells = len(fr.find_all(["td", "th"]))
    print(f"  id={sid!r:28s}  tables={len(tables)}  total_rows={rows:3d}  first_row_cells={first_row_cells}")

# ── 3. Inspect #quarters section ─────────────────────────────────────────────
print("\n=== #quarters section ===")
q_sec = soup.find("section", {"id": "quarters"})
if q_sec:
    print(f"Found (inner HTML: {len(str(q_sec)):,} chars)")
    for t in q_sec.find_all("table"):
        thead = t.find("thead")
        if thead:
            headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
            print(f"  Headers: {headers}")
        all_rows = t.find_all("tr")
        print(f"  Total <tr> rows: {len(all_rows)}")
        for row in all_rows[:6]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            print(f"    {cells}")
else:
    print("NOT FOUND — data is probably loaded via AJAX (JS-rendered)")
    print("  → The HTML fallback won't work; export API is the only option.")

# ── 4. Test export API with proper headers ────────────────────────────────────
print("\n=== Export API test ===")
m = re.search(r'/api/company/(\d+)/export/', html)
cid = int(m.group(1)) if m else None
print(f"Company ID extracted from HTML: {cid}")

if not cid:
    print("ERROR: could not find company ID in page. Is the session cookie valid?")
    sys.exit(1)

for rtype in ["consolidated", "standalone"]:
    api_url = f"https://www.screener.in/api/company/{cid}/export/?type={rtype}"
    api_headers = {
        "Referer": fetched_url,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/csv,application/csv,*/*",
    }
    r2 = s.get(api_url, headers=api_headers, timeout=20)
    ct = r2.headers.get("Content-Type", "")
    print(f"\n  type={rtype}:")
    print(f"    HTTP {r2.status_code}  Content-Type={ct!r}  body_len={len(r2.text):,}")
    if r2.status_code == 200 and len(r2.text) > 50:
        print(f"    First 500 chars of response:")
        print("    " + r2.text[:500].replace("\n", "\n    "))
    else:
        print(f"    Response body: {r2.text[:300]!r}")