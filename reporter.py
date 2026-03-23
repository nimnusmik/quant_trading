# =============================================================================
# reporter.py — 백테스트 결과 시각화 및 저장
#
# 생성 결과물:
#   1) results/charts/dashboard_1h.png     — 전략 비교 대시보드
#   2) results/charts/heatmap_1h.png       — 월별 수익률 히트맵
#   3) results/csv/trades_S1_1h.csv        — 전략별 개별 거래 내역
#   4) results/csv/best_params.csv         — 최적 파라미터 요약표
# =============================================================================

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # GUI 없는 환경(서버)에서도 동작
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib import font_manager as fm

from config import CHART_STYLE, KOREAN_FONTS, OUTPUT_DIR, CHART_DIR, CSV_DIR
from backtest_engine import trades_to_dataframe
from strategies import STRATEGY_LABELS


# ─────────────────────────────────────────────
# 한글 폰트 설정 (OS별 자동 감지)
# ─────────────────────────────────────────────

def _setup_font():
    """사용 가능한 한글 폰트를 자동으로 선택합니다."""
    available = {f.name for f in fm.fontManager.ttflist}

    for font_name in KOREAN_FONTS:
        if font_name in available:
            plt.rcParams["font.family"]        = font_name
            plt.rcParams["axes.unicode_minus"] = False
            return font_name

    # 후보가 없으면 기본 폰트 유지 (한글이 □로 보일 수 있음)
    plt.rcParams["axes.unicode_minus"] = False
    return "default"


# ─────────────────────────────────────────────
# 공통 스타일 적용
# ─────────────────────────────────────────────

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
# 1. 전략 비교 대시보드
# ─────────────────────────────────────────────

