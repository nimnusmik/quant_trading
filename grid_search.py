# =============================================================================
# grid_search.py — 파라미터 그리드 서치
#
# 스승의 노트:
#   그리드 서치의 함정 = 과적합(Overfitting).
#   "이 기간 데이터에서 가장 좋은 파라미터"를 찾아도
#   미래 데이터에서 망하는 경우가 다반사입니다.
#
#   그래서 이 코드는:
#   1) 6개월 데이터를 앞 5개월(학습) / 뒤 1개월(검증)으로 분리
#   2) 학습 데이터에서 최적 파라미터 탐색
#   3) 검증 데이터에서 그 파라미터의 "진짜" 성능 확인
#   이를 Walk-Forward 검증이라 부릅니다.
# =============================================================================

import itertools
import pandas as pd
import numpy as np
from tqdm import tqdm

from config import GRID, STRATEGY_GRIDS
from indicators import compute_all
from backtest_engine import run_backtest, compute_metrics
from strategies import STRATEGIES


# ─────────────────────────────────────────────
# Walk-Forward 데이터 분할
# ─────────────────────────────────────────────

def split_train_test(df: pd.DataFrame,
                     test_ratio: float = 1/6) -> tuple:
    """
    앞부분을 학습(train), 뒷부분을 검증(test) 데이터로 분리합니다.
    기본값: 앞 5/6 = 학습, 뒤 1/6 = 검증 (6개월 → 5개월 학습 + 1개월 검증)
    """
    split_idx   = int(len(df) * (1 - test_ratio))
    df_train    = df.iloc[:split_idx].reset_index(drop=True)
    df_test     = df.iloc[split_idx:].reset_index(drop=True)

    print(f"  학습 기간: {df_train['datetime'].iloc[0].date()} "
          f"~ {df_train['datetime'].iloc[-1].date()} ({len(df_train):,}캔들)")
    print(f"  검증 기간: {df_test['datetime'].iloc[0].date()} "
          f"~ {df_test['datetime'].iloc[-1].date()} ({len(df_test):,}캔들)")

    return df_train, df_test


# ─────────────────────────────────────────────
# 단일 전략 그리드 서치
# ─────────────────────────────────────────────

