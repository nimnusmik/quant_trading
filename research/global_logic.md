# 🌍 AI 기반 가상화폐 자동매매 봇 — 글로벌 구현 현황 조사 보고서

**작성일:** 2026년 3월 26일  
**목적:** XRP 스캘핑 자동매매 봇 개발을 위한 기술 스택 및 오픈소스 생태계 조사  
**대상 독자:** 0318 회의 참석자 (대표님, 서민 개발자)

---

## 1. 전체 기술 스택 지도 (Technology Stack Map)

AI 자동매매 봇은 크게 **5개 레이어**로 구성됩니다. 각 레이어별로 전 세계에서 가장 널리 사용되는 도구를 정리했습니다.

### 레이어 구조

```
┌─────────────────────────────────────────────────┐
│  Layer 5: 모니터링 & 알림                          │
│  Telegram Bot API, Discord Webhook, Web UI       │
├─────────────────────────────────────────────────┤
│  Layer 4: AI/ML 의사결정 엔진                      │
│  FreqAI, PyTorch, TensorFlow, LLM (GPT/Claude)  │
├─────────────────────────────────────────────────┤
│  Layer 3: 전략 & 보조지표 계산                     │
│  TA-Lib, pandas-ta, ta, 자체 계산 모듈             │
├─────────────────────────────────────────────────┤
│  Layer 2: 데이터 수집 & 처리                       │
│  CCXT, WebSocket, pandas, numpy                  │
├─────────────────────────────────────────────────┤
│  Layer 1: 거래소 연동 & 주문 실행                   │
│  CCXT (REST/WebSocket), 거래소 자체 API            │
└─────────────────────────────────────────────────┘
```

---

## 2. 핵심 Python 패키지 상세 분석

### 2-1. CCXT (CryptoCurrency eXchange Trading Library) ⭐ 필수

| 항목 | 내용 |
|------|------|
| **GitHub** | github.com/ccxt/ccxt |
| **Stars** | 35,000+ |
| **지원 거래소** | 107개 이상 (바이낸스, 바이비트, 코빗 등) |
| **언어** | Python, JavaScript, TypeScript, PHP, C#, Go |
| **핵심 기능** | 통합 API로 거래소 간 코드 변경 없이 전환 가능 |

**우리 프로젝트와의 연관성:**
- 코빗(Korbit) API를 CCXT를 통해 연동 가능
- `fetch_ohlcv()`로 캔들 데이터 수집, `create_order()`로 지정가 주문 실행
- WebSocket 지원으로 실시간 시세 스트리밍 가능

**기본 사용 예시:**
```python
import ccxt

exchange = ccxt.korbit({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET_KEY',
    'enableRateLimit': True,  # API Rate Limit 자동 관리
})

# OHLCV 데이터 수집 (30분봉)
ohlcv = exchange.fetch_ohlcv('XRP/KRW', '30m', limit=100)

# 지정가 매수 주문
order = exchange.create_order('XRP/KRW', 'limit', 'buy', amount, price)
```

### 2-2. 보조지표 계산 라이브러리 비교

| 패키지 | 지표 수 | 설치 난이도 | 속도 | 추천 용도 |
|--------|---------|------------|------|----------|
| **TA-Lib** | 150+ (캔들 패턴 포함) | 어려움 (C 라이브러리 별도 설치 필요) | 매우 빠름 | 프로덕션 환경, 고성능 필요 시 |
| **pandas-ta** | 130+ | 쉬움 (pip install) | 보통 | pandas와 자연스럽게 통합 |
| **ta** | 80+ | 쉬움 (pip install) | 보통 | 빠른 프로토타이핑 |

**0318 회의에서 논의된 지표 구현 가능 여부:**

