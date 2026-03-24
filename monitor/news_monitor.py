# =============================================================================
# monitor/news_monitor.py — 유가·PPI·지정학 뉴스 수집
#
# 데이터 소스:
#   유가 (WTI): yfinance CL=F
#   PPI:        FRED API (https://fred.stlouisfed.org) — PPIACO 시리즈
#   뉴스:       Reuters / CoinDesk RSS 피드 + 키워드 필터
# =============================================================================

import os
import requests
import feedparser
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

_FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# RSS 피드 목록
_NEWS_FEEDS = [
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("CoinDesk",         "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Reuters World",    "https://feeds.reuters.com/Reuters/worldNews"),
]

# 주요 관심 키워드 (대소문자 무관)
_KEYWORDS = [
    "XRP", "ripple", "crypto", "bitcoin", "ethereum",
    "oil", "crude", "OPEC",
    "geopolit", "war", "sanction", "missile", "tension",
    "Fed", "Federal Reserve", "interest rate", "inflation", "PPI", "CPI",
    "SEC", "ETF",
]


# ─────────────────────────────────────────────
# 유가 조회 (yfinance)
# ─────────────────────────────────────────────

def get_oil_price() -> dict:
    """WTI 원유 현재가와 전일 대비 변동률을 반환합니다."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("CL=F")
        hist   = ticker.history(period="5d")
        if len(hist) < 2:
            return {"price": None, "change_pct": None}
        price  = round(float(hist["Close"].iloc[-1]), 2)
        prev   = round(float(hist["Close"].iloc[-2]), 2)
        change = round((price - prev) / prev * 100, 2)
        return {"price": price, "change_pct": change}
    except Exception as e:
        print(f"[news_monitor] 유가 조회 실패: {e}")
        return {"price": None, "change_pct": None}


# ─────────────────────────────────────────────
# PPI 조회 (FRED API)
# ─────────────────────────────────────────────

def get_ppi() -> dict:
    """미국 PPI(생산자물가지수) 최신 수치를 반환합니다."""
    if not _FRED_API_KEY:
        return {"value": None, "date": None, "note": "FRED_API_KEY 미설정"}
    try:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id":  "PPIACO",
                "api_key":    _FRED_API_KEY,
                "file_type":  "json",
                "sort_order": "desc",
                "limit":      1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        obs = resp.json()["observations"]
        return {"value": obs[0]["value"], "date": obs[0]["date"]}
    except Exception as e:
        print(f"[news_monitor] PPI 조회 실패: {e}")
        return {"value": None, "date": None}


# ─────────────────────────────────────────────
# 뉴스 헤드라인 수집 (RSS)
# ─────────────────────────────────────────────

def get_news_headlines(max_items: int = 5) -> list:
    """관심 키워드가 포함된 뉴스 헤드라인을 반환합니다."""
    headlines = []
    seen = set()

    for source_name, feed_url in _NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                if any(kw.lower() in title.lower() for kw in _KEYWORDS):
                    headlines.append(f"• {title}  [{source_name}]")
                    seen.add(title)
                    if len(headlines) >= max_items:
                        return headlines
        except Exception as e:
            print(f"[news_monitor] RSS 파싱 실패 ({source_name}): {e}")
            continue

    return headlines


# ─────────────────────────────────────────────
# 일일 브리핑 생성
# ─────────────────────────────────────────────

def build_daily_briefing(crypto_prices: dict) -> str:
    """
    코인 시황 + 유가 + PPI + 뉴스를 종합한 일일 브리핑 메시지를 반환합니다.

    Parameters
    ----------
    crypto_prices : {"XRPUSDT": float, "BTCUSDT": float, "ETHUSDT": float}
    """
    oil  = get_oil_price()
    ppi  = get_ppi()
    news = get_news_headlines()

    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M") + " KST"
    xrp = crypto_prices.get("XRPUSDT", 0)
    btc = crypto_prices.get("BTCUSDT", 0)
    eth = crypto_prices.get("ETHUSDT", 0)

    lines = [
        f"📅 일일 브리핑 [{date_str}]",
        "─" * 32,
        "💰 코인 현재가",
        f"  XRP : ${xrp:,.4f}",
        f"  BTC : ${btc:>10,.0f}",
        f"  ETH : ${eth:>10,.0f}",
        "",
    ]

    # 유가
    if oil["price"]:
        sign = "+" if (oil["change_pct"] or 0) >= 0 else ""
        lines.append(f"🛢  유가 WTI : ${oil['price']} ({sign}{oil['change_pct']}%)")
    else:
        lines.append("🛢  유가 WTI : 조회 실패")

    # PPI
    if ppi["value"]:
        lines.append(f"📊 PPI (PPIACO) : {ppi['value']}  ({ppi['date']})")
    elif ppi.get("note"):
        lines.append(f"📊 PPI : {ppi['note']}")

    # 뉴스
    if news:
        lines.append("")
        lines.append("📰 주요 뉴스")
        lines.extend(news)

    lines.append("─" * 32)
    return "\n".join(lines)
