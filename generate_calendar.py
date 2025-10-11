# generate_calendar.py
import os
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event
import pytz

BASE_URL = "https://roulette.org/calendar/"
OUTPUT_FILE = "docs/roulette.ics"
TZ = pytz.timezone("America/New_York")

# Example listing date line:
#   "Saturday, November 1, 2025. 8:00 pm"
DATE_LINE_RE = re.compile(
    r"^[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\.\s+\d{1,2}:\d{2}\s*(AM|PM|am|pm)$"
)

def fetch_page(url: str) -> BeautifulSoup:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def iter_upcoming_pages(start_url: str, max_pages: int = 6):
    """Yield soups for page 1..N following 'Next page' pagination."""
    url = start_url
    for _ in range(max_pages):
        soup = fetch_page(url)
        yield soup
        next_link = soup.find("a", string=re.compile(r"Next page", re.I))
        if not next_link or not next_link.get("href"):
            break
        url = urljoin(url, next_link["href"])

def normalize_texts(node):
    """Return a list of non-empty text lines within node, stripped."""
    texts = []
    for t in node.find_all(string=True):
        s = t.strip()
        if s:
            texts.append(s)
    return texts

def extract_listing_fields(card, base_url):
    """
    From an event 'card' (using the <h2> anchor as the card root),
    return dict with title, date_line, url, and description_from_listing.
    Description is everything from 'Tickets' line onward (including it).
    """
    h2 = card if card.name == "h2" else card.find("h2")
    if not h2:
        return None

    a = h2.find("a", href=True)
    if not a:
        return None

    title = a.get_text(strip=True)
    event_url = urljoin(base_url, a["href"])

    # Heuristic card root: often h2.parent is the event block; if not, use h2 itself.
    root = h2.parent if h2.parent else h2

    texts = normalize_texts(root)

    date_line = None
    desc_from_listing = ""
    tickets_idx = None

    # Find the date line + index of "Tickets ..."
    for i, t in enumerate(texts):
        if DATE_LINE_RE.match(t):
            date_line = t
        if tickets_idx is None and t.lower().startswith("tickets"):
            tickets_idx = i

    if tickets_idx is not None:
        desc_from_listing = "\n".join(texts[tickets_idx:])  # include the Tickets line & everything after

    return {
        "title": title,
        "date_line": date_line,
        "url": event_url,
        "listing_desc": desc_from_listing,
    }

def parse_begin(dt_line: str) -> datetime:
    # "Saturday, November 1, 2025. 8:00 pm" -> datetime (NY tz-aware)
    left, timepart = dt_line.split(".", 1)  # ["Saturday, November 1, 2025", " 8:00 pm"]
    date_str = left.split(",", 1)[1].strip()   # "November 1, 2025"
    time_str = timepart.strip()                 # "8:00 pm"
    naive = datetime.strptime(f"{date_str} {time_str}", "%B %d, %Y %I:%M %p")
    return TZ.localize(naive)

def fetch_detail_description(url: str) -> str:
    """
    Optional: pull a fuller description from the event detail page.
    We'll be conservative—collect paragraph text under the main article/content.
    If structure changes, this safely returns "".
    """
    try:
        s = fetch_page(url)
    except Exception:
        return ""

    # Try common content containers in Roulette pages
    candidates = []
    # 1) Any obvious content container
    for sel in ["article", "div.entry-content", "div.content", "main", "div#content"]:
        for node in s.select(sel):
            txts = normalize_texts(node)
            # Skip nav/menus by requiring a minimal length
            body = "\n".join(txts).strip()
            if len(body) > 120:  # heuristic: non-trivial content
                candidates.append(body)

    # Pick the longest plausible block
    if candidates:
        candidates.sort(key=len, reverse=True)
        return candidates[0]
    return ""

def build_calendar() -> Calendar:
    cal = Calendar()
    total = 0
    for soup in iter_upcoming_pages(BASE_URL, max_pages=6):
        # Use all H2s with links as event anchors
        for h2 in soup.select("h2"):
            item = extract_listing_fields(h2, BASE_URL)
            if not item or not item.get("date_line"):
                continue

            try:
                start = parse_begin(item["date_line"])
            except Exception:
                continue

            # Listing description (Tickets… onward)
            listing_desc = item.get("listing_desc", "").strip()

            # Optional: fetch full detail page and append
            detail_desc = fetch_detail_description(item["url"]).strip()

            # Build final description
            parts = []
            if listing_desc:
                parts.append(listing_desc)
            if detail_desc:
                parts.append(detail_desc)
            description = "\n\n".join(parts).strip()

            e = Event()
            e.name = item["title"]
            e.begin = start
            e.duration = {"hours": 2}  # adjust if you prefer
            e.location = "Roulette Intermedium, 509 Atlantic Ave, Brooklyn, NY"
            e.url = item["url"]
            if description:
                e.description = description

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
