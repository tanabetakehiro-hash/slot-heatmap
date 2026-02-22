# analysis/predict_next_day.py
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def mean(nums: List[int]) -> float:
    return sum(nums) / len(nums) if nums else 0.0


def load_history(path: Path) -> Dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("history.json must be an object")
    return obj


def predict_next(history: Dict[str, Any], window: int = 7, min_points: int = 2) -> Dict[str, Any]:
    dates: List[str] = history.get("dates") or []
    units: List[str] = history.get("units") or []
    values: List[List[Optional[int]]] = history.get("values") or []

    if not dates or not units or not values:
        raise ValueError("history.json missing dates/units/values")

    # 最終日の次の日を “予測対象日” とする（営業日飛びは考慮しない簡易版）
    last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
    target_date = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")

    # values: [date_index][unit_index]
    # 各台ごとに、直近window日から non-null を拾って平均
    preds: List[Dict[str, Any]] = []

    # 直近 window 日だけ切る
    use_values = values[-window:] if len(values) > window else values[:]
    use_dates = dates[-window:] if len(dates) > window else dates[:]

    for ui, unit_no in enumerate(units):
        series: List[int] = []
        for di in range(len(use_values)):
            v = use_values[di][ui] if ui < len(use_values[di]) else None
            if isinstance(v, int):
                series.append(v)

        if len(series) < min_points:
            pred = None
        else:
            pred = round(mean(series), 1)

        preds.append(
            {
                "unit_no": unit_no,
                "pred_max_payout": pred,          # null or number
                "based_on_days": len(series),
                "window_days": len(use_dates),
            }
        )

    # predicted があるものだけランキング
    ranked = [p for p in preds if isinstance(p.get("pred_max_payout"), (int, float))]
    ranked.sort(key=lambda x: x["pred_max_payout"], reverse=True)

    out = {
        "target_date": target_date,
        "method": "moving_average",
        "window_days": len(use_dates),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "top": ranked[:50],
        "all": preds,
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", required=True, help="Path to docs/data/history.json")
    ap.add_argument("--out", required=True, help="Path to write prediction json")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--min_points", type=int, default=2)
    args = ap.parse_args()

    history_path = Path(args.history)
    out_path = Path(args.out)

    history = load_history(history_path)
    pred = predict_next(history, window=args.window, min_points=args.min_points)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pred, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")


if __name__ == "__main__":
    main()