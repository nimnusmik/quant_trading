# =============================================================================
# monitor/best_params.py — 백테스트 최적 파라미터 로더
#
# best_params_1h.csv에서 전략별 최적 파라미터를 읽어옵니다.
# signal_monitor, scheduler에서 이 파라미터를 사용합니다.
# =============================================================================

import os
import csv

# 프로젝트 루트 기준 CSV 경로
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CSV_PATH = os.path.join(_PROJECT_ROOT, "results", "1year", "csv", "best_params_1h.csv")

# 통계적으로 유의한 전략만 활성화 (Bootstrap CI 하한 > 0%)
ACTIVE_STRATEGIES = {"S1_EMA_Cross", "S2_VWAP_Bounce", "S6_MACD_Volume"}


def load_best_params(csv_path: str = _CSV_PATH) -> dict:
    """
    best_params CSV를 읽어 전략별 파라미터 딕셔너리로 반환합니다.

    Returns
    -------
    dict  {
        "S1_EMA_Cross": {
            "ema_fast": 5, "ema_slow": 13, "rsi_period": 14,
            "tp_pct": 0.05, "sl_pct": 0.002, "max_hold": 96,
            "cooldown": 3, "vwap_tol": None,
        },
        ...
    }
    """
    params = {}

    if not os.path.exists(csv_path):
        print(f"[best_params] CSV 없음: {csv_path} — 기본값 사용")
        return params

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            strat = row["strategy"]
            params[strat] = {
                "ema_fast":   int(row["param_ema_fast"]),
                "ema_slow":   int(row["param_ema_slow"]),
                "rsi_period": int(row["param_rsi_period"]),
                "tp_pct":     float(row["param_tp_pct"]),
                "sl_pct":     float(row["param_sl_pct"]),
                "max_hold":   int(row["param_max_hold"]),
                "cooldown":   int(row["param_cooldown"]),
                "vwap_tol":   float(row["param_vwap_tol"]) if row.get("param_vwap_tol") else None,
            }

    print(f"[best_params] {len(params)}개 전략 파라미터 로드 완료")
    for strat, p in params.items():
        active = "✓" if strat in ACTIVE_STRATEGIES else "✗"
        print(f"  {active} {strat}: EMA({p['ema_fast']}/{p['ema_slow']}) RSI({p['rsi_period']}) TP({p['tp_pct']:.1%}) SL({p['sl_pct']:.1%})")

    return params


# 모듈 로드 시 1회 읽기 (캐싱)
BEST_PARAMS = load_best_params()