| 회의 지표 | TA-Lib | pandas-ta | ta |
|-----------|--------|-----------|-----|
| RSI | ✅ | ✅ | ✅ |
| 볼린저 밴드 | ✅ | ✅ | ✅ |
| 이동평균선 (SMA/EMA) | ✅ | ✅ | ✅ |
| 일목균형표 (Ichimoku) | ✅ | ✅ | ✅ |
| DMI/ADX | ✅ | ✅ | ✅ |
| MACD | ✅ | ✅ | ✅ |
| 매물대 (Volume Profile) | ❌ | ✅ | ❌ |
| 이격도 (Disparity) | ❌ (직접 구현) | ✅ | ❌ (직접 구현) |
| 심리도/신심리도 | ❌ (직접 구현) | ❌ (직접 구현) | ❌ (직접 구현) |

**결론:** `pandas-ta`가 가장 많은 지표를 커버하면서도 설치가 쉽습니다. 성능이 중요해지면 TA-Lib으로 전환을 고려할 수 있습니다.

### 2-3. 데이터 처리 & 기타 필수 패키지

| 패키지 | 용도 | 필수 여부 |
|--------|------|----------|
| **pandas** | OHLCV 시계열 데이터 처리 | 필수 |
| **numpy** | 수치 계산, 배열 연산 | 필수 |
| **python-dotenv** | API 키 보안 관리 (.env 파일) | 필수 |
| **websocket-client** | 실시간 시세 스트리밍 | 필수 |
| **schedule / APScheduler** | 주기적 작업 스케줄링 | 필수 |
| **SQLite / PostgreSQL** | 거래 기록, 점수 DB 저장 | 필수 |
| **matplotlib / plotly** | 차트 시각화, 백테스트 결과 | 선택 |
| **requests** | 외부 API 호출 (뉴스, Fear & Greed 등) | 필수 |

---

## 3. 주요 오픈소스 트레이딩 봇 프레임워크

### 3-1. Freqtrade ⭐⭐⭐ (가장 추천)

| 항목 | 내용 |
|------|------|
| **GitHub** | github.com/freqtrade/freqtrade |
| **Stars** | 39,900+ (1위) |
| **언어** | Python 3.11+ |
| **라이선스** | GPL-3.0 (무료) |
| **거래소** | CCXT 기반 100개+ 거래소 지원 |

**왜 가장 추천하는가:**

1. **FreqAI 모듈 내장:** ML 모델을 전략에 바로 통합 가능합니다.
   - LightGBM, XGBoost, CatBoost (그래디언트 부스팅)
   - PyTorch 기반 MLP, LSTM 등 딥러닝 모델
   - 강화학습 (Reinforcement Learning) 에이전트
   - 실시간 자동 재훈련 — 시장 변화에 적응하는 모델 구축 가능

2. **완전한 개발 파이프라인:**
   - 전략 작성 → 백테스트 → 하이퍼파라미터 최적화 → 페이퍼 트레이딩 → 라이브 트레이딩

3. **운영 편의:**
   - 텔레그램 봇으로 원격 제어 및 모니터링
   - Web UI 내장
   - Docker 지원으로 서버 배포 용이

4. **우리 프로젝트 적합성:**
   - 0318 회의의 "3단계 판단 프로세스"를 Freqtrade 전략 클래스로 구현 가능
   - ABC 그룹 가중치 점수 시스템을 `populate_indicators()`에서 계산 가능
   - DCA(분할매수) 전략을 내장 기능으로 지원

### 3-2. Jesse ⭐⭐

| 항목 | 내용 |
|------|------|
| **GitHub** | github.com/jesse-ai/jesse |
| **Stars** | 6,500+ |
| **특징** | 백테스트 정확도에 특화, JesseGPT (AI 전략 작성 도우미) |
| **장점** | zero look-ahead bias 백테스트, Optuna 기반 파라미터 최적화 |
| **단점** | Freqtrade 대비 커뮤니티 규모 작음, 일부 기능 유료 |

**우리 프로젝트와의 연관성:**
- JesseGPT를 활용하면 Python 지식이 부족해도 전략 코드 작성 가능
- 백테스트 정확도가 높아 전략 검증에 유리

