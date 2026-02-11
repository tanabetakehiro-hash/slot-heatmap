import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from urllib.request import Request
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor

from bs4 import BeautifulSoup

OUT_DIR = Path("data/daily")
OUT_DIR.mkdir(parents=True, exist_ok=True)

NEWS_URL = "https://reitoweb.com/b_moba/doc/news.php?h=2&anchor=machine"
MACHINE4_URL = "https://reitoweb.com/b_moba/doc/machine4.php"

H = "2"
T = "29"  # 1000/47枚S

CJ = CookieJar()
OPENER = build_opener(HTTPCookieProcessor(CJ))


def http_get(url: str, timeout=30) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with OPENER.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def http_post_machine4(payload: dict, referer: str, timeout=30) -> dict:
    body = urlencode(payload).encode("utf-8")
    req = Request(
        MACHINE4_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
            "Origin": "https://reitoweb.com",
        },
        method="POST",
    )
    with OPENER.open(req, timeout=timeout) as r:
        txt = r.read().decode("utf-8", errors="ignore").strip()
    return json.loads(txt)


def to_int(x):
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            if str(x) == "nan":
                return None
            return int(x)
        s = str(x).replace(",", "").strip()
        if s == "" or s == "-":
            return None
        return int(float(s))
    except:
        return None


