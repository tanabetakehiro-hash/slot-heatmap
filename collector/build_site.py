# collector/build_site.py
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =========================
# 設定（必要ならここだけ変える）
# =========================
MAX_HISTORY_DAYS = 60  # ヒートマップに載せる最大日数（重ければ 30 などに）
DAILY_DIR_REL = Path("data") / "daily"
DOCS_DIR_REL = Path("docs")
DOCS_DATA_DIR_REL = Path("docs") / "data"
DOCS_DAILY_DIR_REL = Path("docs") / "data" / "daily"

HISTORY_JSON_REL = Path("docs") / "data" / "history.json"
INDEX_JSON_REL = Path("docs") / "data" / "index.json"
PREDICT_JSON_REL = Path("docs") / "data" / "prediction_next.json"

ANALYSIS_PREDICT_SCRIPT_REL = Path("analysis") / "predict_next_day.py"


@dataclass
class Row:
    date: str
    unit_no: str
    model_name: str
    bb: Optional[int]
    rb: Optional[int]
    art: Optional[int]
    total_start: Optional[int]
    max_payout: Optional[int]
    diff_medals: Optional[int]
    source_url: Optional[str]
    detail_url: Optional[str]
    m: Optional[str]
    is_smart: Optional[bool]


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip()
        if s == "" or s.lower() == "nan":
            return None
        # "1,234" 対応
        s = s.replace(",", "")
        return int(float(s))
    except Exception:
        return None


def _to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v)
    return s if s != "" else None


def _load_daily_file(path: Path, date_str: str) -> List[Row]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # utf-8-sig 対応
        data = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(data, list):
        return []

    rows: List[Row] = []
    for r in data:
        if not isinstance(r, dict):
            continue

        unit_no = _to_str(r.get("unit_no")) or _to_str(r.get("machine_id")) or ""
        model_name = _to_str(r.get("model_name")) or _to_str(r.get("machine_name")) or ""

        row = Row(
            date=date_str,
            unit_no=unit_no,
            model_name=model_name,
            bb=_to_int(r.get("bb")),
            rb=_to_int(r.get("rb")),
            art=_to_int(r.get("art")) if r.get("art") is not None else _to_int(r.get("at_art")),
            total_start=_to_int(r.get("total_start")),
            max_payout=_to_int(r.get("max_payout")) if r.get("max_payout") is not None else _to_int(r.get("max_medals")),
            diff_medals=_to_int(r.get("diff_medals")) if r.get("diff_medals") is not None else _to_int(r.get("diff_payout")),
            source_url=_to_str(r.get("source_url")),
            detail_url=_to_str(r.get("detail_url")),
            m=_to_str(r.get("m")),
            is_smart=r.get("is_smart") if isinstance(r.get("is_smart"), bool) else None,
        )
        if row.unit_no and row.model_name:
            rows.append(row)

    # 台番号で並べる（数字として比較できる場合は数字優先）
    def key_unit(x: Row) -> Tuple[int, str]:
        try:
            return (0, f"{int(x.unit_no):08d}")
        except Exception:
            return (1, x.unit_no)

    rows.sort(key=key_unit)
    return rows


