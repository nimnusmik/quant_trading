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
import os
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm

from config import GRID, STRATEGY_GRIDS, WF_TRAIN_DAYS, WF_TEST_DAYS, INITIAL_CAPITAL
from indicators import compute_all
from backtest_engine import run_backtest, compute_metrics
from strategies import STRATEGIES


# ─────────────────────────────────────────────
# Rolling Walk-Forward 데이터 분할
# ─────────────────────────────────────────────

def generate_wf_splits(df: pd.DataFrame,
                       candles_per_day: int = 24) -> list:
    """
    Rolling Walk-Forward 분할.
    테스트 구간이 겹치지 않도록 슬라이딩합니다.

    1년 1h 데이터 예시 (train=6개월, test=2개월):
      폴드1: 학습 [月1-6] → 검증 [月7-8]
      폴드2: 학습 [月3-8] → 검증 [月9-10]
      폴드3: 학습 [月5-10] → 검증 [月11-12]
    → 검증 합산 6개월 (기존 1개월 대비 6배)
    """
    train_candles = WF_TRAIN_DAYS * candles_per_day
    test_candles  = WF_TEST_DAYS  * candles_per_day

    n = len(df)
    splits = []
    start = 0

    while start + train_candles + test_candles <= n:
        train_end = start + train_candles
        test_end  = train_end + test_candles

        df_train = df.iloc[start:train_end].reset_index(drop=True)
        df_test  = df.iloc[train_end:test_end].reset_index(drop=True)
        splits.append((df_train, df_test))

        start += test_candles  # 테스트 구간만큼 전진 (겹침 없음)

    print(f"\n  Rolling Walk-Forward: {len(splits)}개 폴드")
    for i, (tr, te) in enumerate(splits):
        print(f"    폴드 {i+1}: 학습 {tr['datetime'].iloc[0].date()}"
              f"~{tr['datetime'].iloc[-1].date()} ({len(tr):,}캔들)"
              f" → 검증 {te['datetime'].iloc[0].date()}"
              f"~{te['datetime'].iloc[-1].date()} ({len(te):,}캔들)")

    return splits


# ─────────────────────────────────────────────
# 단일 전략 그리드 서치
# ─────────────────────────────────────────────

def grid_search_strategy(strategy_key: str,
                          df_train: pd.DataFrame,
                          candles_per_day: int = 24,
                          top_n: int = 5,
                          tqdm_position: int = 0) -> pd.DataFrame:
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

    # 매매 파라미터 조합 (지표·신호와 무관 → 내부 루프에서만 변경)
    trade_combos = [
        (tp, sl, mh, cd)
        for tp, sl, mh, cd in itertools.product(
            tp_pcts, sl_pcts, max_hold_bars, cooldown_bars)
        if tp > sl * 0.3  # TP가 SL의 30% 이상이어야 손익비 최소 유지
    ]

    # 지표가 달라지는 조합: (ema_pair, rsi_period)만 — 나머지는 동일
    indicator_keys = list(itertools.product(ema_pairs, rsi_periods))
    total = len(indicator_keys) * len(vwap_tol_pcts) * len(trade_combos)

    desc = f"{strategy_key} 그리드 서치"
    pbar = tqdm(total=total, desc=desc, position=tqdm_position, leave=True)

    for ema_pair, rsi_p in indicator_keys:
        # 지표 계산: (ema_pair, rsi_period) 당 1회만
        df_ind = compute_all(df_train,
                             ema_fast   = ema_pair[0],
                             ema_slow   = ema_pair[1],
                             ema_trend  = max(ema_pair[1], 50),
                             rsi_period = rsi_p)

        for vwap_tol in vwap_tol_pcts:
            # 신호 생성: 같은 지표 + vwap_tol이면 신호도 동일
            try:
                if vwap_tol is not None:
                    long_sig, short_sig = strategy_fn(df_ind, vwap_tol=vwap_tol)
                else:
                    long_sig, short_sig = strategy_fn(df_ind)
            except Exception:
                pbar.update(len(trade_combos))
                continue

            n_signals = long_sig.sum() + short_sig.sum()
            if n_signals < 3:
                pbar.update(len(trade_combos))
                continue

            # 매매 파라미터만 변경하며 백테스트 반복
            for tp, sl, max_hold, cooldown in trade_combos:
                pbar.update(1)

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

    pbar.close()

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
# 병렬 그리드 서치 워커
# ─────────────────────────────────────────────

def _grid_search_worker(args):
    """ProcessPoolExecutor 워커. 하나의 전략에 대해 그리드 서치를 실행합니다."""
    s_key, df_train, candles_per_day, position = args
    top_df = grid_search_strategy(s_key, df_train, candles_per_day,
                                  tqdm_position=position)
    return s_key, top_df


# ─────────────────────────────────────────────
# 전체 전략 그리드 서치 실행
# ─────────────────────────────────────────────

def _evaluate_test(s_key, best_params, df_train, df_test, candles_per_day):
    """하나의 전략에 대해 검증 데이터로 백테스트를 실행합니다."""
    p = best_params
    warmup = max(p["ema_slow"], 50) * 3
    df_ctx = pd.concat([df_train.tail(warmup), df_test], ignore_index=True)
    df_ind = compute_all(df_ctx,
                         ema_fast   = p["ema_fast"],
                         ema_slow   = p["ema_slow"],
                         ema_trend  = max(p["ema_slow"], 50),
                         rsi_period = p["rsi_period"])
    df_ind = df_ind.iloc[warmup:].reset_index(drop=True)

    vwap_tol = p.get("vwap_tol")
    if vwap_tol is not None:
        long_sig, short_sig = STRATEGIES[s_key](df_ind, vwap_tol=vwap_tol)
    else:
        long_sig, short_sig = STRATEGIES[s_key](df_ind)

    trades, equity = run_backtest(
        df_ind, long_sig, short_sig,
        tp_pct        = p["tp_pct"],
        sl_pct        = p["sl_pct"],
        max_hold_bars = p["max_hold"],
        cooldown_bars = p["cooldown"],
    )
    return trades, equity


