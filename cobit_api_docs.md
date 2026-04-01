# 코빗 Open API 문서

> **REST API 기본 URL:** `https://api.korbit.co.kr`  
> **WebSocket Public URL:** `wss://ws-api.korbit.co.kr/v2/public`  
> **WebSocket Private URL:** `wss://ws-api.korbit.co.kr/v2/private`

---

## 목차

1. [소개](#1-소개)
2. [API 키 생성 및 관리](#2-api-키-생성-및-관리)
3. [REST API 일반](#3-rest-api-일반)
4. [인증 (서명된 요청 보내기)](#4-인증-서명된-요청-보내기)
   - [HMAC-SHA256 서명](#41-hmac-sha256-서명)
   - [ED25519 서명](#42-ed25519-서명)
5. [시세 API (Public)](#5-시세-api-public)
   - [현재가 조회](#51-현재가-조회)
   - [호가 조회](#52-호가-조회)
   - [최근 체결 내역](#53-최근-체결-내역)
   - [캔들스틱 조회](#54-캔들스틱-조회)
   - [거래지원 목록 조회](#55-거래지원-목록-조회)
   - [호가 정책 조회](#56-호가-정책-조회)
6. [주문 API (Private)](#6-주문-api-private)
   - [개별 주문 조회](#61-개별-주문-조회)
   - [미체결 주문 조회](#62-미체결-주문-조회)
   - [최근 주문 내역 조회](#63-최근-주문-내역-조회)
   - [최근 체결 내역 조회](#64-최근-체결-내역-조회)
   - [주문하기](#65-주문하기)
   - [주문 취소하기](#66-주문-취소하기)
7. [자산 API (Private)](#7-자산-api-private)
   - [자산 현황](#71-자산-현황)
8. [가상자산 입금](#8-가상자산-입금)
   - [입금 주소 전체 조회](#81-입금-주소-전체-조회)
   - [입금 주소 조회](#82-입금-주소-조회)
   - [입금 주소 생성](#83-입금-주소-생성)
   - [최근 입금내역 조회](#84-최근-입금내역-조회)
   - [입금 진행상황 조회](#85-입금-진행상황-조회)
9. [가상자산 출금](#9-가상자산-출금)
   - [출금 가능 주소 목록 조회](#91-출금-가능-주소-목록-조회)
   - [출금 가능 수량 조회](#92-출금-가능-수량-조회)
   - [출금 요청](#93-출금-요청)
   - [출금 취소](#94-출금-취소)
   - [최근 출금내역 조회](#95-최근-출금내역-조회)
   - [출금 진행상황 조회](#96-출금-진행상황-조회)
10. [원화 입출금](#10-원화-입출금)
    - [입금 요청](#101-입금-요청)
    - [출금 요청](#102-출금-요청)
    - [최근 입금내역 조회](#103-최근-입금내역-조회)
    - [최근 출금내역 조회](#104-최근-출금내역-조회)
11. [기타 API](#11-기타-api)
    - [가상자산 정보 조회](#111-가상자산-정보-조회)
    - [서버 시각 조회](#112-서버-시각-조회)
    - [거래수수료율 조회](#113-거래수수료율-조회)
    - [API 키 정보 조회](#114-api-키-정보-조회)
12. [WebSocket API](#12-websocket-api)
    - [연결 및 인증](#121-연결-및-인증)
    - [현재가 (Ticker)](#122-현재가-ticker)
    - [호가 (Orderbook)](#123-호가-orderbook)
    - [체결 (Trade)](#124-체결-trade)
    - [내 주문 (MyOrder)](#125-내-주문-myorder)
    - [내 체결 (MyTrade)](#126-내-체결-mytrade)
    - [내 자산 (MyAsset)](#127-내-자산-myasset)

---

## 1. 소개

코빗 Open API를 통해 가상자산 시세 조회, 주문, 입출금 등 거래소의 다양한 기능을 자유롭게 이용할 수 있습니다.

- **Public API**: 누구나 사용 가능 (API 키 불필요)
- **Private API**: 코빗 회원 전용 (API 키 + 서명 인증 필요)

> 코빗 Open API는 **비동기 시스템**으로, 응답 데이터에 약간의 지연이 있을 수 있습니다.  
> 한글 API 문서와 영문 API 문서 간 차이가 있는 경우, **한글 문서가 우선**합니다.

---

## 2. API 키 생성 및 관리

### API 키 생성

개발자센터에서 API 키 생성 시 인증 방식을 선택합니다.

| 방식 | 설명 |
|------|------|
| **HMAC-SHA256** | 코빗이 Secret Key를 생성하여 제공 |
| **ED25519** | 사용자가 직접 Key Pair를 생성하고 Public Key를 코빗에 제공 |

**ED25519 키 페어 생성 (Node.js)**
```js
import { generateKeyPairSync } from "crypto";

const { publicKey, privateKey } = generateKeyPairSync("ed25519", {
  publicKeyEncoding: { type: "spki", format: "pem" },
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
});
console.log(publicKey, privateKey);
```

**ED25519 키 페어 생성 (OpenSSL)**
```bash
# 개인 키 생성
openssl genpkey -algorithm ED25519 -out private_key.pem
# 공개 키 변환
openssl pkey -in private_key.pem -pubout -out public_key.pem
```

### API 키 관리

- 유효 기간: 생성 시점으로부터 **1년**
- IP 주소 제한: 키당 최대 **20개** IP 설정 가능
- 권한 변경 후 반영까지 **최대 1분** 소요

**Private API 권한 목록**

| 권한 | 설명 |
|------|------|
| 자산 조회 | 보유 자산 조회 |
| 주문 조회 | 주문 내역 조회 |
| 주문 신청 | 주문 생성 및 취소 |
| 입금 조회 | 입금 내역 조회 |
| 입금 신청 | 입금 주소 생성 등 |
| 출금 조회 | 출금 내역 조회 |
| 출금 신청 | 출금 요청 |

---

## 3. REST API 일반

### 요청 방식

| HTTP 메소드 | 파라미터 전달 방식 |
|-------------|-------------------|
| `GET`, `DELETE` | URL 쿼리 스트링 (Query String) |
| `POST` | 요청 본문 (`application/x-www-form-urlencoded`) |

- 응답 형식: **JSON**
- 시간 단위: **Unix Timestamp (밀리초)**

### 요청 수 제한 (Rate Limit)

| 대상 | 기준 | 제한 |
|------|------|------|
| Public API | IP 주소 | 초당 50회 |
| 주문하기 | 회원 계정 | 초당 30회 |
| 주문 취소하기 | 회원 계정 | 초당 30회 |
| 입출금 신청 | 회원 계정 | 초당 5회 |
| 그 외 Private API | 회원 계정 | 초당 50회 |

**응답 헤더 예시**
```
# 200 OK
Ratelimit: limit=50, remaining=48, reset=1
Ratelimit-Policy: 50;w=1

# 429 Too Many Requests
Retry-After: 1
Ratelimit-Policy: 30;w=1
```

---

## 4. 인증 (서명된 요청 보내기)

Private API 요청 시 `signature`와 `timestamp`를 반드시 포함해야 합니다.

### 시간 정보

- `timestamp`: 현재 시각의 Unix Timestamp (밀리초 단위), **필수**
- `recvWindow`: 요청 유효 시간 (기본값: `5000`ms, 최대: `60000`ms), 선택
- 서버 시각은 `GET /v2/time`으로 확인 가능

```
// 요청 처리 조건
if (serverTime - timestamp <= recvWindow && timestamp < serverTime + 1000) {
  // 요청 처리
} else {
  // 요청 거부 (EXCEED_TIME_WINDOW 에러)
}
```

### 4.1 HMAC-SHA256 서명

1. 요청 변수를 Query String 형태로 조합 (예: `symbol=btc_krw&side=buy&timestamp=...`)
2. Secret Key로 HMAC-SHA256 서명 생성 (hex 인코딩)
3. `signature` 파라미터에 추가
4. HTTP 헤더에 `X-KAPI-KEY` 포함하여 요청

```js
import crypto from "crypto";

const apiKey = "YOUR_API_KEY";
const apiSecret = "YOUR_SECRET_KEY";

const createHmacSignature = (query) => {
  return crypto.createHmac("sha256", apiSecret).update(query, "utf-8").digest("hex");
};

// POST 요청 예시 (주문하기)
const placeOrder = async (symbol, side, price, qty, orderType, timeInForce) => {
  const timestamp = Date.now();
  const params = new URLSearchParams({ symbol, side, price, qty, orderType, timeInForce, timestamp });
  const signature = createHmacSignature(params.toString());
  params.append("signature", signature);

  const response = await fetch("https://api.korbit.co.kr/v2/orders", {
    method: "POST",
    headers: {
      "X-KAPI-KEY": apiKey,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
  });
  return response.json();
};
```

### 4.2 ED25519 서명

1. 요청 변수를 Query String 형태로 조합
2. 개인 키(Private Key)로 ED25519 서명 생성 후 **Base64 인코딩**
3. `signature` 파라미터에 추가 (URL 인코딩 주의)
4. HTTP 헤더에 `X-KAPI-KEY` 포함하여 요청

```js
import crypto from "crypto";

const apiKey = "YOUR_API_KEY";
const privateKeyPem = `-----BEGIN PRIVATE KEY-----
YOUR_PRIVATE_KEY_HERE
-----END PRIVATE KEY-----`;

const createEd25519Signature = (data) => {
  const messageBuffer = Buffer.from(data);
  const signature = crypto.sign(null, messageBuffer, { key: privateKeyPem });
  return signature.toString("base64");
};
```

> **주의**: URL 쿼리스트링과 요청 본문에 변수가 각각 있을 경우, 두 문자열을 `&` 없이 그대로 이어 붙여 서명합니다.

---

## 5. 시세 API (Public)

### 5.1 현재가 조회

`GET /v2/tickers`

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 선택 | 거래쌍 심볼. 콤마로 구분하여 다중 조회 가능. 미입력 시 전체 조회 |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `symbol` | string | 거래쌍 |
| `open` | string | 최근 24시간 시가 |
| `high` | string | 최근 24시간 고가 |
| `low` | string | 최근 24시간 저가 |
| `close` | string | 최근 24시간 종가 |
| `prevClose` | string | 직전 24시간 종가 |
| `priceChange` | string | 직전 종가 대비 가격 변화량 |
| `priceChangePercent` | string | 직전 종가 대비 가격 변화율 (%) |
| `volume` | string | 최근 24시간 거래량 (가상자산) |
| `quoteVolume` | string | 최근 24시간 거래대금 (원화) |
| `bestBidPrice` | string | 매수 1호가 |
| `bestAskPrice` | string | 매도 1호가 |
| `lastTradedAt` | number | 마지막 체결 시각 (Unix ms) |

```bash
curl 'https://api.korbit.co.kr/v2/tickers?symbol=btc_krw,eth_krw'
```

```json
{
  "success": true,
  "data": [
    {
      "symbol": "btc_krw",
      "open": "77060000",
      "high": "79650000",
      "low": "76550000",
      "close": "77136000",
      "prevClose": "77060000",
      "priceChange": "76000",
      "priceChangePercent": "0.1",
      "volume": "48.73739983",
      "quoteVolume": "3785149733.32633",
      "bestBidPrice": "77136000",
      "bestAskPrice": "77193000",
      "lastTradedAt": 1725525721041
    }
  ]
}
```

---

### 5.2 호가 조회

`GET /v2/orderbook`

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `level` | string | 선택 | 오더북 모아보기 단위 |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `timestamp` | number | 호가 정보 기준 시각 (Unix ms) |
| `bids` | array | 매수 호가 목록 (호가 내림차순) |
| `asks` | array | 매도 호가 목록 (호가 오름차순) |
| `bids[].price` | string | 매수호가 |
| `bids[].qty` | string | 매수잔량 |
| `asks[].price` | string | 매도호가 |
| `asks[].qty` | string | 매도잔량 |

```bash
curl 'https://api.korbit.co.kr/v2/orderbook?symbol=btc_krw'
```

---

### 5.3 최근 체결 내역

`GET /v2/trades`

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `limit` | number | 선택 | 최대 조회 건수 (1~500) |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `timestamp` | number | 체결 시각 (Unix ms) |
| `price` | string | 체결 가격 |
| `qty` | string | 체결량 |
| `isBuyerTaker` | boolean | 매수 주문으로 인한 체결 여부 |
| `tradeId` | number | 거래 체결 ID |

```bash
curl 'https://api.korbit.co.kr/v2/trades?symbol=btc_krw&limit=4'
```

---

### 5.4 캔들스틱 조회

`GET /v2/candles`

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `interval` | string | 필수 | 캔들 주기: `1`, `5`, `15`, `30`, `60`, `240`, `1D`, `1W` |
| `start` | number | 선택 | 조회 시작 시각 (timestamp) |
| `end` | number | 선택 | 조회 종료 시각 (timestamp) |
| `limit` | number | 필수 | 최대 조회 건수 (1~200) |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `timestamp` | number | 캔들 시작 시각 |
| `open` | string | 시가 |
| `high` | string | 고가 |
| `low` | string | 저가 |
| `close` | string | 종가 |
| `volume` | string | 거래량 |

```bash
curl 'https://api.korbit.co.kr/v2/candles?symbol=btc_krw&interval=60&limit=5'
```

---

### 5.5 거래지원 목록 조회

`GET /v2/currencyPairs`

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `symbol` | string | 거래쌍 심볼 |
| `status` | string | `launched` (거래 가능) / `stopped` (거래 중단) |

```bash
curl 'https://api.korbit.co.kr/v2/currencyPairs'
```

---

### 5.6 호가 정책 조회

`GET /v2/tickSizePolicy`

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `symbol` | string | 거래쌍 심볼 |
| `tickSizePolicy` | array | 호가 정책 목록 |
| `tickSizePolicy[].priceGte` | string | 가격 범위 시작값 (이상) |
| `tickSizePolicy[].tickSize` | string | 해당 가격 범위의 호가 단위 |
| `orderbookLevels` | array | 오더북 모아보기 단위 목록 |

```bash
curl 'https://api.korbit.co.kr/v2/tickSizePolicy?symbol=xrp_krw'
```

---

## 6. 주문 API (Private)

### 주문 상태 값

| 상태 | 설명 |
|------|------|
| `pending` | 주문 접수 대기 중 |
| `open` | 전량 미체결 |
| `filled` | 전량 체결 |
| `canceled` | 전량 취소 |
| `partiallyFilled` | 부분 체결 |
| `partiallyFilledCanceled` | 부분 체결 후 잔량 취소 |
| `expired` | 주문 접수 실패 (잔고 부족 또는 timeInForce 조건) |

### timeInForce 값

| 값 | 설명 |
|----|------|
| `gtc` | Good-Till-Canceled: 전량 체결 또는 취소 시까지 유효 (지정가 기본값) |
| `ioc` | Immediate-Or-Cancel: 즉시 체결, 잔량 취소 |
| `fok` | Fill-Or-Kill: 전량 즉시 체결, 불가 시 전량 취소 |
| `po` | Post-Only: 즉시 체결 상황이면 주문 취소 (메이커 주문만 허용) |

---

### 6.1 개별 주문 조회

`GET /v2/orders` — **필요 권한: 주문 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `orderId` | number | 선택 | 주문 ID (orderId 또는 clientOrderId 중 하나 필수) |
| `clientOrderId` | string | 선택 | 사용자 지정 주문 ID |

> expired, canceled 상태의 주문은 종결 후 약 3일이 지나면 조회 불가

```bash
curl -H "X-KAPI-KEY: API키" \
  'https://api.korbit.co.kr/v2/orders?symbol=btc_krw&orderId=1234&timestamp=시각&signature=서명'
```

---

### 6.2 미체결 주문 조회

`GET /v2/openOrders` — **필요 권한: 주문 조회**

`open`, `partiallyFilled` 상태 주문만 조회됩니다.

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `limit` | number | 선택 | 최대 조회 건수 (1~1000, 기본값 500) |

```bash
curl -H "X-KAPI-KEY: API키" \
  'https://api.korbit.co.kr/v2/openOrders?symbol=btc_krw&timestamp=시각&signature=서명'
```

---

### 6.3 최근 주문 내역 조회

`GET /v2/allOrders` — **필요 권한: 주문 조회**

최근 **36시간** 이내 주문 내역만 조회 가능. 데이터에 수 초 지연이 있을 수 있습니다.

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `startTime` | number | 선택 | 조회 시작 시각 (기본값: 36시간 전) |
| `endTime` | number | 선택 | 조회 종료 시각 (기본값: 현재) |
| `limit` | number | 선택 | 최대 조회 건수 (1~1000, 기본값 500) |

---

### 6.4 최근 체결 내역 조회

`GET /v2/myTrades` — **필요 권한: 주문 조회**

최근 **36시간** 이내 체결 내역만 조회 가능.

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `startTime` | number | 선택 | 조회 시작 시각 |
| `endTime` | number | 선택 | 조회 종료 시각 |
| `limit` | number | 선택 | 최대 조회 건수 (1~1000, 기본값 500) |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `tradeId` | number | 거래 체결 ID |
| `orderId` | number | 원주문 ID |
| `side` | string | `buy` / `sell` |
| `price` | string | 체결 단가 |
| `qty` | string | 체결 수량 |
| `amt` | string | 체결 금액 |
| `tradedAt` | number | 체결 시각 |
| `isTaker` | boolean | Taker 체결 여부 |
| `feeCurrency` | string | 수수료 지불 자산 |
| `feeQty` | string | 수수료 수량 |

---

### 6.5 주문하기

`POST /v2/orders` — **필요 권한: 주문 신청**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `side` | string | 필수 | `buy` / `sell` |
| `orderType` | string | 필수 | `limit` / `market` / `best` |
| `price` | string | 조건부 | 지정가 주문의 주문 가격 (시장가/BBO 생략) |
| `qty` | string | 조건부 | 주문 수량 (지정가, 시장가 매도, BBO 매도에 사용) |
| `amt` | string | 조건부 | 주문 대금 KRW (시장가 매수, BBO 매수에 사용) |
| `timeInForce` | string | 선택 | `gtc` / `ioc` / `fok` / `po` |
| `bestNth` | number | 조건부 | BBO 주문 시 N호가 선택 (1~5, BBO 필수) |
| `clientOrderId` | string | 선택 | 사용자 지정 주문 ID (최대 36자, `[0-9a-zA-Z.:_-]`) |
| `pp` | string | 선택 | 가격 보호 사용 여부 (`true`) |
| `ppPercent` | string | 선택 | 가격 보호 범위 (1~100, 기본값 5) |

**응답**

| 필드 | 타입 | 설명 |
|------|------|------|
| `orderId` | number | 생성된 주문 ID |

**주요 에러 코드**

| 코드 | 설명 |
|------|------|
| `DUPLICATE_CLIENT_ORDER_ID` | 중복된 clientOrderId |
| `INVALID_CURRENCY_PAIR` | 잘못된 거래쌍 |
| `NO_BALANCE` | 잔고 부족 |
| `ORDER_VALUE_TOO_LARGE` | 주문 금액 초과 (최대 10억원) |
| `ORDER_VALUE_TOO_SMALL` | 주문 금액 미달 (최소 5,000원) |
| `PRICE_TICK_SIZE_INVALID` | 호가 단위 오류 |
| `TOO_MANY_OPEN_ORDERS` | 미체결 주문 개수 초과 |

```bash
curl -X POST -H "X-KAPI-KEY: API키" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  'https://api.korbit.co.kr/v2/orders' \
  --data-raw "symbol=btc_krw&side=buy&orderType=limit&price=90000000&qty=0.5&timeInForce=gtc&timestamp=시각&signature=서명"
```

```json
{
  "success": true,
  "data": { "orderId": 1234 }
}
```

---

### 6.6 주문 취소하기

`DELETE /v2/orders` — **필요 권한: 주문 신청**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 거래쌍 심볼 |
| `orderId` | number | 선택 | 주문 ID (orderId 또는 clientOrderId 중 하나 필수) |
| `clientOrderId` | string | 선택 | 사용자 지정 주문 ID |

**주요 에러 코드**

| 코드 | 설명 |
|------|------|
| `ORDER_NOT_FOUND` | 주문 ID 없음 |
| `ORDER_ALREADY_CANCELED` | 이미 취소된 주문 |
| `ORDER_ALREADY_FILLED` | 이미 전량 체결된 주문 |
| `ORDER_ALREADY_EXPIRED` | 실패 처리된 주문 |
| `TRY_AGAIN` | 주문 접수 처리 중, 재시도 필요 |

```bash
curl -X DELETE -H "X-KAPI-KEY: API키" \
  'https://api.korbit.co.kr/v2/orders?orderId=1234&symbol=btc_krw&timestamp=시각&signature=서명'
```

---

## 7. 자산 API (Private)

### 7.1 자산 현황

`GET /v2/balance` — **필요 권한: 자산 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currencies` | string | 선택 | 조회할 자산 목록 (콤마 구분). 미입력 시 전체 조회 |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `currency` | string | 자산 이름 |
| `balance` | string | 보유 수량 (사용 가능 + 거래 중 + 출금 중) |
| `available` | string | 사용 가능 수량 |
| `tradeInUse` | string | 거래 중 수량 |
| `withdrawalInUse` | string | 출금 중 수량 |
| `avgPrice` | string | 매수 평균가 |

```bash
curl -H "X-KAPI-KEY: API키" \
  'https://api.korbit.co.kr/v2/balance?currencies=btc,eth&timestamp=시각&signature=서명'
```

---

## 8. 가상자산 입금

### 입금 상태 값

| 상태 | 설명 |
|------|------|
| `pending` | 블록체인에서 트랜잭션 발견 |
| `actionRequired` | 서류 제출 대기 중 |
| `reviewing` | 제출 서류 심사 중 |
| `done` | 입금 완료 |
| `refunded` | 심사 거절 후 반환 |
| `failed` | 입금 실패 |

### 8.1 입금 주소 전체 조회

`GET /v2/coin/depositAddresses` — **필요 권한: 입금 조회**

```bash
curl -H "X-KAPI-KEY: API키" \
  'https://api.korbit.co.kr/v2/coin/depositAddresses?timestamp=시각&signature=서명'
```

---

### 8.2 입금 주소 조회

`GET /v2/coin/depositAddress` — **필요 권한: 입금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 필수 | 가상자산 심볼 |
| `network` | string | 선택 | 블록체인 네트워크 심볼 (미입력 시 기본 네트워크) |

---

### 8.3 입금 주소 생성

`POST /v2/coin/depositAddress` — **필요 권한: 입금 신청**

이미 주소가 존재하면 기존 주소를 반환합니다.

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 필수 | 가상자산 심볼 |
| `network` | string | 선택 | 블록체인 네트워크 심볼 |

---

### 8.4 최근 입금내역 조회

`GET /v2/coin/recentDeposits` — **필요 권한: 입금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 필수 | 가상자산 심볼 |
| `limit` | number | 필수 | 최대 조회 건수 (1~100) |

---

### 8.5 입금 진행상황 조회

`GET /v2/coin/deposit` — **필요 권한: 입금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 필수 | 가상자산 심볼 |
| `coinDepositId` | number | 필수 | 가상자산 입금 ID |

---

## 9. 가상자산 출금

### 출금 상태 값

| 상태 | 설명 |
|------|------|
| `pending` | 출금 요청 접수됨 |
| `actionRequired` | 이메일 확인 대기 (취소 가능) |
| `reviewing` | 출금 심사 중 (취소 가능) |
| `processing` | 출금 처리 중 |
| `done` | 출금 완료 |
| `canceled` | 출금 취소 |
| `failed` | 출금 실패 |

### 9.1 출금 가능 주소 목록 조회

`GET /v2/coin/withdrawableAddresses` — **필요 권한: 출금 조회**

API 출금 허용 주소로 등록된 주소 목록을 반환합니다.

```bash
curl -H "X-KAPI-KEY: API키" \
  'https://api.korbit.co.kr/v2/coin/withdrawableAddresses?timestamp=시각&signature=서명'
```

---

### 9.2 출금 가능 수량 조회

`GET /v2/coin/withdrawableAmount` — **필요 권한: 출금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 선택 | 가상자산 심볼 (미입력 시 전체 조회) |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `currency` | string | 가상자산 심볼 |
| `withdrawableAmount` | string | 출금 가능 수량 |
| `withdrawalInUseAmount` | string | 출금 진행 중 수량 |

---

### 9.3 출금 요청

`POST /v2/coin/withdrawal` — **필요 권한: 출금 신청**

> 출금 API 사용 전 개발자센터에서 **API 출금 허용 주소 등록** 필요

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 필수 | 출금할 가상자산 심볼 |
| `network` | string | 선택 | 블록체인 네트워크 심볼 |
| `amount` | string | 필수 | 출금 수량 (수수료 별도) |
| `address` | string | 필수 | 출금 주소 (허용 주소만 가능) |
| `secondaryAddress` | string | 선택 | 2차 주소 (Destination Tag, Memo 등) |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | 출금 진행 상황 |
| `coinWithdrawalId` | number | 출금 요청 고유 ID |

**주요 에러 코드**

| 코드 | 설명 |
|------|------|
| `UNREGISTERED_WITHDRAWAL_ADDRESS` | 허용 주소 미등록 |
| `FORBIDDEN_WITHDRAWAL_ADDRESS` | 출금 불가 주소 |
| `WITHDRAWAL_ALREADY_IN_PROGRESS` | 다른 출금 진행 중 |
| `NO_BALANCE` | 잔고 부족 |
| `DAILY_LIMIT_EXCEEDED` | 일일 출금 한도 초과 |

---

### 9.4 출금 취소

`DELETE /v2/coin/withdrawal` — **필요 권한: 출금 신청**

`actionRequired`, `reviewing` 상태인 경우에만 취소 가능합니다.

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `coinWithdrawalId` | number | 필수 | 출금 ID |

---

### 9.5 최근 출금내역 조회

`GET /v2/coin/recentWithdrawals` — **필요 권한: 출금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 필수 | 가상자산 심볼 |
| `limit` | number | 필수 | 최대 조회 건수 (1~100) |

---

### 9.6 출금 진행상황 조회

`GET /v2/coin/withdrawal` — **필요 권한: 출금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `currency` | string | 필수 | 가상자산 심볼 |
| `coinWithdrawalId` | number | 필수 | 출금 ID |

---

## 10. 원화 입출금

### 10.1 입금 요청

`POST /v2/krw/sendKrwDepositPush` — **필요 권한: 입금 신청**

코빗 모바일 앱으로 원화 입금 요청 알림을 전송합니다. 앱에서 인증 완료 후 입금이 진행됩니다.

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `amount` | string | 필수 | 입금 요청 금액 |

---

### 10.2 출금 요청

`POST /v2/krw/sendKrwWithdrawalPush` — **필요 권한: 출금 신청**

코빗 모바일 앱으로 원화 출금 요청 알림을 전송합니다.

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `amount` | string | 필수 | 출금 요청 금액 |

---

### 10.3 최근 입금내역 조회

`GET /v2/krw/recentDeposits` — **필요 권한: 입금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `limit` | number | 필수 | 최대 조회 건수 (1~100) |
| `includeAll` | string | 선택 | `true` 시 예치금 이용료, 이벤트 보상 등 포함 |

**입금 구분 (type)**

| 값 | 설명 |
|----|------|
| `general` | 일반 원화 입금 |
| `depositInterest` | 예치금 이용료 |
| `makerIncentive` | 메이커 인센티브 |
| `reward` | 이벤트 보상 |
| `etc` | 기타 |

---

### 10.4 최근 출금내역 조회

`GET /v2/krw/recentWithdrawals` — **필요 권한: 출금 조회**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `limit` | number | 필수 | 최대 조회 건수 (1~100) |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | number | KRW 출금 ID |
| `quantity` | string | 출금된 KRW 수량 (수수료 제외) |
| `fee` | string | 출금 수수료 |
| `status` | string | 출금 상태 |
| `createdAt` | number | 출금 요청 시각 |

---

## 11. 기타 API

### 11.1 가상자산 정보 조회

`GET /v2/currencies`

**응답 필드 (networkList 포함)**

| 필드 | 설명 |
|------|------|
| `name` | 자산 심볼 |
| `fullName` | 자산 이름 |
| `defaultNetwork` | 기본 네트워크 심볼 |
| `withdrawalMaxAmountPerRequest` | 1회 최대 출금 수량 |
| `networkList[].name` | 네트워크 심볼 |
| `networkList[].depositStatus` | 입금 가능 상태 (`launched` / `stopped`) |
| `networkList[].withdrawalStatus` | 출금 가능 상태 (`launched` / `stopped`) |
| `networkList[].confirmationCount` | 입금에 필요한 컨펌 수 |
| `networkList[].withdrawalTxFee` | 출금 수수료 |
| `networkList[].withdrawalMinAmount` | 최소 출금 수량 |
| `networkList[].withdrawalPrecision` | 출금 수량 소수점 자릿수 |
| `networkList[].hasSecondaryAddr` | 2차 주소 존재 여부 |

```bash
curl 'https://api.korbit.co.kr/v2/currencies'
```

---

### 11.2 서버 시각 조회

`GET /v2/time`

```bash
curl 'https://api.korbit.co.kr/v2/time'
```

```json
{
  "success": true,
  "data": { "time": 1700000000000 }
}
```

---

### 11.3 거래수수료율 조회

`GET /v2/tradingFeePolicy` — **필요 권한: 없음 (인증 필요)**

**요청 파라미터**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 선택 | 거래쌍 심볼 (콤마 구분 다중 입력 가능) |

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `symbol` | string | 거래쌍 |
| `buyFeeCurrency` | string | 매수 수수료 수취 자산 |
| `sellFeeCurrency` | string | 매도 수수료 수취 자산 |
| `maxFeeRate` | string | 최대 수취 가능 수수료율 |
| `takerFeeRate` | string | Taker 수수료율 |
| `makerFeeRate` | string | Maker 수수료율 |

---

### 11.4 API 키 정보 조회

`GET /v2/currentKeyInfo` — **필요 권한: 없음**

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `apiKey` | string | API 키 ID |
| `type` | string | `hmac-sha256` / `ed25519` |
| `publicKey` | string | ED25519 공개 키 (ED25519 타입일 때만) |
| `permissions` | array | 권한 목록 |
| `whitelist` | string | 허용 IP 목록 |
| `expiration` | number | 만료 시각 |
| `status` | string | `activated` / `deactivated` |
| `label` | string | API 키 라벨 |
| `createdAt` | number | 생성 시각 |

---

## 12. WebSocket API

### 12.1 연결 및 인증

| 타입 | URL | 인증 필요 |
|------|-----|----------|
| Public | `wss://ws-api.korbit.co.kr/v2/public` | 불필요 |
| Private | `wss://ws-api.korbit.co.kr/v2/private` | 필요 |

**Private 연결 시 인증 방법**: URL 쿼리스트링에 `timestamp`, `signature` 포함, 헤더에 `X-KAPI-KEY` 포함

**구독 요청 형식**
```json
[{"method":"subscribe","type":"ticker","symbols":["btc_krw","eth_krw"]}]
```

**응답 메시지 종류**

| 종류 | 설명 |
|------|------|
| 실시간 데이터 | `status` 필드 없음 |
| 제어 메시지 | `status` 필드 있음 (`success` / `fail` / `error`) |

**requestId 사용 시 응답 예시**
```json
// 요청
[{"requestId": 1, "method": "subscribe", "type": "myOrder", "symbols": ["btc_krw"]}]

// 응답
{"requestId": 1, "status": "success"}
{"requestId": 1, "status": "fail", "code": "INVALID_SYMBOL", "message": "..."}
```

---

### 12.2 현재가 (Ticker)

**구독 요청**
```json
[{"method":"subscribe","type":"ticker","symbols":["btc_krw","eth_krw"]}]
```

**응답 필드**

| 필드 | 설명 |
|------|------|
| `type` | 고정값 `ticker` |
| `timestamp` | 현재 서버 시간 (Unix ms) |
| `symbol` | 거래쌍 |
| `snapshot` | `true` = 구독 직후 스냅샷, `null` = 실시간 |
| `data.open` | 최근 24시간 시가 |
| `data.close` | 최근 24시간 종가 |
| `data.high` | 최근 24시간 고가 |
| `data.low` | 최근 24시간 저가 |
| `data.volume` | 최근 24시간 거래량 |
| `data.bestBidPrice` | 매수 1호가 |
| `data.bestAskPrice` | 매도 1호가 |

---

### 12.3 호가 (Orderbook)

최대 **30호가** 조회 가능합니다.

**구독 요청**
```json
[{"method":"subscribe","type":"orderbook","symbols":["btc_krw"]}]
```

**파라미터**

| 필드 | 설명 |
|------|------|
| `level` | 오더북 모아보기 단위 (선택) |

---

### 12.4 체결 (Trade)

**구독 요청**
```json
[{"method":"subscribe","type":"trade","symbols":["btc_krw"]}]
```

**응답 필드** (`data` 배열)

| 필드 | 설명 |
|------|------|
| `timestamp` | 체결 시각 |
| `price` | 체결 가격 |
| `qty` | 체결량 |
| `isBuyerTaker` | 매수 주문으로 인한 체결 여부 |
| `tradeId` | 거래 체결 ID |

---

### 12.5 내 주문 (MyOrder)

**필요 권한: 주문 조회**

**구독 요청**
```json
[{"method":"subscribe","type":"myOrder","symbols":["btc_krw"]}]
```

**응답 필드** (`order.orders` 배열)

| 필드 | 설명 |
|------|------|
| `orderId` | 주문 ID |
| `status` | 주문 상태 (`unfilled` = REST API의 `open`) |
| `side` | `buy` / `sell` |
| `orderType` | `limit` / `market` / `best` |
| `timeInForce` | 주문 조건 |
| `price` | 주문 가격 |
| `qty` | 주문 수량 |
| `filledQty` | 체결량 |
| `filledAmt` | 체결금액 |
| `avgPrice` | 평균 체결 단가 |
| `createdAt` | 주문 접수 시각 |
| `clientOrderId` | 사용자 지정 주문 ID |

---

### 12.6 내 체결 (MyTrade)

**필요 권한: 주문 조회**

**구독 요청**
```json
[{"method":"subscribe","type":"myTrade","symbols":["btc_krw"]}]
```

**응답 필드** (`trade.trades` 배열)

| 필드 | 설명 |
|------|------|
| `tradeId` | 거래 체결 ID |
| `orderId` | 원주문 ID |
| `side` | `buy` / `sell` |
| `price` | 체결 단가 |
| `qty` | 체결 수량 |
| `fee` | 수수료 |
| `feeCurrency` | 수수료 자산 |
| `filledAt` | 체결 시각 |
| `isTaker` | Taker 체결 여부 |

---

### 12.7 내 자산 (MyAsset)

**필요 권한: 자산 조회**

**구독 요청**
```json
[{"method":"subscribe","type":"myAsset"}]
```

> `symbols` 파라미터 불필요

**응답 필드** (`asset.assets` 배열)

| 필드 | 설명 |
|------|------|
| `currency` | 자산 이름 |
| `balance` | 보유 수량 |
| `available` | 사용 가능 수량 |
| `tradeInUse` | 거래 중 수량 |
| `withdrawalInUse` | 출금 중 수량 |
| `avgPrice` | 매수 평균가 |
| `updatedAt` | 변동 시각 |