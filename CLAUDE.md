# 프로젝트 컨텍스트

## 프로젝트 경로
`/Users/seonminkim/Desktop/글로벌비전_프로젝트/quant_trading`

## 프로젝트 개요
XRP 스캘핑 자동매매 봇 (코빗 거래소, Maker 0% 수수료 활용)

- **현재 상태**: 룰 베이스 (조건문 기반) 6개 전략 + Walk-Forward 통계 검증
- **심볼**: XRPUSDT (Binance 공개 REST API로 데이터 수집, 매매는 코빗)
- **타임프레임**: 1h, 30m, 5m, 1m (4종)
- **백테스트 기간**: 2년 (`LOOKBACK_DAYS = 730`)
- **Walk-Forward 설정**: 학습 180일 / 검증 60일 (`WF_TRAIN_DAYS=180`, `WF_TEST_DAYS=60`)
- **언어**: Python
- **거래소**: 코빗 (Korbit) — Maker 0%, Taker 0.1%, 슬리피지 0.02%
- **개발 단계**: 봇 기본 구조 완성, 백테스팅/Walk-Forward/통계 검증/모니터링/텔레그램 알림 구현됨

## 운영 환경
- **서버**: Mac Studio (Apple M2 Max, 12코어, 32GB RAM)
- **목표**: Mac Studio를 24/7 서버로 사용해 봇 상시 가동
- **요구사항**: 자동으로 데이터 수집 → 학습 → 전략 수정까지 자가 진화

## 핵심 파일 구조
```
quant_trading/
├── main.py                  ← 실행 진입점
├── config.py                ← 설정값 (심볼, 타임프레임, 수수료, 그리드)
├── data_loader.py           ← Binance 공개 REST API 데이터 수집
├── indicators.py            ← EMA / RSI / VWAP / BB / MACD
├── strategies.py            ← 6개 전략 (룰 베이스)
├── backtest_engine.py       ← 백테스트 엔진 (진입가는 다음 봉 시가)
├── grid_search.py           ← 파라미터 최적화 (Walk-Forward)
├── stat_validation.py       ← Bootstrap CI / 통계 검증
├── fold_regime_analyzer.py  ← 폴드별 시장 국면 분석
├── reporter.py              ← 차트/CSV 결과
├── run_monitor.py           ← 모니터링 실행
├── research/
│   └── global_logic.md
└── monitor/
    ├── price_monitor.py
    ├── signal_monitor.py
    ├── news_monitor.py
    ├── trade_executor.py
    ├── telegram_bot.py
    └── scheduler.py
```

## 6개 전략 (현재 룰 베이스)

| 코드 | 전략명 | 진입 조건 (롱 기준) |
|------|--------|--------------------|
| **S1** | EMA 크로스 추세추종 | ① EMA 골든크로스 ② RSI < `rsi_long_max` ③ 가격 ≥ VWAP × (1−tol) |
| **S2** | VWAP 바운스 평균회귀 | ① 가격이 VWAP 상향 돌파 ② EMA fast 상승 ③ RSI 35~65 ④ 거래량 ≥ 평균 × `vol_mult` |
| **S3** | RSI 극단 역추세 | ① RSI가 `rsi_oversold` 상향 돌파 ② VWAP 근접 (`|price_vs_vwap|` ≤ tol) ③ EMA fast 상승 |
| **S4** | 3중 EMA 눌림매수 | ① EMA 정배열 (fast > slow > trend) ② RSI가 `rsi_reentry_long` 상향 돌파 ③ 가격 > VWAP |
| **S5** | 볼린저 스퀴즈 | ① 직전 캔들 squeeze → 현 캔들 해소 ② 가격 > BB 중간선 + VWAP ③ RSI 40~60 |
| **S6** | MACD 모멘텀 전환 | ① MACD 히스토그램 음→양 전환 ② 가격 > VWAP ③ RSI 35~65 ④ 거래량 ≥ 평균 × `vol_mult` |

전략 레지스트리: `STRATEGIES` 딕셔너리로 관리 (`strategies.py:248`).

### 전략별 그리드 오버라이드 (`config.py:STRATEGY_GRIDS`)
- **S2**: TP를 1.0~2.0%로 상향 (기본 0.3~5.0% 대신 0.010, 0.012, 0.015, 0.020)
- **S3**: VWAP 근접 허용 범위를 0.8~2.0%로 완화 (진입 조건 완화)
- **S4**: SL을 1.0~1.5%로 재그리드 (1시간봉 노이즈 대응)

### 최근 개선 사항 (git log 기준)
- 30분봉 타임프레임 추가
- 진입가를 종가 → **다음 봉 시가**로 수정 (룩어헤드 편향 제거)
- 통계 검증 추가 (`stat_validation.py`, Bootstrap CI 10,000회 / 95% 신뢰구간)
- 폴드별 결과 표시 (`fold_regime_analyzer.py`)
- 백테스트 기간 6개월 → 1년 → 2년으로 확장

---

# 진행 중인 논의 / 다음 단계

