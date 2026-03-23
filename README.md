# XRP 스캘핑 6전략 백테스트 (코빗 Maker 0%)

## 프로젝트 구조

```
xrp_backtest/
├── main.py              ← 실행 진입점 (여기서 시작)
├── config.py            ← 모든 설정값 (수수료, 파라미터 범위 등)
├── data_loader.py       ← CryptoCompare API 데이터 수집
├── indicators.py        ← EMA / RSI / VWAP / BB / MACD 계산
├── strategies.py        ← 6개 전략 신호 생성
├── backtest_engine.py   ← 백테스트 엔진 (손익 계산, 에퀴티 곡선)
├── grid_search.py       ← 파라미터 최적화 (Walk-Forward)
├── reporter.py          ← 차트 / CSV 결과 저장
└── requirements.txt     ← 필요 패키지
```

## 설치

```bash
# 1. Python 3.9 이상 확인
python --version

# 2. 가상환경 생성 (선택, 권장)
python -m venv venv
source venv/bin/activate   # macOS / Linux
venv\Scripts\activate      # Windows

# 3. 패키지 설치
pip install -r requirements.txt

# 4. 한글 폰트 (Linux 사용 시)
sudo apt-get install -y fonts-noto-cjk
```

## 실행

```bash
# 기본 실행 (1h + 5m 둘 다, 6개월)
python main.py

# 1시간봉만
python main.py --tf 1h

# 5분봉만
python main.py --tf 5m

# API 재수집 (캐시 갱신)
python main.py --refresh

# 롱 포지션만 (숏 비활성화)
python main.py --no-short
```

## 결과물 위치

```
results/
├── charts/
│   ├── dashboard_1h.png       ← 전략 비교 대시보드 (1h)
│   ├── dashboard_5m.png       ← 전략 비교 대시보드 (5m)
│   ├── heatmap_1h.png         ← 월별 수익률 히트맵
│   └── heatmap_5m.png
└── csv/
    ├── trades_S1_EMA_Cross_1h.csv   ← 전략별 거래 내역
    ├── trades_S2_VWAP_Bounce_1h.csv
    ├── ...
    └── best_params_1h.csv           ← 최적 파라미터 요약표
```

## 6개 전략 요약

| 코드 | 전략명 | 핵심 아이디어 |
|------|--------|--------------|
| S1 | EMA 크로스 추세추종 | 골든크로스 발생 순간 + VWAP + RSI 필터 |
| S2 | VWAP 바운스 평균회귀 | VWAP 돌파 순간 + 거래량 확인 |
| S3 | RSI 극단 역추세 | RSI 과매도/과매수 탈출 + VWAP 근접 |
| S4 | 3중 EMA 눌림매수 | 정배열 상태 + RSI 눌림 후 재가속 |
| S5 | 볼린저 스퀴즈 | 밴드 수축 → 확장 폭발 방향 추종 |
| S6 | MACD 모멘텀 전환 | 히스토그램 전환 + 거래량 필터 |

## 주요 설정 변경 방법 (config.py)

```python
# 백테스트 기간 변경 (기본 180일)
LOOKBACK_DAYS = 180

# 수수료 (코빗 지정가 = 0%)
MAKER_FEE = 0.0000

# 초기 자본
INITIAL_CAPITAL = 10_000.0

# 그리드 서치 TP/SL 범위 추가
GRID["tp_pcts"] = [0.003, 0.005, 0.008, 0.012, 0.020, 0.030, 0.050]
```

## 소요 시간 예상

| 타임프레임 | 데이터 수집 | 그리드 서치 | 총계 |
|-----------|-----------|-----------|------|
| 1h (4,320캔들) | ~10초 | ~3분 | ~4분 |
| 5m (51,840캔들) | ~3분 | ~20분 | ~25분 |
| 둘 다 | - | - | ~30분 |

## 주의사항

- 백테스트 결과가 좋다고 실전에서도 좋다는 보장은 없습니다
- 최소 6개월 이상 데이터로 검증하고, 페이퍼 트레이딩을 먼저 하세요
- 코빗 XRP 유동성이 바이낸스 대비 얕아서 대량 주문 시 슬리피지 추가 발생 가능
- 승률 100%처럼 보이는 결과는 과적합(Overfitting) 가능성을 의심하세요
