from pathlib import Path
from datetime import datetime
import requests
import zipfile
import pandas as pd
import re

DATA_DIR = Path("data")
PR_DIR = DATA_DIR / "pr"
PR_DIR.mkdir(parents=True, exist_ok=True)

PARQUET_FILE = DATA_DIR / "corporate_actions_all.parquet"


def download_pr_file(dt):

    fname = f"PR{dt.strftime('%d%m%y')}.zip"

    url = (
        "https://nsearchives.nseindia.com/"
        f"archives/equities/bhavcopy/pr/{fname}"
    )
    print("Downloading:", url)
    zip_path = PR_DIR / fname

    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=60
    )

    if r.status_code != 200:
        raise Exception(
            f"Download failed: {r.status_code}"
        )

    zip_path.write_bytes(r.content)

    return zip_path


def extract_zip(zip_file):

    with zipfile.ZipFile(zip_file) as z:
        z.extractall(PR_DIR)

    txt_files = list(PR_DIR.glob("an*.txt"))

    if not txt_files:
        raise Exception("Announcement file not found")

    return txt_files[0]


def parse_file(txt_file, dt):

    rows = []

    with open(
        txt_file,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        for line in f:

            line = line.strip()

            if (
                not line
                or line.startswith("COMPANY NAME")
            ):
                continue

            m = re.match(
                r"^(.*?)\s+([A-Z0-9&\-.]+)\s*:\s*(.*)$",
                line
            )

            if m:

                symbol = m.group(2).strip().upper()
                raw_ann = m.group(3).strip()

                parts = raw_ann.split(symbol + " : ", 1)

                if len(parts) == 2:
                    ann_type = parts[0].strip()
                    ann_text = parts[1].strip()
                else:
                    ann_type = raw_ann
                    ann_text = ""

                rows.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "company": m.group(1).strip(),
                    "symbol": symbol,
                    "announcement_type": ann_type,
                    "announcement_text": ann_text
                })

    return pd.DataFrame(rows)


def update_master(df_new):

    if PARQUET_FILE.exists():

        master = pd.read_parquet(
            PARQUET_FILE
        )

        master = pd.concat(
            [master, df_new],
            ignore_index=True
        )

        master.drop_duplicates(
            subset=[
                "date",
                "symbol",
                "announcement_type",
                "announcement_text"
            ],
            inplace=True
        )

    else:
        master = df_new

    master.to_parquet(
        PARQUET_FILE,
        index=False
    )

    print(
        f"Saved {len(master)} announcements"
    )

from datetime import datetime, timedelta
import requests

def get_latest_available_date(max_days=15):

    session = requests.Session()

    session.headers.update({
        "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/137.0 Safari/537.36"
    })

    for i in range(max_days):

        dt = datetime.today() - timedelta(days=i)

        fname = f"PR{dt.strftime('%d%m%y')}.zip"

        url = (
            "https://nsearchives.nseindia.com/"
            f"archives/equities/bhavcopy/pr/{fname}"
        )

        try:

            r = session.head(
                url,
                timeout=15,
                allow_redirects=True
            )

            print(
                f"Checking {fname} : {r.status_code}"
            )

            if r.status_code == 200:
                return dt

        except Exception as e:
            print(e)

    raise Exception(
        "No NSE PR file found in last 15 days"
    )
from datetime import datetime, timedelta

if __name__ == "__main__":

    success = False

    for i in range(15):

        dt = datetime.today() - timedelta(days=i)

        try:

            print(
                f"Trying {dt.strftime('%d-%b-%Y')}"
            )

            zip_file = download_pr_file(dt)

            print("Downloaded")

            txt_file = extract_zip(zip_file)

            print("Extracted")

            df = parse_file(txt_file, dt)

            print(
                f"Parsed {len(df)} rows"
            )

            update_master(df)

            success = True

            break

        except Exception as e:

            print(
                f"Failed {dt.strftime('%d-%b-%Y')} : {e}"
            )

    if not success:

        raise Exception(
            "No PR file found in last 15 days"
        )