### 3-3. OctoBot ⭐⭐

| 항목 | 내용 |
|------|------|
| **GitHub** | github.com/Drakkar-Software/OctoBot |
| **Stars** | 4,000+ |
| **특징** | Web UI가 뛰어남, AI/Grid/DCA 전략 내장 |
| **지원 거래소** | 바이낸스, Hyperliquid 등 15개+ |
| **장점** | 초보자 친화적 UI, TradingView 시그널 연동 |
| **단점** | 코빗 미지원 (CCXT 커스텀 연동 필요) |

### 3-4. Hummingbot ⭐

| 항목 | 내용 |
|------|------|
| **GitHub** | github.com/hummingbot/hummingbot |
| **Stars** | 8,500+ |
| **특징** | 마켓 메이킹 / 차익거래 특화 |
| **특이사항** | MCP(Model Context Protocol) 지원 — Claude, Gemini 같은 AI 어시스턴트와 연동 가능 |
| **장점** | DEX(탈중앙 거래소)도 지원, 고빈도 거래에 적합 |
| **단점** | 스캘핑보다는 마켓 메이킹에 더 최적화됨 |

### 3-5. Superalgos

| 항목 | 내용 |
|------|------|
| **GitHub** | github.com/Superalgos/Superalgos |
| **Stars** | 4,200+ |
| **특징** | 협업 기반 트레이딩 인텔리전스 플랫폼 |
| **장점** | 시각적 전략 빌더, 커뮤니티 전략 공유 |
| **단점** | Node.js 기반이라 Python 생태계와 분리됨 |

---

## 4. AI/ML 접근 방식별 분류

전 세계 AI 트레이더들이 사용하는 접근 방식을 크게 4가지로 분류할 수 있습니다.

### 4-1. 규칙 기반 + 보조지표 (Traditional Rule-Based)

**가장 보편적인 방식입니다. 우리 프로젝트의 기본 전략과 일치합니다.**

- RSI, 볼린저밴드, 이동평균선 등 보조지표의 조건 조합으로 매수/매도 신호 생성
- if-else 로직으로 구현, 가장 이해하기 쉽고 디버깅이 용이
- 사용 도구: CCXT + TA-Lib/pandas-ta + pandas

**우리 프로젝트 적용:**
- 0318 회의의 "5점 척도 평가 체계"가 이 방식에 해당
- A그룹(기술적 지표 70%) + B그룹(거시적 동향 20%) + C그룹(유가/원자재 10%)

### 4-2. 머신러닝 기반 예측 (ML-Based Prediction)

**보조지표를 "특성(feature)"으로 사용하여 ML 모델이 매수/매도를 예측합니다.**

| ML 모델 | 프레임워크 | 특징 | 난이도 |
|---------|-----------|------|--------|
| LightGBM | FreqAI 내장 | 빠른 학습, 테이블 데이터에 강함 | 중 |
| XGBoost | FreqAI 내장 | LightGBM과 유사, 정확도 약간 높음 | 중 |
| CatBoost | FreqAI 내장 | 범주형 데이터 처리 우수 | 중 |
| LSTM | PyTorch/TF | 시계열 패턴 학습 | 상 |
| Transformer | PyTorch | 최신 아키텍처, 장기 의존성 포착 | 최상 |

**FreqAI를 통한 적응형 모델:**
- 자동으로 주기적 재훈련을 수행하여 변화하는 시장에 적응
- 사용자가 정의한 보조지표를 feature set으로 자동 변환
- 예측 신뢰도 점수를 함께 제공하여 불확실한 구간에서 거래를 회피 가능

### 4-3. 강화학습 기반 (Reinforcement Learning)

**에이전트가 "매수/매도/홀드" 행동을 시행착오로 학습합니다.**