def _ensure_dirs(repo_root: Path) -> None:
    docs_dir = repo_root / DOCS_DIR_REL
    (repo_root / DOCS_DATA_DIR_REL).mkdir(parents=True, exist_ok=True)
    (repo_root / DOCS_DAILY_DIR_REL).mkdir(parents=True, exist_ok=True)

    # GitHub Pages 用（念のため）
    nojekyll = docs_dir / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("", encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_daily_outputs(repo_root: Path) -> Tuple[List[str], List[str], Dict[str, Dict[str, Optional[int]]]]:
    """
    returns:
      dates_sorted
      units_sorted
      date_to_unit_to_maxpayout
    """
    daily_dir = repo_root / DAILY_DIR_REL
    if not daily_dir.exists():
        raise FileNotFoundError(f"daily dir not found: {daily_dir}")

    # data/daily の YYYY-MM-DD.json を拾う
    daily_files = sorted([p for p in daily_dir.glob("*.json") if p.is_file()])

    date_rows: Dict[str, List[Row]] = {}
    all_units: set[str] = set()

    for p in daily_files:
        date_str = p.stem  # "2026-02-21"
        # 日付っぽくないものはスキップ
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            continue

        rows = _load_daily_file(p, date_str)
        if not rows:
            continue

        date_rows[date_str] = rows
        for r in rows:
            all_units.add(r.unit_no)

        # その日の一覧を docs/data/daily/<date>.json として保存（フロントがランキング表示に使う）
        out_daily_path = repo_root / DOCS_DAILY_DIR_REL / f"{date_str}.json"
        out_daily_obj = {
            "date": date_str,
            "rows": [r.__dict__ for r in rows],
        }
        _write_json(out_daily_path, out_daily_obj)

    dates_sorted = sorted(date_rows.keys())
    units_sorted = sorted(
        list(all_units),
        key=lambda x: (0, int(x)) if str(x).isdigit() else (1, str(x)),
    )

    # 日×台 の max_payout マップ
    date_to_unit_to_max: Dict[str, Dict[str, Optional[int]]] = {}
    for d in dates_sorted:
        m: Dict[str, Optional[int]] = {}
        for r in date_rows[d]:
            m[r.unit_no] = r.max_payout
        date_to_unit_to_max[d] = m

    return dates_sorted, units_sorted, date_to_unit_to_max


def _build_history(repo_root: Path, dates_sorted: List[str], units_sorted: List[str], date_to_unit_to_max: Dict[str, Dict[str, Optional[int]]]) -> Dict[str, Any]:
    # 最新 MAX_HISTORY_DAYS に絞る
    use_dates = dates_sorted[-MAX_HISTORY_DAYS:] if len(dates_sorted) > MAX_HISTORY_DAYS else dates_sorted[:]

    values: List[List[Optional[int]]] = []
    for d in use_dates:
        unit_map = date_to_unit_to_max.get(d, {})
        row_vals: List[Optional[int]] = []
        for u in units_sorted:
            row_vals.append(unit_map.get(u))
        values.append(row_vals)

    history = {
        "dates": use_dates,
        "units": units_sorted,
        "values": values,  # values[y][x] = max_payout
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return history


def _run_predict(repo_root: Path) -> None:
    script = repo_root / ANALYSIS_PREDICT_SCRIPT_REL
    history_path = repo_root / HISTORY_JSON_REL
    out_path = repo_root / PREDICT_JSON_REL

    if not script.exists():
        print(f"[WARN] predict script not found: {script}")
        return
    if not history_path.exists():
        print(f"[WARN] history json not found: {history_path}")
        return

    try:
        subprocess.run(
            [sys.executable, str(script), "--history", str(history_path), "--out", str(out_path)],
            check=True,
        )
        print(f"[OK] prediction written: {out_path}")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] predict failed: {e}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)

    _ensure_dirs(repo_root)

    dates_sorted, units_sorted, date_to_unit_to_max = _build_daily_outputs(repo_root)
    if not dates_sorted:
        raise RuntimeError("No daily data found under data/daily (YYYY-MM-DD.json).")

    history = _build_history(repo_root, dates_sorted, units_sorted, date_to_unit_to_max)
    _write_json(repo_root / HISTORY_JSON_REL, history)
    print(f"[OK] history written: {repo_root / HISTORY_JSON_REL}")

    index_obj = {
        "dates": dates_sorted,
        "latest_date": dates_sorted[-1],
        "daily_path_format": "data/daily/{date}.json",
        "history_path": "data/history.json",
        "prediction_path": "data/prediction_next.json",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_json(repo_root / INDEX_JSON_REL, index_obj)
    print(f"[OK] index written: {repo_root / INDEX_JSON_REL}")

    # 予測（analysis を使う：簡易の移動平均）
    _run_predict(repo_root)

    # 注意：docs/index.html と docs/assets/* は “手で置く” 方針（誤上書きを防ぐため）
    print("[INFO] Make sure docs/index.html and docs/assets/* exist for the UI.")


if __name__ == "__main__":
    main()