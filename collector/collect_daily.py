# collector/collect_daily.py
import os
import re
import json
import time
import random
import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

NEWS_URL = "https://reitoweb.com/b_moba/doc/news.php?h=2&anchor=machine"

H = "2"
T_SLOT = "29"  # 1000/47枚S
BASE = "https://reitoweb.com"
MACHINE4_URL = f"{BASE}/b_moba/doc/machine4.php"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123 Safari/537.36"
)

JST = ZoneInfo("Asia/Tokyo")


# ----------------------------
# Utils
# ----------------------------
def ensure_dir(path: str) -> None:
    if not path:
        return
    os.makedirs(path, exist_ok=True)


def today_jst_str() -> str:
    return datetime.datetime.now(JST).date().strftime("%Y-%m-%d")


def now_ts_str() -> str:
    return datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def log_line(path: str, msg: str) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")


def safe_int(x: Any) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, (int, float)):
            return int(x)
        s = str(x).strip()
        if s == "" or s.lower() in ("null", "none") or s == "-":
            return None
        s = s.replace(",", "")
        return int(float(s))
    except Exception:
        return None


def extract_m_from_url(url: str) -> str:
    m = re.search(r"[?&]m=(\d+)", url)
    return m.group(1) if m else ""


def absolutize_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE + href


def zfill_n(n_value: str) -> str:
    s = str(n_value).strip()
    if s == "":
        return ""
    m = re.search(r"\d+", s)
    if not m:
        return ""
    return m.group(0).zfill(4)


def n_to_int(n4: str) -> int:
    n4 = zfill_n(n4)
    if not n4:
        return 0
    try:
        return int(n4)
    except Exception:
        return 0


def is_smart_slot(machine_name: str) -> bool:
    s = (machine_name or "").strip()
    return s.startswith("L") or s.startswith("Ｌ")


def rand_wait(a: float = 0.15, b: float = 0.45) -> None:
    time.sleep(random.uniform(a, b))


# ----------------------------
# Fetch (requests)
# ----------------------------
def fetch_html(
    session: requests.Session,
    url: str,
    referer: str = "",
    timeout: int = 25,
    retries: int = 3,
) -> Tuple[Optional[str], Optional[str]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer

    last_reason = None
    for i in range(retries):
        try:
            r = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if r.status_code != 200:
                last_reason = f"status={r.status_code}"
                time.sleep(0.5 * (i + 1))
                continue
            return r.text, None
        except Exception as e:
            last_reason = f"exception:{type(e).__name__}:{e}"
            time.sleep(0.5 * (i + 1))
    return None, last_reason


# ----------------------------
# Parse news.php -> data.php links
# ----------------------------
def get_machine_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if "data.php" in href and "t=29" in href and "m=" in href:
            links.append(absolutize_url(href))

    seen = set()
    out = []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ----------------------------
# data.php parse
# ----------------------------
def parse_units_from_data_page(
    html: str,
    source_url: str,
    date_str: str,
    m_value: str,
) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")

    machine_name = ""
    for sel in ["h1", "h2", "h3", ".ttl", ".title", ".machine", ".midashi"]:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) >= 2 and "レイト" not in txt and "平和島" not in txt:
                machine_name = txt
                break

    text_all = soup.get_text("\n", strip=True)

    raw_candidates = re.findall(r"\b(\d{3,4})\s*番台\b", text_all)
    seen = set()
    units: List[Dict[str, Any]] = []

    for raw_n in raw_candidates:
        n_value = zfill_n(raw_n)
        if not n_value or n_value in seen:
            continue
        seen.add(n_value)

        detail_url = ""
        try:
            n3 = str(int(n_value))
        except Exception:
            n3 = n_value.lstrip("0") or n_value

        a = (
            soup.select_one(f'a[href*="machine.php"][href*="n={n_value}"]')
            or soup.select_one(f'a[href*="machine.php"][href*="n={n3}"]')
        )
        if a and a.get("href"):
            detail_url = absolutize_url(a.get("href"))

        bb = rb = art = 0
        m_line = re.search(
            rf"{re.escape(raw_n)}\s*番台.*?"
            r"(?:BB|ＢＢ)\s*(\d+)回.*?"
            r"(?:RB|ＲＢ)\s*(\d+)回.*?"
            r"(?:AT・ART|AT/ART|ＡＴ・ＡＲＴ)\s*(\d+)回",
            text_all,
            flags=re.DOTALL,
        )
        if m_line:
            bb = safe_int(m_line.group(1)) or 0
            rb = safe_int(m_line.group(2)) or 0
            art = safe_int(m_line.group(3)) or 0

        max_medals = None
        m_max = re.search(
            rf"{re.escape(raw_n)}\s*番台.*?最大持玉\s*([-\d,]+)枚",
            text_all,
            flags=re.DOTALL,
        )
        if m_max:
            max_medals = safe_int(m_max.group(1))

        units.append(
            {
                "machine_id": n_value,
                "machine_name": machine_name,
                "bb": bb,
                "rb": rb,
                "art": art,
                "total_start": None,
                "max_medals": max_medals,
                "diff_medals": None,
                "diff_reason": "",
                "date": date_str,
                "source_url": source_url,
                "detail_url": detail_url,
                "m": m_value,
                "is_smart": is_smart_slot(machine_name),
            }
        )

    return units