주요 오픈소스 프로젝트:
- **RLTrader** (github.com/notadamking/RLTrader): PPO2 알고리즘 + Bayesian Optimization
- **crypto-rl** (github.com/sadighian/crypto-rl): DQN 알고리즘 + 호가창 데이터 활용
- **FreqAI RL 모듈**: Freqtrade에 내장된 강화학습 지원

주로 사용되는 RL 알고리즘:
- PPO (Proximal Policy Optimization) — 안정적인 학습, 가장 인기
- DQN / DDQN (Double Deep Q-Network) — 이산적 행동 공간에 적합
- A2C/A3C — 병렬 학습 가능

**현실적 평가:**
- 백테스트에서는 좋은 성과를 보이지만, 실제 라이브 트레이딩에서는 시장 레짐 변화에 취약
- 학습에 방대한 데이터와 컴퓨팅 파워 필요
- 우리 프로젝트의 2개월 베타 일정에는 과도할 수 있으므로, **2차 고도화 단계에서 도입 검토**를 권장

### 4-4. LLM 기반 멀티에이전트 (최신 트렌드) 🔥

**가장 최신이자 가장 빠르게 성장하는 영역입니다.**

#### TradingAgents (github.com/TauricResearch/TradingAgents)

실제 트레이딩 펌의 구조를 모방한 멀티 LLM 에이전트 프레임워크입니다:

| 에이전트 역할 | 하는 일 |
|-------------|---------|
| **Fundamental Analyst** | 기본적 분석 (재무, 온체인 데이터) |
| **Sentiment Analyst** | SNS/뉴스 감성 분석 |
| **Technical Analyst** | RSI, MACD 등 기술적 분석 |
| **Bull Researcher** | 매수 근거 주장 |
| **Bear Researcher** | 매도 근거 주장 |
| **Trader** | 최종 매매 결정 |
| **Risk Manager** | 포트폴리오 리스크 평가 |

GPT-5, Gemini, Claude 4, Grok 등 다양한 LLM 프로바이더를 지원하며, LangGraph를 기반으로 에이전트 간 워크플로를 관리합니다.

#### LLM_trader (github.com/qrak/LLM_trader)

"Council of Models" 아키텍처를 사용하는 실전 트레이딩 봇입니다:
- Visual Cortex Analyst: 차트 이미지를 LLM Vision으로 분석
- Technical Specialist: 보조지표 기반 분석
- Sentiment Scout: 뉴스/매크로 감성 분석
- Memory Historian: 과거 트레이드 패턴을 벡터 DB에서 검색
- 여러 에이전트가 합의(consensus)하여 최종 시그널을 생성

#### Sibyl (github.com/nMaroulis/sibyl)

AI 기반 암호화폐 분석 & 거래 대시보드입니다:
- Oracle: LLM 기반 인텔리전스 레이어 (실시간 감성 분석, 전략 제안)
- Chronos: TensorFlow Bi-LSTM, GTU, ARIMA 기반 가격 예측 모듈
- RAG 시스템으로 암호화폐 관련 문서 기반 질의응답

**우리 프로젝트와의 연관성:**
- 0318 회의에서 논의한 "Perplexity로 시세/동향 분석" 역할을 LLM 에이전트가 대체 가능
- B그룹(거시적 동향)과 C그룹(유가/원자재)의 점수화를 LLM이 자동 수행 가능
- 다만 API 비용이 발생하므로, 호출 빈도를 신중히 설계해야 함

---

## 5. 감성 분석 (Sentiment Analysis) 도구

0318 회의에서 "XRP 관련 뉴스와 규제 동향"을 10점 만점으로 평가하여 DB에 축적하겠다는 방안이 논의되었습니다. 이를 자동화할 수 있는 도구들을 소개합니다.

### 5-1. 금융 특화 감성 분석 모델

