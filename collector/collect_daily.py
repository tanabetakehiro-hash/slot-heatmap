import json
import re
from datetime import date
from pathlib import Path
from time import sleep
from urllib.parse import urlparse, parse_qs
import urllib.request

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://reitoweb.com"
START_URL = "https://reitoweb.com/b_moba/doc/news.php?h=2&anchor=machine"
MACHINE4_ENDPOINT = "https://reitoweb.com/b_moba/doc/machine4.php"

SLOT_T_VALUE = "29"  # 1000/47枚S

OUT_DIR = Path("data/daily")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def to_int(s: str):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("枚", "").strip()
    if s in ("", "-", "—"):
        return None
    try:
        return int(s)
    except:
        return None


def extract_query(url: str):
    q = parse_qs(urlparse(url).query)

    def get1(k, default=None):
        v = q.get(k)
        return v[0] if v else default

    return {
        "h": get1("h", "2"),
        "t": get1("t"),
        "m": get1("m"),
        "d": get1("d"),
        "n": get1("n"),
    }


def get_machine_links(html: str):
    """news.php から data.php へのリンクを集め、t=29のみ残す"""
    soup = BeautifulSoup(html, "lxml")
    links = []

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "doc/data.php" not in href:
            continue

        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = BASE + href
        else:
            url = BASE + "/b_moba/" + href

        q = parse_qs(urlparse(url).query)
        t = (q.get("t") or [None])[0]
        if t != SLOT_T_VALUE:
            continue

        links.append(url)

    return list(dict.fromkeys(links))


def parse_data_php(html: str):
    soup = BeautifulSoup(html, "lxml")

    machine_name = "UNKNOWN"
    h3 = soup.select_one("h3")
    if h3:
        machine_name = h3.get_text(strip=True)

    text = soup.get_text("\n", strip=True)

    matches = list(re.finditer(r"(\d{3,4})\s*(番台|台番|台番号)", text))
    items = []

    for i, m in enumerate(matches):
        machine_id = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        bb = rb = art = None
        m_stats = re.search(
            r"BB\s*(\d+)回.*RB\s*(\d+)回.*AT[・･/／ ]?ART\s*(\d+)回",
            block
        )
        if m_stats:
            bb = to_int(m_stats.group(1))
            rb = to_int(m_stats.group(2))
            art = to_int(m_stats.group(3))
        else:
            m_bb = re.search(r"BB\s*(\d+)回", block)
            m_rb = re.search(r"RB\s*(\d+)回", block)
            m_art = re.search(r"AT[・･/／ ]?ART\s*(\d+)回", block)
            if m_bb:
                bb = to_int(m_bb.group(1))
            if m_rb:
                rb = to_int(m_rb.group(1))
            if m_art:
                art = to_int(m_art.group(1))

        max_medals = None
        m_max = re.search(r"最大持玉(?:数)?\s*([0-9,]+)\s*枚", block)
        if m_max:
            max_medals = to_int(m_max.group(1))

        items.append(
            {
                "machine_id": machine_id,
                "machine_name": machine_name,
                "bb": bb,
                "rb": rb,
                "art": art,
                "total_start": None,
                "max_medals": max_medals,
                "diff_medals": None,
            }
        )

    return items


def post_machine4(h: str, t: str, m: str, n: str):
    payload = {"h": str(h), "t": str(t), "m": str(m), "n": str(n)}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        MACHINE4_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def extract_total_and_diff(machine4_json: dict):
    d = (machine4_json or {}).get("Data", {})
    dd = d.get("data", [])

    total_start = None
    if isinstance(dd, list) and dd and isinstance(dd[0], dict):
        total_start = dd[0].get("dTotalStart")

    data_array = d.get("dataArray")
    diff_medals = None

    if isinstance(data_array, dict) and data_array:
        if total_start is not None:
            try:
                k = str(int(total_start))
                if k in data_array:
                    diff_medals = data_array.get(k)
            except:
                pass

        if diff_medals is None:
            try:
                last_key = max(data_array.keys(), key=lambda x: int(x))
                diff_medals = data_array.get(last_key)
            except:
                pass

    return to_int(total_start), to_int(diff_medals)


def safe_goto(page, url: str, label: str = "") -> bool:
    """
    Actionsで止まりやすい networkidle を使わず、タイムアウトしてもスキップして続行。
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        # ちょい待ち（DOM整うまで）
        page.wait_for_timeout(500)
        return True
    except Exception as e:
        print(f"!! GOTO FAIL {label} url={url} err={e}")
        return False


def main():
    today = date.today().isoformat()
    out_path = OUT_DIR / f"{today}.json"

    skipped_urls = []
    m4_fail = 0
    total_rows = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("OPEN:", START_URL)
        if not safe_goto(page, START_URL, "START"):
            raise SystemExit("Cannot open START_URL")

        # スクロールで追加される場合に備えて最下部まで
        last_h = 0
        for _ in range(25):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            h = page.evaluate("document.body.scrollHeight")
            if h == last_h:
                break
            last_h = h

        links = get_machine_links(page.content())
        print(f"LINKS: {len(links)} (filtered t={SLOT_T_VALUE})")

        all_records = []

        for i, data_url in enumerate(links, start=1):
            ok = safe_goto(page, data_url, f"DATA {i}/{len(links)}")
            if not ok:
                skipped_urls.append(data_url)
                continue

            items = parse_data_php(page.content())
            q = extract_query(data_url)
            h, m = q["h"], q["m"]

            filled = 0
            for it in items:
                it["date"] = today
                it["source_url"] = data_url
                it["m"] = m

                try:
                    m4 = post_machine4(h, SLOT_T_VALUE, m, it["machine_id"].zfill(4))
                    total_start, diff_medals = extract_total_and_diff(m4)
                    it["total_start"] = total_start
                    it["diff_medals"] = diff_medals
                    filled += 1
                except:
                    m4_fail += 1
                    it["total_start"] = None
                    it["diff_medals"] = None

                all_records.append(it)

            total_rows += len(items)
            print(f"[{i}/{len(links)}] rows={len(items)} filled={filled} url={data_url}")
            sleep(0.4)

        browser.close()

    out_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path} ({len(all_records)} records)")
    print(f"Summary: LINKS={len(links)} total_rows={total_rows} SKIPPED_URLS={len(skipped_urls)} M4_fail={m4_fail}")
    if skipped_urls:
        print("First 10 skipped URLs:")
        for u in skipped_urls[:10]:
            print("  ", u)


if __name__ == "__main__":
    main()