# ----------------------------
# cookies -> playwright
# ----------------------------
def transfer_cookies_to_playwright(session: requests.Session) -> List[Dict[str, Any]]:
    cookies: List[Dict[str, Any]] = []
    for c in session.cookies:
        cookies.append(
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain if c.domain else "reitoweb.com",
                "path": c.path if c.path else "/",
            }
        )
    return cookies


# ----------------------------
# machine.php rendered text -> stats
# ----------------------------
def parse_machine_stats_from_rendered_text(text: str) -> Dict[str, Optional[int]]:
    if not text:
        return {
            "bb": None,
            "rb": None,
            "art": None,
            "max_medals": None,
            "total_start": None,
            "diff_medals": None,
        }

    norm = text.replace("\u3000", " ")
    norm = norm.replace("\t", " ")
    norm = re.sub(r"[ ]{2,}", " ", norm)
    norm = re.sub(r"\r\n|\r", "\n", norm)

    def pick(patterns: List[str]) -> Optional[int]:
        for pat in patterns:
            m = re.search(pat, norm, flags=re.MULTILINE)
            if m:
                return safe_int(m.group(1))
        return None

    bb = pick([r"\bBB\b(?!確率)\s*([0-9]{1,6})\b", r"BB回数\s*([0-9]{1,6})\b"])
    rb = pick([r"\bRB\b(?!確率)\s*([0-9]{1,6})\b", r"RB回数\s*([0-9]{1,6})\b"])
    art = pick([r"(?:AT・ART|AT/ART|ＡＴ・ＡＲＴ)\s*([0-9]{1,6})\b"])

    total_start = pick([r"累計スタート\s*([0-9]{1,9})\b", r"(?:総回転|回転数|スタート)\s*([0-9]{1,9})\b"])
    max_medals = pick([r"最大持玉\s*([-0-9,]{1,12})\b", r"(?:最大獲得|最大出玉)\s*([-0-9,]{1,12})\b"])
    diff_medals = pick([r"(?:差枚|差メダル|差枚数|差ﾒﾀﾞﾙ|差玉|差玉数)\s*([-0-9,]{1,12})\b"])

    return {
        "bb": bb,
        "rb": rb,
        "art": art,
        "max_medals": max_medals,
        "total_start": total_start,
        "diff_medals": diff_medals,
    }


# ----------------------------
# machine4.php JSON helpers
# ----------------------------
def extract_json_fragment(text: str) -> Optional[str]:
    if not text:
        return None
    s = text.lstrip()
    if s.startswith("{") or s.startswith("["):
        return s
    i = s.find("{")
    if i == -1:
        return None
    cand = s[i:]
    j = cand.rfind("}")
    if j == -1:
        return None
    return cand[: j + 1]


