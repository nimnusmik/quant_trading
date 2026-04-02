# =============================================================================
# main.py — 실행 진입점
#
# 사용법:
#   python main.py               # 1h + 5m 둘 다 실행 (기본값)
#   python main.py --tf 1h       # 1시간봉만
#   python main.py --tf 5m       # 5분봉만
#   python main.py --refresh     # 캐시 무시하고 API 재수집
#   python main.py --no-short    # 롱 포지션만 (숏 비활성화)
#
# 처음 실행 시:
#   1) pip install -r requirements.txt
#   2) python main.py
# =============================================================================

import argparse
import os
import time
from datetime import datetime

from config import TIMEFRAMES, OUTPUT_DIR, CHART_DIR, CSV_DIR
from data_loader import fetch_ohlcv, validate_data
from indicators import compute_all
from grid_search import run_all_grid_searches
from reporter import generate_report


def parse_args():
    parser = argparse.ArgumentParser(
        description="XRP 스캘핑 6전략 백테스트 (코빗 Maker 0% 기준)"
    )
    parser.add_argument(
        "--tf", choices=["1h", "5m", "1m", "both"],
        default="both",
        help="봉 단위 (기본값: both = 1h + 5m). 1m은 별도 지정)"
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="캐시 무시하고 API 재수집"
    )
    parser.add_argument(
        "--no-short", action="store_true",
        help="롱 포지션만 (숏 비활성화)"
    )
    return parser.parse_args()


def run_for_timeframe(timeframe_key: str, force_refresh: bool, allow_short: bool):
    """
    하나의 봉 단위에 대해 전체 파이프라인을 실행합니다.

    파이프라인:
      1. 데이터 수집 / 캐시 로드
      2. 데이터 품질 검사
      3. 지표 계산 (지표는 grid_search 내부에서 파라미터마다 다시 계산)
      4. Walk-Forward 그리드 서치
      5. 결과 리포트 생성
    """
    tf = TIMEFRAMES[timeframe_key]
    print(f"\n{'='*60}")
    print(f"  {tf['label']} 백테스트 시작")
    print(f"{'='*60}")
    t0 = time.time()

    # ── Step 1: 데이터 수집 ──────────────────────────
    df = fetch_ohlcv(timeframe_key, force_refresh=force_refresh)

    # ── Step 2: 데이터 품질 검사 ─────────────────────
    validate_data(df, timeframe_key)

    # ── Step 3: 그리드 서치 (Walk-Forward) ───────────
    grid_output = run_all_grid_searches(
        df,
        candles_per_day = tf["candles_per_day"],
    )

    # ── Step 4: 리포트 생성 ───────────────────────────
    generate_report(grid_output, timeframe_key)

    elapsed = time.time() - t0
    print(f"\n  ✓ {tf['label']} 완료 ({elapsed:.0f}초)")
    return grid_output


def print_final_summary(results: dict):
    """
    모든 타임프레임 결과를 최종 정리해서 콘솔에 출력합니다.
    """
    print(f"\n{'='*60}")
    print("  최종 결과 요약")
    print(f"{'='*60}")

    for tf_key, grid_output in results.items():
        tf_label = TIMEFRAMES[tf_key]["label"]
        print(f"\n[{tf_label}]")

        test_results = grid_output["test_results"]
        best_params  = grid_output["best_params"]

        # 수익률 기준 정렬
        ranked = sorted(
            [(sk, r) for sk, r in test_results.items()
             if r and r.get("metrics")],
            key=lambda x: x[1]["metrics"]["total_return_pct"],
            reverse=True,
        )

        if not ranked:
            print("  결과 없음")
            continue

        fold_metrics = grid_output.get("fold_metrics", {})
        n_folds      = grid_output.get("n_folds", 0)

        for rank, (sk, result) in enumerate(ranked, 1):
            m = result["metrics"]
            p = best_params.get(sk, {})
            pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float("inf") else "∞"

            # 폴드별 수익률 문자열
            fm = fold_metrics.get(sk, [])
            if fm:
                fold_str = " | 폴드 " + "/".join(
                    f"{f['total_return_pct']:+.1f}%" for f in fm
                )
            else:
                fold_str = ""

            print(
                f"  {rank}위 {sk:<20} "
                f"수익률 {m['total_return_pct']:+5.1f}% | "
                f"승률 {m['win_rate']:4.0f}% | "
                f"PF {pf_str:>6} | "
                f"MDD {m['mdd']:5.1f}% | "
                f"거래수 {m['total_trades']:3d}"
                f"{fold_str}"
            )

    print(f"\n결과 파일 위치:")
    print(f"  차트: {CHART_DIR}/")
    print(f"  CSV:  {CSV_DIR}/")
    print()


def main():
    args = parse_args()

    # 결과 디렉토리 생성
    for d in [OUTPUT_DIR, CHART_DIR, CSV_DIR]:
        os.makedirs(d, exist_ok=True)

    # 실행할 타임프레임 결정
    if args.tf == "both":
        timeframes_to_run = ["1h", "5m"]
    else:
        timeframes_to_run = [args.tf]

    # 1m 백테스트 경고: 캔들 수가 매우 많아 실행 시간이 길 수 있음
    if "1m" in timeframes_to_run:
        print(f"\n  ※ 1분봉 백테스트: 약 {180 * 1440:,}개 캔들 — 그리드 서치에 시간이 많이 걸릴 수 있습니다.")

    all_results = {}

    print(f"\n XRP 스캘핑 백테스트")
    print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" 타임프레임: {', '.join(timeframes_to_run)}")
    print(f" 숏 포지션: {'비활성화' if args.no_short else '활성화'}")
    print(f" 캐시 갱신: {'예' if args.refresh else '아니오 (캐시 있으면 재사용)'}")

    # 타임프레임별 실행
    for tf_key in timeframes_to_run:
        try:
            result = run_for_timeframe(
                tf_key,
                force_refresh = args.refresh,
                allow_short   = not args.no_short,
            )
            all_results[tf_key] = result
        except Exception as e:
            print(f"\n  [오류] {tf_key} 실행 중 예외 발생: {e}")
            import traceback
            traceback.print_exc()

    # 최종 요약 출력
    if all_results:
        print_final_summary(all_results)


if __name__ == "__main__":
    main()