## 1. ML 전환 계획 (룰 베이스 → ML 하이브리드)

### 결정 사항
- **트레이딩에는 LLM보다 ML이 압도적으로 유리** (속도, 정확도, 메모리 효율)
- LLM (Hermes/Claude)은 보조 역할 (모니터링, 로그 분석, 코드 수정)
- ML 모델이 메인 두뇌 역할

### 단계별 로드맵
```
0단계: 데이터 수집/저장 (현재 진행 가능)
  - 가격 (1m, 5m, 1h봉)
  - 거래량, 호가창
  - 최소 3~6개월치 필요

1단계: 하이브리드 (룰 + ML 보조)
  - 기존 룰 유지
  - LightGBM이 "확률" 제공
  - 룰과 ML 모두 동의할 때만 매매

2단계: ML 메인 + 룰 보조
  - ML이 매매 신호 생성
  - 룰은 안전장치 역할

3단계: 강화학습 (자가 진화)
  - 실시간 학습
  - FinRL, Stable-Baselines3 활용
```

### 추천 ML 스택 (Mac Studio M2 Max 32GB 최적화)
- **LightGBM** (시작용, 가볍고 빠름)
- **XGBoost**
- **LSTM / Transformer** (시계열 예측)
- **MLX** (Apple Silicon 가속)
- **PyTorch + MPS backend**
- **Stable-Baselines3, FinRL** (강화학습)

### 첫 단계 구체 액션
```python
# "다음 1시간 가격 상승 여부" 예측 모델
import lightgbm as lgb

features = ['close', 'volume', 'rsi_14', 'macd', 'bb_upper', 'bb_lower', 'ema_20', ...]
target = 'price_up_1h'

model = lgb.LGBMClassifier()
model.fit(X_train, y_train)

# 정확도 55% 이상이면 실전 투입 고려
```

## 2. AI 에이전트 활용 계획

### 도구 분담
| 도구 | 역할 | 비용 |
|------|------|------|
| **Claude Code** (Max 플랜) | 봇 개발, 복잡한 로직, 새 전략 설계 | 구독 중 |
| **Hermes Agent** (검토 중) | 24/7 운영, 모니터링, 자동화 | OpenRouter 또는 Ollama 로컬 |
| **ML 모델** (LightGBM 등) | 핵심 예측 엔진 | $0 |

### Hermes Agent 도입 검토 결과
- **선택지**: OpenRouter (종량제) vs Ollama 로컬 무료
- **Mac Studio 32GB 한계**: 13B~14B 모델까지만 가능 (70B는 메모리 부족)
- **무료 모델로 가능한 것**: 로그 분석, 에러 감지, 단순 파라미터 조정, 알림
- **무료 모델로 어려운 것**: 복잡한 전략 코드 수정, 새 전략 설계
- **결론**: Hermes Agent는 "감시 + 알림 + 단순 자동화" 용도로만 사용

### 이상적인 아키텍처
```
Mac Studio (24/7)
├── 트레이딩 봇 (메인)
│   ├── ML 모델 (LightGBM 등) ← 핵심 예측
│   └── 거래 실행 로직
│
├── Hermes Agent (보조, 옵션)
│   ├── 로그 모니터링
│   ├── 뉴스 감성 분석
│   ├── 에러 자동 알림
│   └── 단순 파라미터 자동 조정
│
└── Claude Code (개발 시)
    └── 새 전략/모델 설계
```

---

# 사용자 정보
- **현재 가입 서비스**: Claude Max 플랜 사용 중
- **개발 환경**: Mac Studio M2 Max 32GB
- **선호**: 추가 비용 최소화, Max 플랜 활용 우선

---

# 이어서 작업할 것 (우선순위)

## 즉시 가능
1. **데이터 수집 파이프라인 강화**
   - 현재 `data_loader.py` 점검
   - ML 학습용 데이터 누적 시작 (가능하면 호가창, 펀딩비 등도)

2. **첫 ML 모델 (LightGBM) 프로토타입**
   - 기존 6개 전략의 신호를 ML 입력 feature로 활용
   - 백테스팅 결과를 학습 데이터로
   - "이 신호가 실제로 수익으로 이어질 확률" 예측

3. **하이브리드 전략 통합**
   - `strategies.py`에 ML confidence score 통합
   - 룰 + ML 동시 충족 시에만 매매

## 검토 필요
- Mac Studio 24/7 운영 환경 세팅 (launchd, systemd 등)
- 데이터베이스 도입 여부 (현재 어떻게 저장 중인지 확인 필요)
- 백테스트 결과를 ML 학습 데이터로 변환하는 로직

---

# 참고: 지난 대화 핵심 결론

1. **트레이딩 봇의 두뇌는 ML이 맡아야 함** (LLM 아님)
2. **LLM은 보조 역할** (코드 작성, 모니터링, 알림)
3. **Mac Studio 32GB**로는 ML은 여유, LLM은 13B 한계
4. **Claude Code + Hermes Agent + ML** 3중 구조가 이상적
5. **데이터 수집이 최우선** (ML의 연료)
