"""
debug_screener.py
─────────────────
Dumps the raw quarterly P&L table structure for one stock so you can
verify what the HTML parser actually sees vs what screener.in shows.

Usage:
    python debug_screener.py ANGELONE
    python debug_screener.py ANGELONE consolidated
"""

import sys
import re
import requests
from bs4 import BeautifulSoup

SESSION_ID = "kwe6vuy1vx4jsbxl04k7go2tm5et27f7"


def make_session(sid):
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.screener.in/",
    })
    s.cookies.set("sessionid", sid, domain="www.screener.in")
    return s


def dump_table(table, label=""):
    """Print every row of a BeautifulSoup table object."""
    # print(f"\n  ── Table: {label} ──")
    rows = table.find_all("tr")
    for r_idx, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        texts = [f"[{c.get_text(strip=True)!r:>20s}]" for c in cells]
        marker = "HEADER" if r_idx == 0 else f"row{r_idx:02d}"
        # print(f"  {marker}: {'  '.join(texts)}")


def main():
    symbol   = sys.argv[1].upper() if len(sys.argv) > 1 else "ANGELONE"
    use_cons = len(sys.argv) > 2 and "cons" in sys.argv[2].lower()

    session = make_session(SESSION_ID)
    session.get("https://www.screener.in/", timeout=10)

    urls = (
        [f"https://www.screener.in/company/{symbol}/consolidated/",
         f"https://www.screener.in/company/{symbol}/"]
        if use_cons else
        [f"https://www.screener.in/company/{symbol}/",
         f"https://www.screener.in/company/{symbol}/consolidated/"]
    )

    soup = used_url = None
    for url in urls:
        r = session.get(url, timeout=20)
        # print(f"GET {url}  ->  HTTP {r.status_code}  ({len(r.content):,} bytes)")
        if r.status_code == 200:
            soup     = BeautifulSoup(r.text, "lxml")
            used_url = url
            if soup.find("section", id="quarters") or soup.find("section", id="profit-loss"):
                print(f"  OK - P&L section found\n")
                break
            print("  No P&L section - trying next URL")
            soup = None

    if not soup:
        print("Could not load page. Check SESSION_ID.")
        return

    # Active report type
    active = soup.select_one("ul.left-nav-pills li.active a")
    print(f"Active report type: {active.get_text(strip=True) if active else 'unknown'}")

    # Dump raw table rows
    for sec_id in ("quarters", "profit-loss"):
        section = soup.find("section", id=sec_id)
        if not section:
            print(f"Section #{sec_id}: NOT FOUND")
            continue

        print(f"\n{'='*70}")
        print(f"  Section: #{sec_id}")
        print(f"{'='*70}")

        tables = section.find_all("table")
        print(f"  Tables found: {len(tables)}")
        for t_idx, table in enumerate(tables):
            dump_table(table, label=f"table[{t_idx}] in #{sec_id}")

    # Show what the fixed parser would extract
    print(f"\n{'='*70}")
    print("  WHAT THE FIXED PARSER EXTRACTS")
    print(f"{'='*70}")

    WANTED = {
        "sales":            "Sales",
        "revenue":          "Sales",
        "operating profit": "EBITDA",
        "opm %":            "EBITDA Margin %",
        "net profit":       "Net Profit",
        "eps in rs":        "EPS",
        "eps":              "EPS",
    }

    for sec_id in ("quarters", "profit-loss"):
        section = soup.find("section", id=sec_id)
        if not section:
            continue
        freq = "quarterly" if sec_id == "quarters" else "annual"
        for table in section.find_all("table"):
            thead = table.find("thead")
            if thead:
                hcells = [td.get_text(strip=True) for td in thead.find_all(["th","td"])]
            else:
                rows   = table.find_all("tr")
                hcells = [td.get_text(strip=True) for td in rows[0].find_all(["th","td"])] if rows else []

            # Track which column indices are real periods vs TTM/blank
            skip_indices = set()
            periods      = []   # list of (original_col_index, label)
            for col_i, h in enumerate(hcells[1:], start=1):
                h_clean = h.strip().upper()
                if h_clean in ("TTM", "TRAILING", "") or not h_clean:
                    skip_indices.add(col_i)
                else:
                    periods.append((col_i, h))

            skipped_labels = [hcells[i] for i in sorted(skip_indices) if i < len(hcells)]
            print(f"\n  [{freq}] Periods : {[p for _,p in periods]}")
            print(f"  [{freq}] Skipped : {skipped_labels}")

            tbody     = table.find("tbody") or table
            data_rows = tbody.find_all("tr") if thead else table.find_all("tr")[1:]

            for row in data_rows:
                cells    = row.find_all(["td","th"])
                if not cells:
                    continue
                label    = cells[0].get_text(strip=True)
                label_lc = label.lower().strip()
                matched  = next((v for k,v in WANTED.items() if k in label_lc), None)
                if not matched:
                    continue

                print(f"\n    Metric: {matched!r}  (row label: {label!r})")
                for col_i, period_label in periods:
                    if col_i < len(cells):
                        raw = cells[col_i].get_text(strip=True).replace(",","").replace("%","")
                        print(f"      {period_label:>12s}  ->  {raw}")
                    else:
                        print(f"      {period_label:>12s}  ->  (no cell)")
        break


if __name__ == "__main__":
    main()