def plot_dashboard(all_results: dict, timeframe_key: str, save_dir: str = CHART_DIR):
    """
    6개 전략의 에퀴티 커브, 성과 지표, 청산 사유를 한 화면에 표시합니다.
    """
    _setup_font()
    _apply_style()
    s = CHART_STYLE

    fig = plt.figure(figsize=(22, 16))
    fig.patch.set_facecolor(s["bg"])

    tf_label = "1시간봉" if timeframe_key == "1h" else "5분봉"
    fig.suptitle(
        f"XRP 스캘핑 6전략 비교 대시보드 ({tf_label} / 6개월 Walk-Forward 검증)",
        fontsize=15, fontweight="bold", y=0.98, color=s["text"]
    )

    strategy_keys = list(all_results.keys())
    colors = [s["teal"], s["gold"], s["green"], "#7B68EE", s["terra"], s["mauve"]]

    # ── 상단: 에퀴티 커브 (전략별 비교) ──────────────
    ax_eq = fig.add_subplot(3, 1, 1)
    ax_eq.set_facecolor(s["bg"])
    ax_eq.set_title("자본금 추이 비교 (검증 기간)", fontsize=12, fontweight="bold",
                    pad=8, color=s["text"])

    for i, sk in enumerate(strategy_keys):
        result = all_results[sk]
        if not result or not result.get("equity"):
            continue
        eq = np.array(result["equity"])
        ax_eq.plot(eq, color=colors[i], linewidth=1.5, alpha=0.9,
                   label=STRATEGY_LABELS.get(sk, sk))

    ax_eq.axhline(10000, color=s["border"], linewidth=0.8, linestyle="--")
    ax_eq.set_ylabel("자본금 ($)", color=s["muted"])
    ax_eq.legend(loc="upper left", fontsize=9, framealpha=0.3)
    ax_eq.grid(True, alpha=0.2)
    ax_eq.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── 중단: 성과 지표 비교 테이블 ──────────────────
    ax_tbl = fig.add_subplot(3, 2, 3)
    ax_tbl.axis("off")

    rows = []
    for sk in strategy_keys:
        result = all_results[sk]
        if not result or not result.get("metrics"):
            rows.append([STRATEGY_LABELS.get(sk, sk), "-", "-", "-", "-", "-", "-"])
            continue
        m = result["metrics"]
        pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float("inf") else "∞"
        rows.append([
            STRATEGY_LABELS.get(sk, sk),
            f"{m['total_return_pct']:+.1f}%",
            f"{m['win_rate']:.0f}%",
            pf_str,
            f"{m['mdd']:.1f}%",
            f"{m['sharpe']:.1f}",
            str(m['total_trades']),
        ])

    col_labels = ["전략명", "수익률", "승률", "PF", "MDD", "Sharpe", "거래수"]
    table = ax_tbl.table(
        cellText   = rows,
        colLabels  = col_labels,
        cellLoc    = "center",
        loc        = "center",
        colWidths  = [0.28, 0.10, 0.09, 0.09, 0.09, 0.09, 0.09],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.8)

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(s["border"])
        if r == 0:
            cell.set_facecolor(s["card"])
            cell.set_text_props(color=s["text"], fontweight="bold")
        else:
            cell.set_facecolor(s["bg"])
            # 수익률 컬럼 색상
            if c == 1 and r > 0:
                val_str = rows[r-1][1].replace("%", "")
                try:
                    val = float(val_str)
                    cell.set_text_props(color=s["green"] if val > 0 else s["red"])
                except ValueError:
                    cell.set_text_props(color=s["muted"])
            else:
                cell.set_text_props(color=s["muted"])

    ax_tbl.set_title("검증 기간 성과 요약", fontsize=11, fontweight="bold",
                     pad=6, color=s["text"])

    # ── 중단 우측: 수익률 막대 차트 ──────────────────
    ax_bar = fig.add_subplot(3, 2, 4)
    ax_bar.set_facecolor(s["bg"])

    ret_vals = []
    bar_labels = []
    bar_colors = []
    for i, sk in enumerate(strategy_keys):
        result = all_results[sk]
        if result and result.get("metrics"):
            ret = result["metrics"]["total_return_pct"]
        else:
            ret = 0
        ret_vals.append(ret)
        bar_labels.append(STRATEGY_LABELS.get(sk, sk).split()[-1][:4])  # 짧게
        bar_colors.append(s["green"] if ret >= 0 else s["red"])

    bars = ax_bar.bar(range(len(ret_vals)), ret_vals,
                      color=bar_colors, alpha=0.8, width=0.6)
    ax_bar.axhline(0, color=s["border"], linewidth=0.8)
    ax_bar.set_xticks(range(len(bar_labels)))
    ax_bar.set_xticklabels(bar_labels, fontsize=9)
    ax_bar.set_ylabel("수익률 (%)", color=s["muted"])
    ax_bar.set_title("전략별 검증 수익률", fontsize=11, fontweight="bold",
                     pad=6, color=s["text"])
    ax_bar.grid(True, alpha=0.2, axis="y")
    for bar, val in zip(bars, ret_vals):
        ax_bar.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() + 0.1,
                    f"{val:+.1f}%", ha="center", va="bottom",
                    fontsize=9, color=s["text"])

    # ── 하단: 전략별 개별 PnL 막대 (처음 3개) ────────
    for idx, sk in enumerate(strategy_keys[:3]):
        ax_pnl = fig.add_subplot(3, 3, 7 + idx)
        ax_pnl.set_facecolor(s["bg"])

        result = all_results[sk]
        if not result or not result.get("trades"):
            ax_pnl.text(0.5, 0.5, "거래 없음", ha="center", va="center",
                        transform=ax_pnl.transAxes, color=s["muted"])
            ax_pnl.set_title(STRATEGY_LABELS.get(sk, sk)[:10], fontsize=9,
                             color=s["text"])
            continue

        pnls   = [t.net_pnl for t in result["trades"]]
        clrs   = [s["green"] if p > 0 else s["red"] for p in pnls]
        ax_pnl.bar(range(len(pnls)), pnls, color=clrs, alpha=0.8, width=0.7)
        ax_pnl.axhline(0, color=s["border"], linewidth=0.8)
        ax_pnl.set_title(STRATEGY_LABELS.get(sk, sk)[:12], fontsize=9,
                         fontweight="bold", pad=5, color=s["text"])
        ax_pnl.set_xlabel("거래 번호", fontsize=8, color=s["muted"])
        ax_pnl.set_ylabel("손익 ($)", fontsize=8, color=s["muted"])
        ax_pnl.grid(True, alpha=0.15, axis="y")
        ax_pnl.tick_params(labelsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, f"dashboard_{timeframe_key}.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=s["bg"], edgecolor="none")
    plt.close()
    print(f"  [저장] {out_path}")
    return out_path


# ─────────────────────────────────────────────
# 2. 월별 수익률 히트맵
# ─────────────────────────────────────────────

def plot_monthly_heatmap(all_results: dict, timeframe_key: str,
                          save_dir: str = CHART_DIR):
    """
    전략별 × 월별 수익률을 히트맵으로 표시합니다.
    어느 전략이 어느 달에 강한지 한눈에 파악할 수 있습니다.
    """
    _setup_font()
    _apply_style()
    s = CHART_STYLE

    # 월별 수익률 수집
    all_months = set()
    monthly_data = {}

    for sk in all_results.keys():
        result = all_results[sk]
        if not result or not result.get("metrics"):
            monthly_data[sk] = {}
            continue
        mr = result["metrics"].get("monthly_ret", {})
        monthly_data[sk] = mr
        all_months.update(mr.keys())

    if not all_months:
        print("  [히트맵] 월별 데이터 없음")
        return

    months_sorted = sorted(all_months)
    strategy_keys = list(all_results.keys())

    # 2D 배열 생성
    matrix = np.zeros((len(strategy_keys), len(months_sorted)))
    for i, sk in enumerate(strategy_keys):
        for j, month in enumerate(months_sorted):
            matrix[i, j] = monthly_data.get(sk, {}).get(month, np.nan)

    fig, ax = plt.subplots(figsize=(max(12, len(months_sorted) * 1.4),
                                     len(strategy_keys) * 1.2 + 2))
    fig.patch.set_facecolor(s["bg"])
    ax.set_facecolor(s["bg"])

    # 커스텀 컬러맵: 손실=빨강, 0=회색, 수익=초록
    import matplotlib.colors as mcolors
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "rg", ["#FC8181", "#2D3748", "#48BB78"], N=256
    )

    # NaN 처리를 위해 masked array 사용
    masked = np.ma.masked_invalid(matrix)
    im = ax.imshow(masked, cmap=cmap, aspect="auto",
                   vmin=-max(5, np.nanmax(np.abs(matrix))),
                   vmax= max(5, np.nanmax(np.abs(matrix))))

    # 축 레이블
    ax.set_xticks(range(len(months_sorted)))
    ax.set_xticklabels(months_sorted, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(len(strategy_keys)))
    ax.set_yticklabels(
        [STRATEGY_LABELS.get(sk, sk) for sk in strategy_keys], fontsize=10
    )

    # 셀 내부에 수치 표시
    for i in range(len(strategy_keys)):
        for j in range(len(months_sorted)):
            val = matrix[i, j]
            if not np.isnan(val):
                color = "white" if abs(val) > 2 else s["muted"]
                ax.text(j, i, f"{val:+.1f}%", ha="center", va="center",
                        fontsize=9, color=color, fontweight="bold")

    # 컬러바
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("월별 수익률 (%)", color=s["muted"])
    cbar.ax.yaxis.set_tick_params(color=s["muted"])
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color=s["muted"])

    tf_label = "1시간봉" if timeframe_key == "1h" else "5분봉"
    ax.set_title(
        f"전략별 월별 수익률 히트맵 ({tf_label})",
        fontsize=13, fontweight="bold", pad=12, color=s["text"]
    )

    plt.tight_layout()
    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, f"heatmap_{timeframe_key}.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=s["bg"], edgecolor="none")
    plt.close()
    print(f"  [저장] {out_path}")
    return out_path