def grid_search_strategy(strategy_key: str,
                          df_train: pd.DataFrame,
                          candles_per_day: int = 24,
                          top_n: int = 5) -> pd.DataFrame:
    """
    하나의 전략에 대해 모든 파라미터 조합을 테스트합니다.

    Parameters
    ----------
    strategy_key    : STRATEGIES 딕셔너리 키 (예: "S3_RSI_Extreme")
    df_train        : 학습 데이터
    candles_per_day : 연환산 계수
    top_n           : 상위 N개 결과 반환

    Returns
    -------
    DataFrame : 상위 N개 파라미터 조합과 성과 지표
    """
    strategy_fn = STRATEGIES[strategy_key]
    results     = []

    # 전략별 파라미터 오버라이드 적용
    overrides     = STRATEGY_GRIDS.get(strategy_key, {})
    ema_pairs     = overrides.get("ema_pairs",     GRID["ema_pairs"])
    rsi_periods   = overrides.get("rsi_periods",   GRID["rsi_periods"])
    tp_pcts       = overrides.get("tp_pcts",       GRID["tp_pcts"])
    sl_pcts       = overrides.get("sl_pcts",       GRID["sl_pcts"])
    max_hold_bars = overrides.get("max_hold_bars", GRID["max_hold_bars"])
    cooldown_bars = overrides.get("cooldown_bars", GRID["cooldown_bars"])
    # vwap_tol_pcts: S3 전용. 나머지 전략은 None(기본값 사용)
    vwap_tol_pcts = overrides.get("vwap_tol_pcts", [None])

    # 파라미터 공간 생성
    param_combos = list(itertools.product(
        ema_pairs,
        rsi_periods,
        tp_pcts,
        sl_pcts,
        max_hold_bars,
        cooldown_bars,
        vwap_tol_pcts,
    ))

    # TP < SL 조합은 의미 없으므로 제거
    param_combos = [
        (ep, rp, tp, sl, mh, cd, vt)
        for (ep, rp, tp, sl, mh, cd, vt) in param_combos
        if tp > sl * 0.3  # TP가 SL의 30% 이상이어야 손익비 최소 유지
    ]

    desc = f"{strategy_key} 그리드 서치"
    for (ema_pair, rsi_p, tp, sl, max_hold, cooldown, vwap_tol) in tqdm(param_combos, desc=desc):

        # 지표 계산 (파라미터 조합마다 EMA/RSI 기간이 달라질 수 있음)
        df_ind = compute_all(df_train,
                             ema_fast   = ema_pair[0],
                             ema_slow   = ema_pair[1],
                             ema_trend  = max(ema_pair[1], 50),  # 장기선은 최소 50
                             rsi_period = rsi_p)

        # 전략 신호 생성 (S3는 vwap_tol을 파라미터로 전달)
        try:
            if vwap_tol is not None:
                long_sig, short_sig = strategy_fn(df_ind, vwap_tol=vwap_tol)
            else:
                long_sig, short_sig = strategy_fn(df_ind)
        except Exception:
            continue

        # 신호가 너무 적으면 통계적 의미 없음 → 건너뜀
        n_signals = long_sig.sum() + short_sig.sum()
        if n_signals < 3:
            continue

        # 백테스트 실행
        trades, equity = run_backtest(
            df_ind, long_sig, short_sig,
            tp_pct        = tp,
            sl_pct        = sl,
            max_hold_bars = max_hold,
            cooldown_bars = cooldown,
        )

        if len(trades) < 3:
            continue

        metrics = compute_metrics(trades, equity, candles_per_day)

        # 결과 저장
        results.append({
            "strategy":    strategy_key,
            "ema_fast":    ema_pair[0],
            "ema_slow":    ema_pair[1],
            "rsi_period":  rsi_p,
            "tp_pct":      tp,
            "sl_pct":      sl,
            "max_hold":    max_hold,
            "cooldown":    cooldown,
            "vwap_tol":    vwap_tol,
            **{k: v for k, v in metrics.items() if k != "monthly_ret"},
        })

    if not results:
        print(f"  [{strategy_key}] 유효한 결과 없음")
        return pd.DataFrame()

    df_results = pd.DataFrame(results)

    # 정렬 기준: 수익률 × PF보너스 × MDD패널티
    # MDD가 클수록 점수가 낮아지도록 (mdd는 음수이므로 abs 처리)
    mdd_penalty = 1 / (1 + df_results["mdd"].abs() / 100)
    df_results["score"] = (
        df_results["total_return_pct"] *
        np.log1p(df_results["profit_factor"].clip(upper=20)) *
        mdd_penalty
    )
    df_results = df_results.sort_values("score", ascending=False).head(top_n)

    return df_results


# ─────────────────────────────────────────────
# 전체 전략 그리드 서치 실행
# ─────────────────────────────────────────────

