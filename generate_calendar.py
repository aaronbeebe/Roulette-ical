# generate_calendar.py
import os
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from ics import Calendar

BASE_PAGE = "https://www.ruhabenjamin.com/events"
OUTPUT_FILE = "docs/ruha.ics"

def fetch_ics_links(page_url: str):
    print(f"[info] Fetching events page: {page_url}")
    resp = requests.get(page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = set()

    # Preferred: visible "ICS" link text
    for a in soup.find_all("a"):
        text = (a.get_text(strip=True) or "").lower()
        href = a.get("href")
        if not href:
            continue
        if text == "ics":
            links.add(urljoin(page_url, href))

    # Fallback: any link ending with .ics
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".ics"):
            links.add(urljoin(page_url, href))

    print(f"[info] Found {len(links)} ICS links")
    for u in sorted(links):
        print(f"  - {u}")
    return sorted(links)

def merge_ics(ics_urls):
    master = Calendar()
    seen = set()
    now = datetime.now(timezone.utc)

    for url in ics_urls:
        try:
            print(f"[info] Downloading: {url}")
            r = requests.get(url, timeout=30)
            r.raise_for_status()

            subcal = Calendar(r.text)
            added = 0
            for ev in subcal.events:
                # Robust UID for de-dupe
                uid = getattr(ev, "uid", None) or f"{ev.name}|{ev.begin}|{ev.location}"
                if uid in seen:
                    continue

                # Keep only upcoming (comment this block to keep all)
                try:
                    ev_end = ev.end or ev.begin
                    if hasattr(ev_end, "tzinfo") and ev_end.tzinfo is None:
                        ev_end = ev_end.replace(tzinfo=timezone.utc)
                    if ev_end < now:
                        continue
                except Exception as e:
                    print(f"[warn] date compare issue for '{ev.name}': {e}")

                master.events.add(ev)
                seen.add(uid)
                added += 1

            print(f"[info] Added {added} events from {url}")

        except Exception as e:
            print(f"[warn] Skipping {url}: {e}")

    print(f"[info] Total merged events: {len(master.events)}")
    return master

def main():
    ics_urls = fetch_ics_links(BASE_PAGE)
    if not ics_urls:
        print("[error] No ICS links found. The page markup may have changed.")
        return 2

    cal = merge_ics(ics_urls)

    # Ensure output folder exists
    outdir = os.path.dirname(OUTPUT_FILE) or "."
    os.makedirs(outdir, exist_ok=True)

    serialized = cal.serialize()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(serialized)

    print(f"[success] Wrote {len(cal.events)} events to {OUTPUT_FILE}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
