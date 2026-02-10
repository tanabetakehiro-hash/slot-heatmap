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

# 1000／47枚S（スロット）だけに限定（URLの t=29 が該当）
SLOT_T_VALUE = "29"

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
    """
    news.php から data.php へのリンクを集める
    ★1000／47枚S（t=29）だけに絞る
    """
    soup = BeautifulSoup(html, "lxml")
    links = []

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "doc/data.php" not in href:
            continue

        # 絶対URL化
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = BASE + href
        else:
            url = BASE + "/b_moba/" + href

        # ★ここで t=29 のみ残す（スロット1000/47枚S）
        q = parse_qs(urlparse(url).query)
        t = (q.get("t") or [None])[0]
        if t != SLOT_T_VALUE:
            continue

        links.append(url)

    # 重複削除（順序維持）
    return list(dict.fromkeys(links))


def parse_data_php(html: str):
    """
    data.php は文章レイアウト例:
      ##### 0729 番台
      BB 15回 ／ RB 22回 ／ AT・ART 0回
      最大持玉 725枚

    表記ゆれ対応:
      番台/台番/台番号
      AT・ART / AT･ART / AT/ART / AT／ART / "AT ART"
    """
    soup = BeautifulSoup(html, "lxml")

    machine_name = "UNKNOWN"
    h3 = soup.select_one("h3")
    if h3:
        machine_name = h3.get_text(strip=True)

    text = soup.get_text("\n", strip=True)

    # 番台表記ゆれ対応
    matches = list(re.finditer(r"(\d{3,4})\s*(番台|台番|台番号)", text))
    items = []

    for i, m in enumerate(matches):
        machine_id = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        bb = rb = art = None

        # ステータス行の表記ゆれ対応
        m_stats = re.search(
            r"BB\s*(\d+)回.*RB\s*(\d+)回.*AT[・･/／ ]?ART\s*(\d+)回",
            block
        )
        if m_stats:
            bb = to_int(m_stats.group(1))
            rb = to_int(m_stats.group(2))
            art = to_int(m_stats.group(3))
        else:
            # もう少し緩め（区切りが変な場合）
            m_bb = re.search(r"BB\s*(\d+)回", block)
            m_rb = re.search(r"RB\s*(\d+)回", block)
            m_art = re.search(r"AT[・･/／ ]?ART\s*(\d+)回", block)
            if m_bb:
                bb = to_int(m_bb.group(1))
            if m_rb:
                rb = to_int(m_rb.group(1))
            if m_art:
                art = to_int(m_art.group(1))

        # 最大持玉の表記ゆれ対応（「最大持玉」「最大持玉数」など）
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
    """
    machine4.php に POST して JSON を取得
    POST_DATA: {"h":"2","t":"29","m":"99119916","n":"0771"}
    """
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
    """
    total_start: Data.data[0].dTotalStart
    diff_medals: Data.dataArray の
      - dTotalStartキーがあればその値（最終差枚として扱う）
      - なければキー最大（最新点）の値
    """
    d = (machine4_json or {}).get("Data", {})
    dd = d.get("data", [])

    total_start = None
    if isinstance(dd, list) and dd and isinstance(dd[0], dict):
        total_start = dd[0].get("dTotalStart")

    data_array = d.get("dataArray")
    diff_medals = None

    if isinstance(data_array, dict) and data_array:
        # まず total_start の点を優先
        if total_start is not None:
            try:
                k = str(int(total_start))
                if k in data_array:
                    diff_medals = data_array.get(k)
            except:
                pass

        # 無ければ最新点（キー最大）
        if diff_medals is None:
            try:
                last_key = max(data_array.keys(), key=lambda x: int(x))
                diff_medals = data_array.get(last_key)
            except:
                pass

    return to_int(total_start), to_int(diff_medals)


def main():
    today = date.today().isoformat()
    out_path = OUT_DIR / f"{today}.json"

    zero_urls = []
    m4_fail = 0
    total_links = 0
    total_rows = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("OPEN:", START_URL)
        page.goto(START_URL, wait_until="networkidle")

        # 一覧がスクロールで追加される場合に備えて、最下部までスクロール
        last_h = 0
        for _ in range(25):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            h = page.evaluate("document.body.scrollHeight")
            if h == last_h:
                break
            last_h = h

        links = get_machine_links(page.content())
        total_links = len(links)
        print("LINKS:", total_links, f"(filtered t={SLOT_T_VALUE})")

        all_records = []

        # ★全リンクを回す（スロットのみ）
        for i, data_url in enumerate(links, start=1):
            page.goto(data_url, wait_until="networkidle")
            items = parse_data_php(page.content())

            if len(items) == 0:
                zero_urls.append(data_url)
                print(f"!! ZERO rows url={data_url}")

            q = extract_query(data_url)
            h, t, m = q["h"], q["t"], q["m"]

            filled = 0
            for it in items:
                it["date"] = today
                it["source_url"] = data_url
                it["m"] = m  # デバッグ用（残してOK）

                try:
                    # t は必ず 29（スロット）を送る
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
            print(f"[{i}/{total_links}] rows={len(items)} filled={filled} url={data_url}")
            sleep(0.6)

        browser.close()

    out_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path} ({len(all_records)} records)")
    print(f"Summary: LINKS={total_links} total_rows={total_rows} ZERO_URLS={len(zero_urls)} M4_fail={m4_fail}")

    if zero_urls:
        print("\nFirst 20 ZERO rows URLs:")
        for u in zero_urls[:20]:
            print("  ", u)


if __name__ == "__main__":
    main()