def run_all_grid_searches(df: pd.DataFrame,
                           candles_per_day: int = 24) -> dict:
    """
    6개 전략 전체에 대해 Walk-Forward 그리드 서치를 실행합니다.

    Returns
    -------
    dict {
        "train_results": {strategy_key: DataFrame},  각 전략의 최적 파라미터
        "test_results":  {strategy_key: dict},        검증 성과
        "best_params":   {strategy_key: dict},        최적 파라미터
        "df_train":      DataFrame,
        "df_test":       DataFrame,
    }
    """
    print("\n" + "="*60)
    print("Walk-Forward 그리드 서치 시작")
    print("="*60)

    # 데이터 분할
    df_train, df_test = split_train_test(df)

    train_results = {}
    test_results  = {}
    best_params   = {}

    for s_key in STRATEGIES.keys():
        print(f"\n── {s_key} ──")

        # 학습 데이터로 최적 파라미터 탐색
        top_df = grid_search_strategy(s_key, df_train, candles_per_day)

        if top_df.empty:
            print(f"  [{s_key}] 최적화 실패 — 기본값 사용")
            best_params[s_key] = _default_params()
            test_results[s_key] = {}
            continue

        train_results[s_key] = top_df

        # 1위 파라미터 추출
        best = top_df.iloc[0].to_dict()
        best_params[s_key] = {
            "ema_fast":    int(best["ema_fast"]),
            "ema_slow":    int(best["ema_slow"]),
            "rsi_period":  int(best["rsi_period"]),
            "tp_pct":      best["tp_pct"],
            "sl_pct":      best["sl_pct"],
            "max_hold":    int(best["max_hold"]),
            "cooldown":    int(best["cooldown"]),
            "vwap_tol":    best.get("vwap_tol"),  # S3만 사용, 나머지는 None
        }

        print(f"  학습 최고: 수익률 {best['total_return_pct']:.1f}% | "
              f"승률 {best['win_rate']:.0f}% | "
              f"거래수 {int(best['total_trades'])} | "
              f"파라미터: EMA{int(best['ema_fast'])}/{int(best['ema_slow'])} "
              f"RSI{int(best['rsi_period'])} "
              f"TP{best['tp_pct']*100:.1f}% SL{best['sl_pct']*100:.1f}%")

        # 검증 데이터로 성능 확인
        p = best_params[s_key]
        # EMA/RSI 워밍업을 위해 훈련 데이터 마지막 N캔들을 앞에 붙임
        # (테스트 구간만 단독 계산하면 초반 EMA 값이 잘못 수렴됨)
        warmup = max(p["ema_slow"], 50) * 3
        df_test_context = pd.concat(
            [df_train.tail(warmup), df_test], ignore_index=True
        )
        df_test_ind_full = compute_all(df_test_context,
                                       ema_fast   = p["ema_fast"],
                                       ema_slow   = p["ema_slow"],
                                       ema_trend  = max(p["ema_slow"], 50),
                                       rsi_period = p["rsi_period"])
        df_test_ind = df_test_ind_full.iloc[warmup:].reset_index(drop=True)

        vwap_tol = p.get("vwap_tol")
        if vwap_tol is not None:
            long_sig, short_sig = STRATEGIES[s_key](df_test_ind, vwap_tol=vwap_tol)
        else:
            long_sig, short_sig = STRATEGIES[s_key](df_test_ind)

        test_trades, test_equity = run_backtest(
            df_test_ind, long_sig, short_sig,
            tp_pct        = p["tp_pct"],
            sl_pct        = p["sl_pct"],
            max_hold_bars = p["max_hold"],
            cooldown_bars = p["cooldown"],
        )

        test_metrics = compute_metrics(test_trades, test_equity, candles_per_day)
        test_results[s_key] = {
            "metrics": test_metrics,
            "trades":  test_trades,
            "equity":  test_equity,
        }

        print(f"  검증 결과: 수익률 {test_metrics['total_return_pct']:.1f}% | "
              f"승률 {test_metrics['win_rate']:.0f}% | "
              f"거래수 {test_metrics['total_trades']}")

    return {
        "train_results": train_results,
        "test_results":  test_results,
        "best_params":   best_params,
        "df_train":      df_train,
        "df_test":       df_test,
    }


def _default_params() -> dict:
    """최적화 실패 시 사용할 기본 파라미터."""
    return {
        "ema_fast":   9,
        "ema_slow":  21,
        "rsi_period": 7,
        "tp_pct":    0.005,
        "sl_pct":    0.010,
        "max_hold":   48,
        "cooldown":    3,
    }