def get_data_links(news_html: str) -> list[str]:
    soup = BeautifulSoup(news_html, "lxml")
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "data.php" not in href:
            continue
        full = urljoin(NEWS_URL, href)
        qs = parse_qs(urlparse(full).query)
        if qs.get("t", [""])[0] != T:
            continue
        links.append(full)

    seen = set()
    out = []
    for u in links:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def extract_units_from_data_html(data_html: str, base_url: str) -> list[dict]:
    """
    data.php のHTMLから、台ごとの基本データ(BB/RB/ART/total_start/max_medals)を拾う。
    台番号は machine.php?...&n=XXXX のリンクから取る（文字化けしない）。
    """
    soup = BeautifulSoup(data_html, "lxml")

    # 機種名（h3）
    h3 = soup.select_one("h3")
    machine_name = h3.get_text(strip=True) if h3 else "UNKNOWN"

    units = []

    # data.php は台ごとにまとまったブロックになってることが多いので、
    # machine.phpリンクを起点にして、近い親要素から数字を拾う戦略
    for a in soup.select('a[href*="machine.php"]'):
        href = a.get("href", "")
        full = urljoin(base_url, href)
        qs = parse_qs(urlparse(full).query)
        n = qs.get("n", [""])[0]
        if not (n and n.isdigit() and 3 <= len(n) <= 4):
            continue
        machine_id = n.zfill(4)

        # 台ブロック探索（リンクの親付近のテキストから数値を拾う）
        block = a.parent
        for _ in range(5):
            if block is None:
                break
            text = block.get_text(" ", strip=True)
            # BB/RB/AT・ART などが近くに入っていそうなら採用
            if ("BB" in text and "RB" in text) or ("累計" in text) or ("最大持玉" in text):
                break
            block = block.parent

        text = block.get_text(" ", strip=True) if block else a.get_text(" ", strip=True)

        # BB/RB/ART/累計/最大持玉 をざっくり正規表現で拾う（多少崩れても耐える）
        # ※表記揺れがあるので “数字”を優先して拾う
        bb = rb = art = total_start = max_medals = None

        m1 = re.search(r"BB\s*([0-9,]+)", text)
        m2 = re.search(r"RB\s*([0-9,]+)", text)
        m3 = re.search(r"(AT|ART|AT・ART)\s*([0-9,]+)", text)
        m4 = re.search(r"(累計スタート|累計)\s*([0-9,]+)", text)
        m5 = re.search(r"(最大持玉)\s*([0-9,]+)", text)

        if m1:
            bb = to_int(m1.group(1))
        if m2:
            rb = to_int(m2.group(1))
        if m3:
            art = to_int(m3.group(2))
        if m4:
            total_start = to_int(m4.group(2))
        if m5:
            max_medals = to_int(m5.group(2))

        units.append(
            {
                "machine_id": machine_id,
                "machine_name": machine_name,
                "bb": bb,
                "rb": rb,
                "art": art,
                "total_start": total_start,
                "max_medals": max_medals,
            }
        )

    # 重複除去（同じ台番号が複数拾われるケース対策）
    seen = set()
    out = []
    for u in units:
        key = u["machine_id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(u)

    return out


def extract_last_diff_from_dataarray(arr) -> int | None:
    if not isinstance(arr, dict) or not arr:
        return None
    keys = []
    for k in arr.keys():
        try:
            keys.append(int(k))
        except:
            pass
    if not keys:
        return None
    last_k = str(max(keys))
    return to_int(arr.get(last_k))


def fetch_machine4_for_unit(m: str, n: str, referer_machine_php: str, retry=2) -> dict | None:
    payload = {"h": H, "t": T, "m": m, "n": n}
    for _ in range(retry + 1):
        try:
            j = http_post_machine4(payload, referer=referer_machine_php, timeout=30)
            if not isinstance(j, dict):
                time.sleep(0.5)
                continue
            if j.get("Result") is False:
                time.sleep(0.5)
                continue
            data = j.get("Data") or {}
            # サービス側エラー
            if isinstance(data, dict) and data.get("status") == "error":
                return None
            return data
        except Exception:
            time.sleep(0.5)
    return None


def main():
    today = date.today().isoformat()
    out_path = OUT_DIR / f"{today}.json"

    print("OPEN:", NEWS_URL)
    news_html = http_get(NEWS_URL)
    links = get_data_links(news_html)
    print(f"LINKS: {len(links)} (filtered t={T})")

    all_rows = []
    filled_diff_total = 0
    skipped_machine4_total = 0

    for idx, data_url in enumerate(links, start=1):
        qs = parse_qs(urlparse(data_url).query)
        m = qs.get("m", [""])[0]
        if not m:
            print(f"[{idx}/{len(links)}] skip (no m) url={data_url}")
            continue

        try:
            data_html = http_get(data_url)
        except Exception as e:
            print(f"[{idx}/{len(links)}] GET failed: {e} url={data_url}")
            continue

        units = extract_units_from_data_html(data_html, data_url)
        if not units:
            dbg = Path("data") / "debug"
            dbg.mkdir(parents=True, exist_ok=True)
            (dbg / f"data_{m}.html").write_text(data_html, encoding="utf-8", errors="ignore")
            print(f"[{idx}/{len(links)}] units=0 (saved debug html) url={data_url}")
            continue

        units_here = 0
        filled_here = 0
        skipped_here = 0

        for u in units:
            units_here += 1
            n = u["machine_id"]
            machine_php_url = f"https://reitoweb.com/b_moba/doc/machine.php?h={H}&t={T}&m={m}&n={n}"

            # ★まず data.php 由来の基本データで1行作る
            item = {
                "machine_id": n,
                "machine_name": u["machine_name"],
                "bb": u["bb"],
                "rb": u["rb"],
                "art": u["art"],
                "total_start": u["total_start"],
                "max_medals": u["max_medals"],
                "diff_medals": None,  # 取れたら後で入れる
                "date": today,
                "source_url": data_url,
                "m": m,
            }

            # ★次に machine4 が取れたら diff を上書き
            data = fetch_machine4_for_unit(m, n, referer_machine_php=machine_php_url)
            if not data:
                skipped_here += 1
                skipped_machine4_total += 1
                all_rows.append(item)
                time.sleep(0.1)
                continue

            diff = extract_last_diff_from_dataarray(data.get("dataArray"))
            item["diff_medals"] = diff

            # machine4 側に機種名や最大持玉が入っていれば上書き（あれば精度UP）
            if data.get("machineName"):
                item["machine_name"] = data.get("machineName")
            if data.get("max") is not None:
                item["max_medals"] = to_int(data.get("max"))

            if item["diff_medals"] is not None:
                filled_here += 1
                filled_diff_total += 1

            all_rows.append(item)
            time.sleep(0.1)

        print(
            f"[{idx}/{len(links)}] units={units_here} filled_diff={filled_here} "
            f"skipped_machine4={skipped_here} url={data_url}"
        )

    out_path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Saved: {out_path} ({len(all_rows)} records) filled_diff_total={filled_diff_total} "
        f"skipped_machine4_total={skipped_machine4_total}"
    )


if __name__ == "__main__":
    main()
