# generate_calendar.py
import os
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
import pytz

BASE_URL = "https://roulette.org/calendar/"      # Upcoming events archive
OUTPUT_FILE = "docs/roulette.ics"
TZ = pytz.timezone("America/New_York")

# Matches lines like: "Saturday, November 1, 2025. 8:00 pm"
DATE_LINE_RE = re.compile(
    r"^[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\.\s+\d{1,2}:\d{2}\s*(AM|PM|am|pm)$"
)

def fetch_page(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def iter_upcoming_pages(start_url, max_pages=6):
    """Yield soup objects for page 1..N until no 'Next page'."""
    url = start_url
    for _ in range(max_pages):
        soup = fetch_page(url)
        yield soup
        # Find 'Next page' link (pagination)
        next_link = soup.find("a", string=re.compile(r"Next page", re.I))
        if not next_link or not next_link.get("href"):
            break
        url = urljoin(url, next_link["href"])

def parse_events_from_page(soup, base_url):
    """Yield dicts with title, dt, url, and optional price."""
    for h2 in soup.select("h2"):
        a = h2.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        event_url = urljoin(base_url, a["href"])

        # The date/time line appears in the following siblings under each event block
        # Example: "Saturday, November 1, 2025. 8:00 pm"
        date_line = None
        price = None

        # Walk a few blocks below the title to find the date line + price/Tickets
        cur = h2.parent
        # Search within the same event card for text nodes
        texts = [t.get_text(strip=True) for t in cur.find_all(text=True) if str(t).strip()]
        # Heuristic: first line matching DATE_LINE_RE is our datetime
        for t in texts:
            if DATE_LINE_RE.match(t):
                date_line = t
            # capture something like "Tickets $25"
            if t.startswith("Tickets "):
                price = t

        if not date_line:
            continue
        yield {"title": title, "date_line": date_line, "url": event_url, "price": price or ""}

def parse_begin(dt_line: str) -> datetime:
    # Example input: "Saturday, November 1, 2025. 8:00 pm"
    # Remove weekday, split at "."
    left, timepart = dt_line.split(".", 1)
    # left: "Saturday, November 1, 2025"
    # timepart: " 8:00 pm"
    date_str = left.split(",", 1)[1].strip()  # "November 1, 2025"
    time_str = timepart.strip()                # "8:00 pm"
    naive = datetime.strptime(f"{date_str} {time_str}", "%B %d, %Y %I:%M %p")
    return TZ.localize(naive)                  # timezone-aware (NY)

def build_calendar():
    cal = Calendar()
    total = 0
    for soup in iter_upcoming_pages(BASE_URL, max_pages=6):
        for ev in parse_events_from_page(soup, BASE_URL):
            start = parse_begin(ev["date_line"])
            e = Event()
            e.name = ev["title"]
            e.begin = start
            e.duration = {"hours": 2}          # default length; adjust if you like
            e.location = "Roulette Intermedium, 509 Atlantic Ave, Brooklyn, NY"
            e.description = ev["price"]
            e.url = ev["url"]
            cal.events.add(e)
            total += 1
    print(f"[info] Built calendar with {total} events")
    return cal

def main():
    cal = build_calendar()
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(cal.serialize())
    print(f"[success] Wrote {len(cal.events)} events to {OUTPUT_FILE}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
