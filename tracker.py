"""WalkingPad Z1 / C2 availability tracker for Georgian sites.

Runs once a day on GitHub Actions. Opens each site's search page in a real
(headless) browser, reads only what is actually on the page, and sends a
Telegram message for new listings, restocks and price drops. state.json
remembers what was already sent so nothing is sent twice.
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from playwright.sync_api import sync_playwright

from sites import SEARCH_TERMS, SITES

# "github" runs on GitHub's servers; "home" runs on your Mac for sites that block servers.
WHERE = os.environ.get("TRACKER_WHERE", "github")
STATE_FILE = "state.json" if WHERE == "github" else "state-home.json"
RELIST_AFTER_DAYS = 3        # missing this long, then back = "restock / relisted"
PRICE_DROP_PCT = 5           # notify if price falls at least this much
MAX_MESSAGES_PER_RUN = 25

BRAND_RE = re.compile(r"walking\s*pad|kingsmith|king\s*smith|ვოლქინგ|уокинг", re.I)
MODEL_RES = {"Z1": re.compile(r"(?<![a-z0-9])z1(?![0-9])", re.I),
             "C2": re.compile(r"(?<![a-z0-9])c2(?![0-9])", re.I)}
USED_RE = re.compile(r"\bused\b|second[\s-]?hand|მეორად|ნახმარ|б/у|подержан", re.I)
NEW_RE = re.compile(r"\bnew\b|ახალი|новы", re.I)
TREADMILL_RE = re.compile(r"treadmill|სარბენ|ბილიკ|беговая|дорожк", re.I)
TBILISI_RE = re.compile(r"tbilisi|თბილის|тбилис", re.I)
OOS_RE = re.compile(r"out of stock|sold out|not available|არ არის მარაგში|მარაგში არ|"
                    r"ამოიწურა|გაყიდულია|нет в наличии|распродан", re.I)
BLOCK_RE = re.compile(r"just a moment|captcha|access denied|attention required|"
                      r"verify you are human|403 forbidden", re.I)
PRICE_SYM_RE = re.compile(
    r"(\d{1,3}(?:[  ,]\d{3})+|\d{2,6})(?:[.,]\d{1,2})?\s*(?:₾|gel|ლარი|ლ\.?(?![ა-ჰ]))"
    r"|(?:₾|gel)\s*(\d{1,3}(?:[  ,]\d{3})+|\d{2,6})", re.I)
PRICE_BARE_RE = re.compile(
    r"(?<![\d.,a-z])(\d{1,2}[  ,]?\d{3}|\d{3})(?:[.,]\d{2})?(?![\d.,]|\s*(?:kg|კგ|km|კმ|w\b|mm|cm|სმ|%))",
    re.I)

# JavaScript run inside the page: for every link, find the nearest "card"
# around it that contains a price, and return its text.
EXTRACT_JS = """
() => {
  const out = []; const seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href;
    if (!href || !href.startsWith('http') || seen.has(href)) continue;
    seen.add(href);
    let el = a, card = '';
    for (let i = 0; i < 7 && el; i++) {
      const t = (el.innerText || '').trim();
      const links = new Set([...el.querySelectorAll('a[href]')].map(x => x.href));
      if (t.length > 1200 || links.size > 4) break;
      card = t;
      if (/₾|GEL|ლარი|\\d[\\d ,.]*\\s*ლ/i.test(t)) break;
      el = el.parentElement;
    }
    const title = (a.innerText || a.title || a.getAttribute('aria-label') || '').trim();
    out.push({href, title, text: card || title});
  }
  return out;
}
"""


def log(msg):
    print(msg, flush=True)


def now():
    return datetime.now(timezone.utc)


def base_domain(url):
    return ".".join(urlsplit(url).netloc.split(":")[0].lower().split(".")[-2:])


def clean_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower().replace("www.", ""), p.path.rstrip("/"), "", ""))


def parse_price(text, allow_bare):
    m = PRICE_SYM_RE.search(text)
    raw, shown = None, True
    if m:
        raw = m.group(1) or m.group(2)
    elif allow_bare:
        for b in PRICE_BARE_RE.finditer(text):
            val = int(re.sub(r"[^\d]", "", b.group(1)))
            if 150 <= val <= 8000:
                raw, shown = b.group(1), False
                break
    if not raw:
        return None, False
    val = int(re.sub(r"[^\d]", "", raw))
    return (val, shown) if 50 <= val <= 20000 else (None, False)


def classify(item, site):
    """Return a listing dict if this link is a WalkingPad Z1/C2, else None."""
    blob = f"{item['title']} {item['text']} {item['href'].replace('-', ' ').replace('_', ' ')}"
    if not (BRAND_RE.search(blob) or (re.search(r"xiaomi|сяоми|შაომი", blob, re.I)
                                       and TREADMILL_RE.search(blob))):
        return None
    models = [m for m, r in MODEL_RES.items() if r.search(blob)]
    if len(models) != 1:          # none, or a page mentioning both (category/compare page)
        return None
    if base_domain(item["href"]) != base_domain(site["url"]):
        return None               # ads / links to other websites
    text = item["text"]
    price, shown = parse_price(text, allow_bare=site["kind"] == "retailer")
    if USED_RE.search(text):
        cond = "Used"
    elif site["kind"] == "retailer":
        cond = "New (shop)"
    elif NEW_RE.search(text):
        cond = "New"
    else:
        cond = "Not stated"
    title = (item["title"] or text).split("\n")[0].strip()[:120]
    return {
        "site": site["name"], "kind": site["kind"], "model": models[0],
        "title": title, "url": item["href"], "price": price, "price_shown_with_currency": shown,
        "condition": cond, "tbilisi": bool(TBILISI_RE.search(text)),
        "in_stock": not OOS_RE.search(text),
    }


def scrape_site(page, site):
    """Returns (matching Z1/C2 listings, number of WalkingPad-related links seen)."""
    found = {}
    related = set()
    errors = []
    for term in SEARCH_TERMS:
        url = site["url"].format(q=quote(term))
        for attempt in (1, 2):
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if resp is not None and resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status}")
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                for _ in range(4):  # trigger lazy-loaded results
                    page.mouse.wheel(0, 3000)
                    page.wait_for_timeout(700)
                body = page.inner_text("body")[:5000]
                if BLOCK_RE.search(body) and len(body) < 3000:
                    raise RuntimeError("blocked by anti-bot page")
                for item in page.evaluate(EXTRACT_JS):
                    if BRAND_RE.search(item["title"] + " " + item["text"][:300]):
                        related.add(clean_url(item["href"]))
                    lst = classify(item, site)
                    if lst:
                        found.setdefault(clean_url(lst["url"]), lst)
                errors = []
                break
            except Exception as e:
                errors = [f"{type(e).__name__}: {str(e).splitlines()[0][:150]}"]
                if attempt == 1:
                    time.sleep(5)
        if errors:
            break  # site unreachable; don't hammer it with more terms
    if errors:
        raise RuntimeError(errors[0])
    return found, len(related)


def priority(lst):
    used = lst["condition"] == "Used"
    return (0 if used and lst["tbilisi"] else 1 if used else 2,
            lst["price"] if lst["price"] is not None else 10**9)


def fmt(lst, reason):
    e = html.escape
    if lst["price"] is None:
        price = "not shown in listing"
    elif lst["price_shown_with_currency"]:
        price = f"{lst['price']:,} GEL"
    else:
        price = f"{lst['price']:,} (shown without currency – assumed GEL)"
    loc = "Tbilisi" if lst["tbilisi"] else "not stated"
    return (f"<b>{e(reason)}: WalkingPad {lst['model']}</b>\n"
            f"💰 {e(price)}\n"
            f"📦 Condition: {e(lst['condition'])}\n"
            f"📍 Location: {loc}\n"
            f"🏪 {e(lst['site'])}\n"
            f"📝 {e(lst['title'])}\n"
            f"🔗 {e(lst['url'])}")


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        log("[telegram not configured] " + text.replace("\n", " | "))
        return False
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": "true"}, timeout=30)
    if not r.ok:
        log(f"Telegram error {r.status_code}: {r.text[:300]}")
    return r.ok


def find_chat_id():
    """Helper for setup: prints the chat ID of whoever messaged the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log("TELEGRAM_BOT_TOKEN secret is missing.")
        return 1
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
    if not r.get("ok"):
        log(f"Telegram says: {r}")
        return 1
    ids = {u["message"]["chat"]["id"] for u in r["result"] if "message" in u}
    if not ids:
        log("No messages found. Open your bot in Telegram, send it 'hi', then run this again.")
        return 1
    for i in ids:
        log(f"YOUR CHAT ID: {i}")
    return 0