| 모델 | 제공 | 특징 |
|------|------|------|
| **FinBERT** | ProsusAI (HuggingFace) | 금융 뉴스에 특화된 BERT 모델, 무료 |
| **GPT-4 Fine-tuned** | OpenAI | 암호화폐 뉴스 감성 분류 정확도 최고 수준 |
| **CryptoBERT** | HuggingFace | 암호화폐 트윗/뉴스 전용 감성 모델 |

### 5-2. 시장 심리 데이터 소스

| 소스 | 데이터 | API 여부 |
|------|--------|---------|
| **Fear & Greed Index** | 0~100 시장 공포/탐욕 지수 | 무료 API |
| **LunarCrush** | SNS 감성, 영향력자 활동 추적 | 유료 API |
| **Santiment** | 온체인 + 소셜 + 개발 활동 데이터 | 유료 API |
| **CryptoCompare** | 뉴스 + 소셜 데이터 | 무료/유료 |

---

## 6. 우리 프로젝트에 최적화된 기술 스택 추천

### 6-1. Phase 1: 베타 버전 (2개월 목표)

**"빠른 베타 출시 후 테스트하며 보완"이라는 대표님의 개발 철학에 맞춰 구성했습니다.**

```
필수 패키지:
├── ccxt              → 코빗 거래소 연동
├── pandas + numpy    → 데이터 처리
├── pandas-ta         → 보조지표 계산 (10개+)
├── python-dotenv     → API 키 보안 관리
├── websocket-client  → 실시간 시세 수신
├── APScheduler       → 주기적 작업 스케줄링
├── sqlite3 (내장)    → 거래 기록/점수 DB
├── requests          → Fear & Greed Index 등 외부 데이터
└── python-telegram-bot → 알림 및 원격 제어
```

**requirements.txt 예시:**
```
ccxt>=4.2.0
pandas>=2.1.0
numpy>=1.24.0
pandas-ta>=0.3.14
python-dotenv>=1.0.0
websocket-client>=1.6.4
APScheduler>=3.10.4
requests>=2.31.0
python-telegram-bot>=20.7
```

### 6-2. Phase 2: 고도화 (3~6개월)

```
추가 패키지:
├── freqtrade         → 프레임워크 전환 (백테스트, 하이퍼옵트)
├── FreqAI            → ML 모델 통합 (LightGBM, XGBoost)
├── TA-Lib            → 고성능 지표 계산으로 전환
├── transformers      → FinBERT 감성 분석
├── langchain         → LLM 에이전트 파이프라인
└── plotly/dash       → 대시보드 구축
```

### 6-3. Phase 3: 풀 AI 시스템 (6개월+)

```
고급 패키지:
├── PyTorch           → LSTM/Transformer 가격 예측
├── stable-baselines3 → 강화학습 에이전트
├── optuna            → 하이퍼파라미터 최적화
├── chromadb          → 벡터 DB (LLM 메모리)
└── FastAPI           → 자체 API 서버
```

---

## 7. 프레임워크 선택 의사결정 매트릭스

| 평가 기준 (가중치) | 직접 구축 (CCXT+) | Freqtrade | Jesse | OctoBot |
|-------------------|-------------------|-----------|-------|---------|
| 개발 속도 (30%) | ★★★★☆ | ★★★★★ | ★★★★☆ | ★★★☆☆ |
| 커스터마이징 자유도 (25%) | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★☆☆ |
| ML/AI 통합 용이성 (20%) | ★★★☆☆ | ★★★★★ | ★★★★☆ | ★★☆☆☆ |
| 코빗 거래소 지원 (15%) | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ |
| 커뮤니티/문서화 (10%) | ★★☆☆☆ | ★★★★★ | ★★★★☆ | ★★★☆☆ |
| **가중 총점** | **3.95** | **4.55** | **3.85** | **2.75** |

---

## 8. 핵심 리스크 및 주의사항

### 8-1. 기술적 리스크