def fetch_machine4_json_pw(
    context,
    m_value: str,
    n4: str,
    d_value: int,
    timeout_ms: int = 25000,
) -> Tuple[Optional[Dict[str, Any]], str, str]:
    n4 = zfill_n(n4)
    n_int = n_to_int(n4)
    n_str = str(n_int)
    n4_str = n4

    n_variants: List[Any] = [n_int, n_str, n4_str]
    referer_variants: List[str] = [
        f"{BASE}/b_moba/doc/machine.php?h={H}&t={T_SLOT}&m={m_value}&n={n_int}",
        f"{BASE}/b_moba/doc/machine.php?h={H}&t={T_SLOT}&m={m_value}&n={n4_str}",
    ]

    last_head = ""
    last_reason = "unknown"

    for ref in referer_variants:
        for n_payload in n_variants:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                "Referer": ref,
                "Origin": BASE,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }

            payload = {
                "h": H,
                "t": int(T_SLOT),
                "m": int(m_value) if str(m_value).isdigit() else m_value,
                "n": n_payload,
                "d": int(d_value),
            }

            try:
                r = context.request.post(MACHINE4_URL, headers=headers, data=payload, timeout=timeout_ms)
                raw = (r.text() or "")
                last_head = raw[:250].replace("\n", "\\n")

                if not r.ok:
                    last_reason = f"status={r.status} n={n_payload}"
                    continue

                frag = extract_json_fragment(raw)
                if frag is None:
                    last_reason = f"not_json n={n_payload} head={last_head}"
                    continue

                try:
                    j = json.loads(frag)
                except Exception as e:
                    last_reason = f"json_decode_error:{type(e).__name__}:{e} n={n_payload} head={last_head}"
                    continue

                return j, "", last_head

            except Exception as e:
                last_reason = f"exception:{type(e).__name__}:{e} n={n_payload}"

    return None, last_reason, last_head


