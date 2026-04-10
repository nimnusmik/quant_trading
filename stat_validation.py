# =============================================================================
# stat_validation.py — Bootstrap Confidence Interval 통계 검증
#
# 백테스트 결과의 통계적 유의성을 검증합니다.
# 거래 목록을 복원추출(Bootstrap)로 10,000번 재조합하여
# 수익률, 승률, PF, MDD, Sharpe의 95% 신뢰구간을 산출합니다.
# =============================================================================

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import font_manager as fm

from config import (
    INITIAL_CAPITAL, CHART_STYLE, CHART_DIR,
    BOOTSTRAP_N, BOOTSTRAP_CI, BOOTSTRAP_SEED, KOREAN_FONTS,
)


# ─────────────────────────────────────────────
# 한글 폰트 / 스타일 (reporter.py와 동일)
# ─────────────────────────────────────────────

def _setup_font():
    available = {f.name for f in fm.fontManager.ttflist}
    for font_name in KOREAN_FONTS:
        if font_name in available:
            plt.rcParams["font.family"] = font_name
            plt.rcParams["axes.unicode_minus"] = False
            return
    plt.rcParams["axes.unicode_minus"] = False


def _apply_style():
    s = CHART_STYLE
    plt.rcParams.update({
        "figure.facecolor": s["bg"],
        "axes.facecolor":   s["bg"],
        "axes.edgecolor":   s["border"],
        "axes.labelcolor":  s["muted"],
        "text.color":       s["text"],
        "xtick.color":      s["muted"],
        "ytick.color":      s["muted"],
        "grid.color":       s["card"],
        "grid.alpha":       0.6,
        "font.size":        s["font_size"],
        "legend.facecolor": s["card"],
        "legend.edgecolor": s["border"],
    })


# ─────────────────────────────────────────────
# Bootstrap 핵심 계산
# ─────────────────────────────────────────────