| 리스크 | 설명 | 대응 방안 |
|--------|------|----------|
| **API Rate Limit** | 코빗 API 호출 제한 초과 시 차단 | CCXT의 `enableRateLimit: True` 사용 + 재시도(Retry) 로직 구현 |
| **슬리피지 (Slippage)** | 주문 시점과 체결 시점의 가격 차이 | 지정가 주문 전용 (0318 회의 결정 사항과 일치) |
| **WebSocket 연결 끊김** | 실시간 시세 수신 중단 | 자동 재연결 로직 + heartbeat 모니터링 |
| **서버 다운** | 봇이 돌아가는 서버 장애 | 클라우드 서버 (AWS/GCP) + 모니터링 알림 |
| **과적합 (Overfitting)** | ML 모델이 과거 데이터에만 최적화 | Walk-forward 검증 + 주기적 재훈련 |

### 8-2. 운영적 리스크

- **LLM API 비용:** GPT-4/Claude API를 초 단위로 호출하면 비용이 급증합니다. 회의에서 논의된 "LLM 과다 사용 지양"은 매우 적절한 판단입니다.
- **거래소 점검:** 코빗 정기 점검 시 봇 자동 중단 로직 필요
- **규제 변동:** XRP 관련 SEC 소송 등 갑작스러운 규제 변화에 대한 뉴스 모니터링 자동화

---

## 9. 최종 추천 로드맵

```
[1개월차] 기반 구축
  ├── CCXT + 코빗 연동 + 주문 실행 모듈
  ├── pandas-ta 기반 보조지표 계산 엔진
  ├── 5점 척도 점수화 시스템 (A/B/C 그룹)
  └── SQLite DB + 기본 텔레그램 알림

[2개월차] 베타 출시
  ├── 3단계 판단 프로세스 구현
  ├── A/B/C 전략 자동 전환
  ├── DCA 분할매수 모듈
  └── 페이퍼 트레이딩 검증

[3~4개월차] 고도화
  ├── Freqtrade 프레임워크 전환 검토
  ├── FreqAI로 LightGBM 예측 모델 추가
  ├── FinBERT 기반 뉴스 감성 분석 자동화
  └── 백테스트 자동화 파이프라인

[5~6개월차] 풀 AI 시스템
  ├── LLM 에이전트 (B/C 그룹 자동 점수화)
  ├── 강화학습 에이전트 실험
  ├── 대시보드 (Plotly/Dash)
  └── 멀티 코인 확장 (이더리움 등)
```

---

## 10. 참고 오픈소스 프로젝트 리스트

| 프로젝트 | GitHub URL | Stars | 핵심 특징 |
|---------|------------|-------|----------|
| Freqtrade | freqtrade/freqtrade | 39.9k | ML 통합, 백테스트, 텔레그램 |
| CCXT | ccxt/ccxt | 35k+ | 107개 거래소 통합 API |
| Hummingbot | hummingbot/hummingbot | 8.5k | 마켓 메이킹, MCP/AI 연동 |
| Jesse | jesse-ai/jesse | 6.5k | 정밀 백테스트, JesseGPT |
| OctoBot | Drakkar-Software/OctoBot | 4k+ | Grid/DCA 내장, Web UI |
| Superalgos | Superalgos/Superalgos | 4.2k | 협업 기반, 시각적 빌더 |
| TradingAgents | TauricResearch/TradingAgents | 신규 | 멀티 LLM 에이전트 |
| LLM_trader | qrak/LLM_trader | 신규 | Vision AI 차트 분석 |
| Sibyl | nMaroulis/sibyl | 신규 | RAG + LSTM 예측 |
| awesome-ai-in-finance | georgezouq/awesome-ai-in-finance | 대형 | AI 금융 도구 종합 목록 |

---

*본 문서는 2026년 3월 26일 기준으로 조사된 내용입니다. 오픈소스 프로젝트의 특성상 빠르게 변화할 수 있으므로, 주요 결정 전 최신 상태를 재확인하시기 바랍니다.*