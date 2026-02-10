import json
import re
from datetime import date
from pathlib import Path
from time import sleep

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://reitoweb.com"
START_URL = "https://reitoweb.com/b_moba/doc/news.php?h=2&anchor=machine"

OUT_DIR = Path("data/daily")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def to_int(s: str):
    if s is None:
        return None
    s = s.replace(",", "").replace("枚", "").strip()
    if s in ("", "-", "—"):
        return None
    try:
        return int(s)
    except:
        return None

def get_machine_links(html: str):
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "doc/data.php" in href:
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = BASE + href
            else:
                url = BASE + "/b_moba/" + href
            links.append(url)
    return list(dict.fromkeys(links))

def parse_data_php(html: str):
    """
    data.php はこういう構造：
      ##### 0729 番台
      BB 18回 ／ RB 15回 ／ AT・ART 0回
      最大持玉 1932枚
    （実ページ確認済み）:contentReference[oaicite:2]{index=2}
    """
    soup = BeautifulSoup(html, "lxml")

    machine_name = "UNKNOWN"
    h3 = soup.select_one("h3")
    if h3:
        machine_name = h3.get_text(strip=True)

    text = soup.get_text("\n", strip=True)

    matches = list(re.finditer(r"(\d{3,4})\s*番台", text))
    items = []
    for i, m in enumerate(matches):
        machine_id = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        bb = rb = art = None
        m_stats = re.search(r"BB\s*(\d+)回.*RB\s*(\d+)回.*AT・ART\s*(\d+)回", block)
        if m_stats:
            bb = to_int(m_stats.group(1))
            rb = to_int(m_stats.group(2))
            art = to_int(m_stats.group(3))

        max_medals = None
        m_max = re.search(r"最大持玉\s*([0-9,]+)\s*枚", block)
        if m_max:
            max_medals = to_int(m_max.group(1))

        items.append({
            "machine_id": machine_id,
            "machine_name": machine_name,
            "bb": bb,
            "rb": rb,
            "art": art,
            "total_start": None,   # 次段階(machine.php/API)で追加
            "max_medals": max_medals,
            "diff_medals": None,   # 次段階(グラフ)で追加
        })
    return items

def main():
    today = date.today().isoformat()
    out_path = OUT_DIR / f"{today}.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("OPEN:", START_URL)
        page.goto(START_URL, wait_until="networkidle")
        links = get_machine_links(page.content())
        print("LINKS:", len(links))

        all_records = []
        for i, url in enumerate(links[:30], start=1):  # 最初は30機種で安全運転
            page.goto(url, wait_until="networkidle")
            items = parse_data_php(page.content())
            for it in items:
                it["date"] = today
                it["source_url"] = url
                all_records.append(it)
            print(f"[{i}/{min(len(links),30)}] rows={len(items)}")
            sleep(1.0)

        browser.close()

    out_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path} ({len(all_records)} records)")

if __name__ == "__main__":
    main()