def _compute_bootstrap_metrics(pnl_pcts: np.ndarray) -> dict:
    """
    리샘플된 거래 수익률(%) 배열로부터 메트릭을 산출합니다.
    pnl_pcts: 각 거래의 수익률 (%) 배열
    """
    n = len(pnl_pcts)
    if n == 0:
        return {"total_return_pct": 0, "win_rate": 0,
                "profit_factor": 0, "mdd": 0, "sharpe": 0}

    # 에퀴티 재구성 (pnl_pct 기반 복리)
    multipliers = 1.0 + pnl_pcts / 100.0
    equity = INITIAL_CAPITAL * np.cumprod(multipliers)
    equity = np.maximum(equity, 0.0)

    # 수익률
    total_return_pct = (equity[-1] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # 승률
    win_rate = np.sum(pnl_pcts > 0) / n * 100

    # Profit Factor
    gains = np.sum(pnl_pcts[pnl_pcts > 0])
    losses = np.abs(np.sum(pnl_pcts[pnl_pcts < 0]))
    profit_factor = gains / losses if losses > 0 else 20.0  # 상한 클리핑

    # MDD
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    mdd = float(drawdown.min() * 100)

    # Sharpe (거래 단위)
    if np.std(pnl_pcts) > 0:
        # 연간 거래수 추정: n trades / 6개월 검증 → × 2
        trades_per_year = n * 2
        sharpe = float(np.mean(pnl_pcts) / np.std(pnl_pcts)
                       * np.sqrt(trades_per_year))
    else:
        sharpe = 0.0

    return {
        "total_return_pct": total_return_pct,
        "win_rate":         win_rate,
        "profit_factor":    min(profit_factor, 20.0),
        "mdd":              mdd,
        "sharpe":           sharpe,
    }


def bootstrap_ci(trades: list,
                 n_bootstrap: int = BOOTSTRAP_N,
                 confidence: float = BOOTSTRAP_CI,
                 seed: int = BOOTSTRAP_SEED) -> dict:
    """
    거래 목록에 대해 Bootstrap Confidence Interval을 계산합니다.

    Parameters
    ----------
    trades      : Trade 객체 리스트 (pnl_pct 속성 필요)
    n_bootstrap : 리샘플링 횟수 (기본 10,000)
    confidence  : 신뢰구간 수준 (기본 0.95)
    seed        : 랜덤 시드

    Returns
    -------
    dict: {metric_name: {"observed": float, "mean": float,
           "ci_lower": float, "ci_upper": float, "samples": np.array}}
    """
    if len(trades) < 2:
        return {}

    pnl_pcts = np.array([t.pnl_pct for t in trades])
    n = len(pnl_pcts)

    # 관측값 (실제 결과)
    observed = _compute_bootstrap_metrics(pnl_pcts)

    # Bootstrap 리샘플링
    rng = np.random.default_rng(seed)
    alpha = (1 - confidence) / 2  # 양측 검정

    metric_keys = ["total_return_pct", "win_rate", "profit_factor", "mdd", "sharpe"]
    samples = {k: np.empty(n_bootstrap) for k in metric_keys}

    for i in range(n_bootstrap):
        idx = rng.choice(n, size=n, replace=True)
        resampled = pnl_pcts[idx]
        m = _compute_bootstrap_metrics(resampled)
        for k in metric_keys:
            samples[k][i] = m[k]

    # 결과 정리
    results = {}
    for k in metric_keys:
        s = samples[k]
        results[k] = {
            "observed":  observed[k],
            "mean":      float(np.mean(s)),
            "ci_lower":  float(np.percentile(s, alpha * 100)),
            "ci_upper":  float(np.percentile(s, (1 - alpha) * 100)),
            "samples":   s,
        }

    return results


# ─────────────────────────────────────────────
# 시각화
# ─────────────────────────────────────────────

def plot_bootstrap_histograms(bootstrap_results: dict,
                               strategy_key: str,
                               timeframe_key: str,
                               save_dir: str = CHART_DIR) -> str:
    """Bootstrap 결과를 히스토그램으로 시각화합니다."""
    if not bootstrap_results:
        return ""

    _setup_font()
    _apply_style()
    s = CHART_STYLE

    fig, axes = plt.subplots(2, 3, figsize=(20, 10))
    fig.patch.set_facecolor(s["bg"])

    tf_label = {"1h": "1시간봉", "5m": "5분봉", "1m": "1분봉"}.get(timeframe_key, timeframe_key)
    fig.suptitle(
        f"Bootstrap 신뢰구간 검증 — {strategy_key} ({tf_label}, {BOOTSTRAP_N:,}회)",
        fontsize=14, fontweight="bold", y=0.98, color=s["text"],
    )

    metric_info = [
        ("total_return_pct", "수익률 (%)",     0,    "수익률 > 0%"),
        ("win_rate",         "승률 (%)",       None,  None),
        ("profit_factor",    "Profit Factor",  1.0,  "PF > 1.0"),
        ("mdd",              "MDD (%)",        None,  None),
        ("sharpe",           "Sharpe Ratio",   0,    "Sharpe > 0"),
    ]

    for idx, (key, label, threshold, sig_label) in enumerate(metric_info):
        ax = axes[idx // 3][idx % 3]
        ax.set_facecolor(s["bg"])

        r = bootstrap_results[key]
        samples = r["samples"]
        ci_lo, ci_hi = r["ci_lower"], r["ci_upper"]
        observed = r["observed"]

        # 히스토그램
        ax.hist(samples, bins=80, color=s["teal"], alpha=0.7, edgecolor="none")

        # CI 영역
        ax.axvspan(ci_lo, ci_hi, alpha=0.15, color=s["gold"])

        # CI 경계선
        ax.axvline(ci_lo, color=s["gold"], linewidth=1.2, linestyle="--",
                   label=f"95% CI: [{ci_lo:.1f}, {ci_hi:.1f}]")
        ax.axvline(ci_hi, color=s["gold"], linewidth=1.2, linestyle="--")

        # 관측값
        ax.axvline(observed, color=s["green"], linewidth=2, linestyle="-",
                   label=f"관측값: {observed:.1f}")

        # 기준선 (수익률 0%, PF 1.0 등)
        if threshold is not None:
            ax.axvline(threshold, color=s["red"], linewidth=1, linestyle=":",
                       alpha=0.7, label=sig_label)

        ax.set_title(label, fontsize=11, fontweight="bold", color=s["text"], pad=6)
        ax.legend(fontsize=8, framealpha=0.3)
        ax.grid(True, alpha=0.15)

    # 마지막 칸: 요약 텍스트
    ax_text = axes[1][2]
    ax_text.axis("off")

    summary_lines = [f"Bootstrap 요약\n({BOOTSTRAP_N:,}회 리샘플링)\n"]
    for key, label, threshold, _ in metric_info:
        r = bootstrap_results[key]
        sig = ""
        if threshold is not None:
            if key == "mdd":
                pass
            elif r["ci_lower"] > threshold:
                sig = "  OK"
            else:
                sig = "  ?"
        summary_lines.append(
            f"{label}:  {r['observed']:+.1f}\n"
            f"  95% CI: [{r['ci_lower']:+.1f}, {r['ci_upper']:+.1f}]{sig}"
        )

    ax_text.text(0.05, 0.95, "\n".join(summary_lines),
                 transform=ax_text.transAxes, fontsize=10,
                 verticalalignment="top", color=s["text"],
                 fontfamily="monospace",
                 bbox=dict(boxstyle="round,pad=0.5",
                           facecolor=s["card"], edgecolor=s["border"]))

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, f"bootstrap_{strategy_key}_{timeframe_key}.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=s["bg"], edgecolor="none")
    plt.close()
    print(f"  [저장] {out_path}")
    return out_path


# ─────────────────────────────────────────────
# 콘솔 출력
# ─────────────────────────────────────────────

def print_bootstrap_summary(bootstrap_results: dict,
                             strategy_key: str,
                             n_trades: int) -> None:
    """Bootstrap CI 결과를 콘솔에 출력합니다."""
    if not bootstrap_results:
        return

    print(f"\n── Bootstrap 신뢰구간 ({strategy_key}, {BOOTSTRAP_N:,}회 리샘플링, {n_trades}건 거래) ──")

    if n_trades < 10:
        print(f"  ※ 거래수 {n_trades}건 — 신뢰구간의 정확도가 낮습니다")

    metric_info = [
        ("total_return_pct", "수익률 (%)",     0,   "0% 초과"),
        ("win_rate",         "승률 (%)",       None, None),
        ("profit_factor",    "Profit Factor",  1.0, "1.0 초과"),
        ("mdd",              "MDD (%)",        None, None),
        ("sharpe",           "Sharpe",         0,   "0 초과"),
    ]

    print(f"  {'지표':<18} {'관측값':>8}    {'95% CI 하한':>12}  {'95% CI 상한':>12}  {'유의성':>8}")
    print(f"  {'-'*66}")

    for key, label, threshold, sig_label in metric_info:
        r = bootstrap_results[key]
        obs = r["observed"]
        lo = r["ci_lower"]
        hi = r["ci_upper"]

        sig = ""
        if threshold is not None:
            if r["ci_lower"] > threshold:
                sig = f"OK ({sig_label})"
            else:
                sig = ""

        print(f"  {label:<18} {obs:>+7.1f}    {lo:>+11.1f}   {hi:>+11.1f}   {sig}")

    # 최종 판단
    ret_lo = bootstrap_results["total_return_pct"]["ci_lower"]
    pf_lo = bootstrap_results["profit_factor"]["ci_lower"]

    print(f"  {'-'*66}")
    if ret_lo > 0 and pf_lo > 1.0:
        print(f"  ==> 수익률 CI 하한 > 0%, PF CI 하한 > 1.0 → 통계적으로 유의한 전략")
    elif ret_lo > 0:
        print(f"  ==> 수익률 CI 하한 > 0% → 양의 수익은 유의하나, PF 안정성 추가 확인 필요")
    else:
        print(f"  ==> 수익률 CI 하한 <= 0% → 통계적 유의성 부족, 실전 투입 주의")