# ─────────────────────────────────────────────
# 3. 개별 거래 내역 CSV 저장
# ─────────────────────────────────────────────

def save_trades_csv(all_results: dict, timeframe_key: str,
                     save_dir: str = CSV_DIR):
    """전략별 개별 거래 내역을 CSV로 저장합니다."""
    os.makedirs(save_dir, exist_ok=True)
    saved = []

    for sk, result in all_results.items():
        if not result or not result.get("trades"):
            continue
        df_trades = trades_to_dataframe(result["trades"])
        if df_trades.empty:
            continue
        path = os.path.join(save_dir, f"trades_{sk}_{timeframe_key}.csv")
        df_trades.to_csv(path, index=False, encoding="utf-8-sig")
        saved.append(path)
        print(f"  [저장] {path} ({len(df_trades)}건)")

    return saved


# ─────────────────────────────────────────────
# 4. 최적 파라미터 요약표 CSV 저장
# ─────────────────────────────────────────────

def save_best_params_csv(best_params: dict, train_results: dict,
                          test_results: dict, timeframe_key: str,
                          save_dir: str = CSV_DIR):
    """
    각 전략의 최적 파라미터와 학습/검증 성과를 한 파일로 저장합니다.
    """
    os.makedirs(save_dir, exist_ok=True)
    rows = []

    for sk, params in best_params.items():
        row = {"strategy": sk, "strategy_label": STRATEGY_LABELS.get(sk, sk)}
        row.update({f"param_{k}": v for k, v in params.items()})

        # 학습 성과
        if sk in train_results and not train_results[sk].empty:
            top = train_results[sk].iloc[0]
            row["train_return_pct"]  = top.get("total_return_pct", "-")
            row["train_win_rate"]    = top.get("win_rate", "-")
            row["train_trades"]      = top.get("total_trades", "-")
            row["train_profit_factor"]= top.get("profit_factor", "-")
            row["train_mdd"]         = top.get("mdd", "-")
            row["train_sharpe"]      = top.get("sharpe", "-")

        # 검증 성과
        if sk in test_results and test_results[sk].get("metrics"):
            m = test_results[sk]["metrics"]
            row["test_return_pct"]   = m.get("total_return_pct", "-")
            row["test_win_rate"]     = m.get("win_rate", "-")
            row["test_trades"]       = m.get("total_trades", "-")
            row["test_profit_factor"]= m.get("profit_factor", "-")
            row["test_mdd"]          = m.get("mdd", "-")
            row["test_sharpe"]       = m.get("sharpe", "-")

        rows.append(row)

    df_params = pd.DataFrame(rows)
    path = os.path.join(save_dir, f"best_params_{timeframe_key}.csv")
    df_params.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  [저장] {path}")
    return path


# ─────────────────────────────────────────────
# 전체 리포트 생성 (외부 호출용)
# ─────────────────────────────────────────────

def generate_report(grid_output: dict, timeframe_key: str):
    """
    grid_search.py의 출력을 받아 모든 결과물을 한 번에 생성합니다.
    """
    print(f"\n── 리포트 생성 ({timeframe_key}) ──")

    test_results = grid_output["test_results"]
    best_params  = grid_output["best_params"]
    train_results = grid_output.get("train_results", {})

    # ① 대시보드 차트
    plot_dashboard(test_results, timeframe_key)

    # ② 월별 히트맵
    plot_monthly_heatmap(test_results, timeframe_key)

    # ③ 거래 내역 CSV
    save_trades_csv(test_results, timeframe_key)

    # ④ 최적 파라미터 CSV
    save_best_params_csv(best_params, train_results, test_results, timeframe_key)

    print(f"  ✓ 모든 결과물 저장 완료 → {OUTPUT_DIR}/")
