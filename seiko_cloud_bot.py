"""
Carousell -> Telegram alert bot (cloud version for GitHub Actions).
Runs ONE check each time GitHub starts it, then stops.
"""

import json
import os
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

# ---------- 1. FILL THESE IN ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]   # stored as a GitHub secret
CHAT_ID = os.environ["CHAT_ID"]       # stored as a GitHub secret

# ---------- 2. SEARCH SETTINGS ----------
SEARCH_WORD = "seiko"

# Skip listings whose title has "mod", "mods", "modded" or "modding".
# (Written carefully so that words like "model" or "modern" are NOT skipped.)
EXCLUDE = re.compile(r"\bmod(s|ded|ding)?\b", re.IGNORECASE)

# sort_by=3 = "Recent" on Carousell, so the newest listings come first
SEARCH_URL = f"https://www.carousell.sg/search/{SEARCH_WORD}?sort_by=3"
SEEN_FILE = Path(__file__).with_name("seen_listings.json")
LISTING_LINK = re.compile(r"/p/([^/?#]+)-(\d+)")


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=20)
    if not r.ok:
        print("Telegram error:", r.text)


def fetch_listings(page):
    """Open the search page and return {listing_id: (title_text, link)}."""
    page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)  # let the listings load

    results = {}
    for a in page.query_selector_all('a[href*="/p/"]'):
        href = a.get_attribute("href") or ""
        m = LISTING_LINK.search(href)
        if not m:
            continue
        slug, listing_id = m.group(1), m.group(2)
        link = f"https://www.carousell.sg/p/{slug}-{listing_id}/"
        # Card text usually holds title + price; fall back to the URL words
        text = (a.inner_text() or "").strip()
        if not text:
            text = slug.replace("-", " ")
        # keep the longest text we find for this listing
        if listing_id not in results or len(text) > len(results[listing_id][0]):
            results[listing_id] = (text, link)
    return results


def main():
    seen = load_seen()
    first_run = not seen

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        listings = fetch_listings(page)
        browser.close()

    print(f"found {len(listings)} listings")
    if not listings:
        print("No listings found - Carousell may be blocking this run.")
        return

    for listing_id, (text, link) in listings.items():
        if listing_id in seen:
            continue
        seen.add(listing_id)
        slug_words = link.split("/p/")[1].replace("-", " ")
        if EXCLUDE.search(text) or EXCLUDE.search(slug_words):
            continue
        if not first_run:
            send_telegram(f"🆕 New Seiko on Carousell\n\n{text}\n\n{link}")

    save_seen(seen)
    if first_run:
        send_telegram(f"✅ Cloud bot is running. Watching '{SEARCH_WORD}' (no mods).")


if __name__ == "__main__":
    main()