def load_env_file(path=".env"):
    """On the Mac, Telegram details live in a local .env file instead of GitHub secrets."""
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            k, _, v = line.strip().partition("=")
            if k and v:
                os.environ.setdefault(k, v.strip().strip('"'))


def main():
    load_env_file()
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "find-chat-id":
        return find_chat_id()
    if mode == "test-telegram":
        ok = send_telegram("✅ WalkingPad tracker is connected. You'll get alerts here.")
        log("Test message sent." if ok else "Test message FAILED – check the secrets.")
        return 0 if ok else 1

    sites = [s for s in SITES if s.get("where", "github") == WHERE]
    state = {"listings": {}}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
    if (WHERE == "home" and mode != "force" and not state.get("last_failed_sites")
            and state.get("last_run", "")[:10] == now().date().isoformat()):
        log("Already checked today.")
        return 0
    known = state.setdefault("listings", {})
    first_run = not known

    results, failed, unsure = {}, {}, []
    with sync_playwright() as p:
        if WHERE == "home":
            # Your own Google Chrome, visible on screen, on your home internet.
            try:
                browser = p.chromium.launch(channel="chrome", headless=False)
            except Exception:
                browser = p.chromium.launch(headless=False)
            ctx = browser.new_context(locale="ka-GE")
        else:
            browser = p.chromium.launch()
            ctx = browser.new_context(
                locale="ka-GE", viewport={"width": 1366, "height": 2000},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"))
        page = ctx.new_page()
        for site in sites:
            try:
                found, related = scrape_site(page, site)
                results.update(found)
                log(f"OK   {site['name']}: {len(found)} Z1/C2 listing(s), "
                    f"{related} WalkingPad-related link(s) on the results page")
                if related == 0:
                    unsure.append(site["name"])
            except Exception as e:
                failed[site["name"]] = str(e)
                log(f"FAIL {site['name']}: {e}")
        browser.close()

    ts = now()
    alerts = []
    for key, lst in results.items():
        old = known.get(key)
        if old is None:
            if lst["in_stock"]:
                alerts.append(("New listing", lst))
        else:
            days_gone = (ts - datetime.fromisoformat(old["last_seen"])).days
            if lst["in_stock"] and not old.get("in_stock", True):
                alerts.append(("Back in stock", lst))
            elif lst["in_stock"] and days_gone >= RELIST_AFTER_DAYS:
                alerts.append(("Available again", lst))
            elif (lst["in_stock"] and lst["price"] and old.get("price")
                  and lst["price"] <= old["price"] * (1 - PRICE_DROP_PCT / 100)):
                alerts.append((f"Price drop (was {old['price']:,})", lst))
        known[key] = {**lst, "first_seen": (old or {}).get("first_seen", ts.isoformat()),
                      "last_seen": ts.isoformat()}

    alerts.sort(key=lambda a: priority(a[1]))
    if first_run and alerts:
        send_telegram(f"👋 First check done. Found {len(alerts)} current WalkingPad Z1/C2 "
                      "listing(s). Cheapest used listings in Tbilisi come first.")
    for reason, lst in alerts[:MAX_MESSAGES_PER_RUN]:
        send_telegram(fmt(lst, reason))
        time.sleep(1)
    if len(alerts) > MAX_MESSAGES_PER_RUN:
        send_telegram(f"…and {len(alerts) - MAX_MESSAGES_PER_RUN} more.")

    if failed:
        lines = "\n".join(f"• {html.escape(n)} – {html.escape(r)}" for n, r in failed.items())
        send_telegram(f"⚠️ Could not check {len(failed)} of {len(sites)} site(s) today:\n{lines}")

    if unsure:
        log("Note: no WalkingPad items at all on: " + ", ".join(unsure) +
            ". Either none are listed, or that site's search address needs fixing.")
    log(f"\nSummary: {len(results)} listing(s) seen, {len(alerts)} alert(s), "
        f"{len(failed)} site(s) failed.")
    state["last_run"] = ts.isoformat()
    state["last_failed_sites"] = failed
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