def _extract_best_params(top_df: pd.DataFrame) -> dict:
    """그리드 서치 결과에서 1위 파라미터를 추출합니다."""
    best = top_df.iloc[0].to_dict()
    return {
        "ema_fast":    int(best["ema_fast"]),
        "ema_slow":    int(best["ema_slow"]),
        "rsi_period":  int(best["rsi_period"]),
        "tp_pct":      best["tp_pct"],
        "sl_pct":      best["sl_pct"],
        "max_hold":    int(best["max_hold"]),
        "cooldown":    int(best["cooldown"]),
        "vwap_tol":    best.get("vwap_tol"),
    }


def _chain_equity_curves(fold_equities: list) -> list:
    """여러 폴드의 에퀴티 곡선을 이어붙입니다.
    각 폴드는 이전 폴드의 최종 자본에서 시작하도록 스케일링."""
    chained = []
    capital = None

    for fold_eq in fold_equities:
        if not fold_eq:
            continue
        if capital is None:
            chained.extend(fold_eq)
        else:
            init = fold_eq[0]
            ratio = capital / init if init != 0 else 1.0
            chained.extend([e * ratio for e in fold_eq])
        capital = chained[-1] if chained else None

    return chained


def run_all_grid_searches(df: pd.DataFrame,
                           candles_per_day: int = 24) -> dict:
    """
    Rolling Walk-Forward 그리드 서치.

    각 폴드마다:
      1) 학습 데이터로 최적 파라미터 탐색 (병렬)
      2) 검증 데이터로 성능 확인
    모든 폴드의 검증 결과를 합산하여 최종 성과를 산출합니다.
    """
    print("\n" + "="*60)
    print("Rolling Walk-Forward 그리드 서치 시작")
    print("="*60)

    splits = generate_wf_splits(df, candles_per_day)

    strategy_keys = list(STRATEGIES.keys())
    n_workers = min(len(strategy_keys), os.cpu_count() or 1)

    # 전략별 폴드 결과 누적
    agg_trades = {sk: [] for sk in strategy_keys}
    agg_equity = {sk: [] for sk in strategy_keys}
    last_best_params   = {sk: _default_params() for sk in strategy_keys}
    last_train_results = {}

    for fold_i, (df_train, df_test) in enumerate(splits):
        print(f"\n{'='*60}")
        print(f"  폴드 {fold_i+1}/{len(splits)}")
        print(f"{'='*60}")

        # ── 병렬 그리드 서치 ──
        print(f"  병렬 실행: {len(strategy_keys)}개 전략 × {n_workers} 워커\n")
        args_list = [
            (s_key, df_train, candles_per_day, i)
            for i, s_key in enumerate(strategy_keys)
        ]

        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            grid_results_list = list(executor.map(_grid_search_worker, args_list))

        grid_results = dict(grid_results_list)
        print()

        # ── 검증 ──
        for s_key in strategy_keys:
            top_df = grid_results[s_key]

            if top_df.empty:
                print(f"  [{s_key}] 폴드{fold_i+1} 최적화 실패")
                continue

            last_train_results[s_key] = top_df
            bp = _extract_best_params(top_df)
            last_best_params[s_key] = bp

            trades, equity = _evaluate_test(
                s_key, bp, df_train, df_test, candles_per_day
            )
            m = compute_metrics(trades, equity, candles_per_day)

            agg_trades[s_key].extend(trades)
            agg_equity[s_key].append(equity)

            best = top_df.iloc[0]
            print(f"  [{s_key}] 폴드{fold_i+1}: "
                  f"학습 {best['total_return_pct']:+.1f}% → "
                  f"검증 {m['total_return_pct']:+.1f}% | "
                  f"승률 {m['win_rate']:.0f}% | "
                  f"거래수 {m['total_trades']} | "
                  f"EMA{bp['ema_fast']}/{bp['ema_slow']} "
                  f"RSI{bp['rsi_period']} "
                  f"TP{bp['tp_pct']*100:.1f}%")

    # ── 전체 폴드 합산 ──
    print(f"\n{'='*60}")
    print("  폴드 합산 결과")
    print(f"{'='*60}")

    test_results = {}
    for s_key in strategy_keys:
        if not agg_trades[s_key]:
            test_results[s_key] = {}
            continue

        chained = _chain_equity_curves(agg_equity[s_key])
        metrics = compute_metrics(agg_trades[s_key], chained, candles_per_day)
        test_results[s_key] = {
            "metrics": metrics,
            "trades":  agg_trades[s_key],
            "equity":  chained,
        }
        print(f"  [{s_key}] 합산: "
              f"수익률 {metrics['total_return_pct']:+.1f}% | "
              f"승률 {metrics['win_rate']:.0f}% | "
              f"PF {metrics['profit_factor']:.2f} | "
              f"MDD {metrics['mdd']:.1f}% | "
              f"거래수 {metrics['total_trades']}")

    # 리포트용: 전체 테스트 구간 합치기
    all_df_tests = [te for _, te in splits]
    df_test_all  = pd.concat(all_df_tests, ignore_index=True)
    last_df_train = splits[-1][0] if splits else pd.DataFrame()

    return {
        "train_results": last_train_results,
        "test_results":  test_results,
        "best_params":   last_best_params,
        "df_train":      last_df_train,
        "df_test":       df_test_all,
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