def parse_diff_from_machine4_json(j: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """
    ★強化版：
    - Data.dataArray 以外にも、名称違いの配列/値がある可能性に備える
    """
    if not isinstance(j, dict):
        return None, "not_dict"

    if j.get("Result") is False:
        err = j.get("Error") or {}
        code = err.get("ErrorCode")
        msg = err.get("ErrorMessage")
        return None, f"result_false:{code}:{msg}"

    data = j.get("Data")
    if not isinstance(data, dict):
        return None, "no_Data"

    # まずは時系列配列っぽい候補を広めに探す
    array_candidates = [
        "dataArray",
        "diffArray",
        "graphArray",
        "medalArray",
        "diffMedalArray",
        "differenceArray",
    ]

    for key in array_candidates:
        data_array = data.get(key)
        if isinstance(data_array, dict) and data_array:
            items: List[Tuple[int, int]] = []
            for k, v in data_array.items():
                kk = safe_int(k)
                vv = safe_int(v)
                if kk is None or vv is None:
                    continue
                items.append((kk, vv))
            if items:
                items.sort(key=lambda x: x[0])
                return items[-1][1], f"Data.{key}(last)"

        if isinstance(data_array, list) and data_array:
            # list の場合は末尾が差枚のことが多い（確証はないので保険）
            vv = safe_int(data_array[-1])
            if vv is not None:
                return vv, f"Data.{key}[last]"

    # 単発キーで差枚がある場合
    scalar_candidates = [
        "diff",
        "diffMedals",
        "difference",
        "medalDiff",
        "diffValue",
    ]
    for key in scalar_candidates:
        vv = safe_int(data.get(key))
        if vv is not None:
            return vv, f"Data.{key}"

    return None, "no_diff_in_json"


def parse_total_start_from_machine4_json(j: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """
    machine4.php JSON から「累計スタート（dTotalStart）」を取り出す。

    - ユーザー要望：Data.data の「最初（=当日扱いのことが多い）」の dTotalStart を優先して使う
    """
    if not isinstance(j, dict):
        return None, "not_dict"

    if j.get("Result") is False:
        err = j.get("Error") or {}
        code = err.get("ErrorCode")
        msg = err.get("ErrorMessage")
        return None, f"result_false:{code}:{msg}"

    data = j.get("Data")
    if not isinstance(data, dict):
        return None, "no_Data"

    # 最優先：Data.data[0].dTotalStart
    data_list = data.get("data")
    if isinstance(data_list, list) and data_list:
        first = data_list[0]
        if isinstance(first, dict):
            vv = safe_int(first.get("dTotalStart"))
            if vv is not None:
                return vv, "Data.data[0].dTotalStart"

        # 念のため：最初に見つかった dTotalStart
        for idx, item in enumerate(data_list):
            if not isinstance(item, dict):
                continue
            vv = safe_int(item.get("dTotalStart"))
            if vv is not None:
                return vv, f"Data.data[{idx}].dTotalStart"

    # 予備：Data 直下の候補キー
    scalar_candidates = [
        "dTotalStart",
        "totalStart",
        "TotalStart",
        "total_start",
        "TotalStartValue",
    ]
    for key in scalar_candidates:
        vv = safe_int(data.get(key))
        if vv is not None:
            return vv, f"Data.{key}"

    return None, "no_total_start_in_json"


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    date_str = today_jst_str()

    out_dir = os.path.join("data", "daily")
    debug_dir = os.path.join("data", "debug")
    ensure_dir(out_dir)
    ensure_dir(debug_dir)

    news_fetch_log = os.path.join(debug_dir, "news_fetch_errors.log")
    data_fetch_log = os.path.join(debug_dir, "data_fetch_errors.log")
    data_units_zero_log = os.path.join(debug_dir, "data_units_zero.log")
    mach_fetch_log = os.path.join(debug_dir, "machine_fetch_errors.log")
    mach_parse_log = os.path.join(debug_dir, "machine_parse_errors.log")
    mach_wrong_page_log = os.path.join(debug_dir, "machine_wrong_page.log")

    api_diff_log = os.path.join(debug_dir, "machine_api_diff.log")
    api_json_log = os.path.join(debug_dir, "machine_api_json.log")
    api_total_log = os.path.join(debug_dir, "machine_api_total.log")
    api_json_save_dir = os.path.join(debug_dir, "machine4_json")
    ensure_dir(api_json_save_dir)

    log_line(api_diff_log, f"[{now_ts_str()}] START collect_daily date={date_str}")
    log_line(api_total_log, f"[{now_ts_str()}] START collect_daily date={date_str}")

    print(f"OPEN: {NEWS_URL}")

    # 1) news.php（Playwright）
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)

        try:
            page.goto(NEWS_URL, wait_until="domcontentloaded", timeout=45000)
            news_html = page.content()
        except Exception as e:
            ts = now_ts_str()
            log_line(news_fetch_log, f"[{ts}] news goto fail url={NEWS_URL} err={type(e).__name__}:{e}")
            print("news fetch failed")
            browser.close()
            return

        links = get_machine_links(news_html)
        links = [u for u in links if "t=29" in u]
        print(f"LINKS: {len(links)} (filtered t=29)")
        browser.close()

    # 2) data.php（requests）
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})

    all_units: List[Dict[str, Any]] = []
    skipped_page_total = 0

    for idx, data_url in enumerate(links, start=1):
        m_value = extract_m_from_url(data_url)

        html, reason = fetch_html(s, data_url, referer=NEWS_URL, timeout=25, retries=3)
        if html is None:
            skipped_page_total += 1
            ts = now_ts_str()
            log_line(data_fetch_log, f"[{ts}] data fetch fail url={data_url} msg={reason}")
            print(f"[{idx}/{len(links)}] SKIP page (fetch error) url={data_url}")
            continue

        units = parse_units_from_data_page(html, data_url, date_str, m_value)
        if len(units) == 0:
            ts = now_ts_str()
            head = html[:250].replace("\n", "\\n")
            log_line(data_units_zero_log, f"[{ts}] units=0 m={m_value} url={data_url} head={head}")

        all_units.extend(units)
        print(f"[{idx}/{len(links)}] units={len(units)} url={data_url}")

        rand_wait()

    # 3) machine.php + machine4
    filled_bb = filled_rb = filled_art = 0
    filled_max = filled_total = filled_total_api = filled_diff_text = 0
    filled_diff_api = 0
    skipped_machine_total = 0
    parse_fail_total = 0
    wrong_page_total = 0
    api_miss_total = 0

    def build_fallback_detail_url(m_value: str, n_value: str) -> str:
        n_value = zfill_n(n_value)
        return f"{BASE}/b_moba/doc/machine.php?h={H}&t={T_SLOT}&m={m_value}&n={n_value}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale="ja-JP")

        cookies = transfer_cookies_to_playwright(s)
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception:
                pass

        page = context.new_page()

        # セッション初期化
        try:
            page.goto(NEWS_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(800)
        except Exception:
            pass

        cache: Dict[str, Dict[str, Optional[int]]] = {}
        api_cache: Dict[str, Tuple[Optional[int], str, Optional[int], str]] = {}

        for i, u in enumerate(all_units, start=1):
            m_value = u.get("m", "")
            n_value = u.get("machine_id", "")
            if not m_value or not n_value:
                continue

            url = u.get("detail_url") or build_fallback_detail_url(m_value, n_value)
            if not url:
                continue

            # ---- machine.php parse ----
            if url in cache:
                stats = cache[url]
            else:
                try:
                    rand_wait()
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)

                    n4 = zfill_n(n_value)
                    n3 = str(n_to_int(n_value))
                    try:
                        page.wait_for_function(
                            """(n4,n3) => {
                                const t = document.body ? document.body.innerText : "";
                                if (!t) return false;
                                if (t.includes("{{ machineData")) return false;
                                return t.includes(n4 + " 番台") || t.includes(n3 + " 番台") || t.includes("データ更新時間");
                            }""",
                            arg=[n4, n3],
                            timeout=12000
                        )
                    except Exception:
                        pass

                    rendered_text = page.inner_text("body")
                except Exception as e:
                    skipped_machine_total += 1
                    ts = now_ts_str()
                    log_line(
                        mach_fetch_log,
                        f"[{ts}] machine goto fail m={m_value} n={n_value} url={url} err={type(e).__name__}:{e}",
                    )
                    continue

                stats = parse_machine_stats_from_rendered_text(rendered_text)
                cache[url] = stats

                if all(v is None for v in stats.values()):
                    wrong_page_total += 1
                    ts = now_ts_str()
                    head = rendered_text[:350].replace("\n", "\\n")
                    try:
                        final_url = page.url
                    except Exception:
                        final_url = ""
                    try:
                        title = page.title()
                    except Exception:
                        title = ""
                    log_line(
                        mach_wrong_page_log,
                        f"[{ts}] SUSPICIOUS(no numbers) m={m_value} n={n_value} url={url} "
                        f"final_url={final_url} title={title} stats={stats} head={head}"
                    )

            # 補完
            if u.get("bb") in (None, 0) and stats.get("bb") is not None:
                u["bb"] = stats["bb"] or 0
                filled_bb += 1
            if u.get("rb") in (None, 0) and stats.get("rb") is not None:
                u["rb"] = stats["rb"] or 0
                filled_rb += 1
            if u.get("art") in (None, 0) and stats.get("art") is not None:
                u["art"] = stats["art"] or 0
                filled_art += 1

            if u.get("max_medals") is None and stats.get("max_medals") is not None:
                u["max_medals"] = stats["max_medals"]
                filled_max += 1
            if u.get("total_start") is None and stats.get("total_start") is not None:
                u["total_start"] = stats["total_start"]
                filled_total += 1

            if u.get("diff_medals") is None and stats.get("diff_medals") is not None:
                u["diff_medals"] = stats["diff_medals"]
                u["diff_reason"] = "machine_text"
                filled_diff_text += 1

            # ---- machine4 API diff / total_start fallback ----
            need_diff_api = u.get("diff_medals") is None
            need_total_api = (safe_int(u.get("total_start")) or 0) == 0

            if need_diff_api or need_total_api:
                api_key_base = f"m={m_value}&n={zfill_n(n_value)}"

                got_diff: Optional[int] = None
                got_diff_reason = ""
                last_diff_reason = ""

                got_total: Optional[int] = None
                got_total_reason = ""
                last_total_reason = ""

                got_json_saved = ""

                for d_value in (1, 0, 2):
                    api_key = f"{api_key_base}&d={d_value}"

                    # cache
                    if api_key in api_cache:
                        diff_val, diff_reason, total_val, total_reason = api_cache[api_key]

                        if got_diff is None and diff_val is not None:
                            got_diff, got_diff_reason = diff_val, diff_reason
                        elif diff_reason:
                            last_diff_reason = diff_reason

                        if got_total is None and total_val is not None:
                            got_total, got_total_reason = total_val, total_reason
                        elif total_reason:
                            last_total_reason = total_reason

                        if (not need_diff_api or got_diff is not None) and (not need_total_api or got_total is not None):
                            break
                        continue

                    rand_wait()

                    j, fail_reason, head_api = fetch_machine4_json_pw(context, m_value, zfill_n(n_value), d_value)
                    ts = now_ts_str()

                    if j is None:
                        miss_reason = f"machine4 json fetch failed {fail_reason}"
                        api_cache[api_key] = (None, miss_reason, None, miss_reason)

                        if need_diff_api:
                            log_line(
                                api_diff_log,
                                f"[{ts}] MISS diff m={m_value} n={zfill_n(n_value)} d={d_value} url={url} reason={miss_reason}",
                            )
                            last_diff_reason = miss_reason
                        if need_total_api:
                            log_line(
                                api_total_log,
                                f"[{ts}] MISS total_start m={m_value} n={zfill_n(n_value)} d={d_value} url={url} reason={miss_reason}",
                            )
                            last_total_reason = miss_reason

                        time.sleep(random.uniform(0.2, 0.6))
                        continue

                    top_keys = list(j.keys()) if isinstance(j, dict) else []
                    log_line(api_json_log, f"[{ts}] CAND page={url} json={MACHINE4_URL} d={d_value} top_keys={top_keys}")

                    save_name = f"{date_str}_m{m_value}_n{zfill_n(n_value)}_d{d_value}.json"
                    save_path = os.path.join(api_json_save_dir, save_name)
                    try:
                        with open(save_path, "w", encoding="utf-8") as f:
                            json.dump(j, f, ensure_ascii=False, indent=2)
                        got_json_saved = save_path
                    except Exception:
                        got_json_saved = ""

                    diff_val, diff_reason = parse_diff_from_machine4_json(j)
                    total_val, total_reason = parse_total_start_from_machine4_json(j)
                    api_cache[api_key] = (diff_val, diff_reason, total_val, total_reason)

                    # diff logs / capture
                    if need_diff_api:
                        if diff_val is not None and got_diff is None:
                            got_diff, got_diff_reason = diff_val, diff_reason
                            log_line(
                                api_diff_log,
                                f"[{ts}] HIT diff={diff_val} d={d_value} page={url} json={MACHINE4_URL} path={diff_reason} saved={got_json_saved}",
                            )
                        else:
                            log_line(
                                api_diff_log,
                                f"[{ts}] MISS diff m={m_value} n={zfill_n(n_value)} d={d_value} url={url} reason={diff_reason} saved={got_json_saved}",
                            )
                            if diff_reason:
                                last_diff_reason = diff_reason

                    # total_start logs / capture
                    if need_total_api:
                        if total_val is not None and got_total is None:
                            got_total, got_total_reason = total_val, total_reason
                            log_line(
                                api_total_log,
                                f"[{ts}] HIT total_start={total_val} d={d_value} page={url} json={MACHINE4_URL} path={total_reason} saved={got_json_saved}",
                            )
                        else:
                            log_line(
                                api_total_log,
                                f"[{ts}] MISS total_start m={m_value} n={zfill_n(n_value)} d={d_value} url={url} reason={total_reason} saved={got_json_saved}",
                            )
                            if total_reason:
                                last_total_reason = total_reason

                    if (not need_diff_api or got_diff is not None) and (not need_total_api or got_total is not None):
                        break

                # total_start を API で補完（0 / None のとき）
                if need_total_api and got_total is not None:
                    u["total_start"] = got_total
                    filled_total_api += 1

                # diff_medals を API で補完（None のとき）
                if need_diff_api:
                    final_diff_reason = got_diff_reason or last_diff_reason or "unknown"

                    # no_diff_in_json かつ 当日完全0なら「差枚0」として扱う
                    if got_diff is None and final_diff_reason == "no_diff_in_json":
                        bb0 = (u.get("bb") or 0) == 0
                        rb0 = (u.get("rb") or 0) == 0
                        art0 = (u.get("art") or 0) == 0
                        ts0 = (safe_int(u.get("total_start")) or 0) == 0
                        mx0 = (u.get("max_medals") or 0) == 0
                        if bb0 and rb0 and art0 and ts0 and mx0:
                            u["diff_medals"] = 0
                            u["diff_reason"] = "no_play_or_no_update(diff=0)"
                        else:
                            u["diff_reason"] = final_diff_reason
                            api_miss_total += 1
                    elif got_diff is not None:
                        u["diff_medals"] = got_diff
                        u["diff_reason"] = got_diff_reason or final_diff_reason
                        filled_diff_api += 1
                    else:
                        u["diff_reason"] = final_diff_reason
                        api_miss_total += 1

        browser.close()

    # save
    out_path = os.path.join(out_dir, f"{date_str}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_units, f, ensure_ascii=False, indent=2)

    print(
        f"Saved: {out_path} ({len(all_units)} records) "
        f"filled(bb/rb/art/max/total_text/total_api/diff_text/diff_api)=({filled_bb}/{filled_rb}/{filled_art}/{filled_max}/{filled_total}/{filled_total_api}/{filled_diff_text}/{filled_diff_api}) "
        f"skipped_machine_total={skipped_machine_total} parse_fail_total={parse_fail_total} "
        f"wrong_page_total={wrong_page_total} skipped_page_total={skipped_page_total} api_miss_total={api_miss_total}"
    )
    print(
        "logs: "
        f"{news_fetch_log} / {data_fetch_log} / {data_units_zero_log} / "
        f"{mach_fetch_log} / {mach_parse_log} / {mach_wrong_page_log} / "
        f"{api_diff_log} / {api_json_log} / {api_total_log}"
    )


if __name__ == "__main__":
    main()