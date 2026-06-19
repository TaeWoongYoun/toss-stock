"""
토스증권 Open API 클라이언트
- 실제 API 키가 있으면 Real 모드
- 없으면 Mock 모드로 자동 전환
공식 문서: https://developers.tossinvest.com/docs
"""

import os
import httpx
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional

TOSS_BASE_URL = "https://openapi.tossinvest.com"

# ──────────────────────────────────────────────
# Mock 데이터 (API 키 없이도 바로 실행 가능)
# ──────────────────────────────────────────────
MOCK_STOCKS = {
    "005930": {"name": "삼성전자",    "price": 74200,  "change": 800,   "change_pct": 1.09,  "volume": 12_345_678},
    "000660": {"name": "SK하이닉스",  "price": 192500, "change": -1500, "change_pct": -0.77, "volume": 3_210_000},
    "035420": {"name": "NAVER",       "price": 215000, "change": 3000,  "change_pct": 1.41,  "volume": 892_000},
    "035720": {"name": "카카오",      "price": 42150,  "change": -350,  "change_pct": -0.82, "volume": 5_120_000},
    "051910": {"name": "LG화학",      "price": 312000, "change": 2500,  "change_pct": 0.81,  "volume": 430_000},
    "006400": {"name": "삼성SDI",     "price": 265000, "change": -2000, "change_pct": -0.75, "volume": 320_000},
    "068270": {"name": "셀트리온",    "price": 178500, "change": 1200,  "change_pct": 0.68,  "volume": 756_000},
    "207940": {"name": "삼성바이오로직스", "price": 892000, "change": 5000, "change_pct": 0.56, "volume": 120_000},
}

MOCK_PORTFOLIO = [
    {"ticker": "005930", "name": "삼성전자",    "qty": 10,  "avg_price": 69500,  "cur_price": 74200},
    {"ticker": "000660", "name": "SK하이닉스",  "qty": 5,   "avg_price": 180000, "cur_price": 192500},
    {"ticker": "035420", "name": "NAVER",       "qty": 3,   "avg_price": 198000, "cur_price": 215000},
    {"ticker": "035720", "name": "카카오",      "qty": 20,  "avg_price": 47000,  "cur_price": 42150},
]

MOCK_ORDERS = [
    {"time": "09:32:11", "ticker": "005930", "name": "삼성전자",  "side": "매수", "qty": 5,  "price": 73800, "status": "체결"},
    {"time": "10:15:44", "ticker": "000660", "name": "SK하이닉스","side": "매도", "qty": 2,  "price": 194000,"status": "체결"},
    {"time": "13:02:30", "ticker": "035720", "name": "카카오",    "side": "매수", "qty": 10, "price": 42200, "status": "대기"},
]


class TossAPIClient:
    def __init__(self):
        self.client_id     = os.getenv("TOSS_CLIENT_ID", "")
        self.client_secret = os.getenv("TOSS_CLIENT_SECRET", "")
        self.access_token: Optional[str] = None
        self.is_mock = not (self.client_id and self.client_secret)

    # ── 인증 ──────────────────────────────────
    async def authorize(self) -> bool:
        if self.is_mock:
            return True
        try:
            async with httpx.AsyncClient() as c:
                r = await c.post(
                    f"{TOSS_BASE_URL}/oauth2/token",
                    data={
                        "grant_type":    "client_credentials",
                        "client_id":     self.client_id,
                        "client_secret": self.client_secret,
                    },
                    timeout=10,
                )
                r.raise_for_status()
                self.access_token = r.json()["access_token"]
                return True
        except Exception:
            self.is_mock = True
            return False

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"}

    # ── 시세 조회 ──────────────────────────────
    async def get_quote(self, ticker: str) -> dict:
        if self.is_mock:
            await asyncio.sleep(0.05)
            base = MOCK_STOCKS.get(ticker, {
                "name": ticker, "price": 50000, "change": 0,
                "change_pct": 0.0, "volume": 0
            })
            # 소폭 랜덤 변동 (리얼타임 느낌)
            noise = random.randint(-100, 100)
            return {**base, "price": base["price"] + noise,
                    "timestamp": datetime.now().strftime("%H:%M:%S")}
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{TOSS_BASE_URL}/v1/stock/{ticker}/price",
                headers=self._headers(), timeout=10
            )
            r.raise_for_status()
            d = r.json()
            return {
                "name":       d.get("stockName", ticker),
                "price":      int(d.get("currentPrice", 0)),
                "change":     int(d.get("priceChange", 0)),
                "change_pct": float(d.get("priceChangeRate", 0)),
                "volume":     int(d.get("accumulatedVolume", 0)),
                "timestamp":  datetime.now().strftime("%H:%M:%S"),
            }

    async def get_all_quotes(self) -> dict:
        results = {}
        for ticker in MOCK_STOCKS:
            results[ticker] = await self.get_quote(ticker)
        return results

    # ── 포트폴리오 ─────────────────────────────
    async def get_portfolio(self) -> list:
        if self.is_mock:
            await asyncio.sleep(0.1)
            portfolio = []
            for item in MOCK_PORTFOLIO:
                q = await self.get_quote(item["ticker"])
                cur = q["price"]
                cost   = item["avg_price"] * item["qty"]
                value  = cur * item["qty"]
                profit = value - cost
                pct    = (profit / cost) * 100 if cost else 0
                portfolio.append({**item, "cur_price": cur,
                                  "value": value, "profit": profit,
                                  "profit_pct": pct})
            return portfolio
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{TOSS_BASE_URL}/v1/account/balance",
                            headers=self._headers(), timeout=10)
            r.raise_for_status()
            return r.json().get("holdings", [])

    # ── 주문 내역 ──────────────────────────────
    async def get_orders(self) -> list:
        if self.is_mock:
            await asyncio.sleep(0.05)
            return MOCK_ORDERS
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{TOSS_BASE_URL}/v1/orders",
                            headers=self._headers(), timeout=10)
            r.raise_for_status()
            return r.json().get("orders", [])

    # ── 주문 실행 ──────────────────────────────
    async def place_order(self, ticker: str, side: str,
                          qty: int, price: int) -> dict:
        if self.is_mock:
            await asyncio.sleep(0.2)
            return {
                "orderId":  f"MOCK-{datetime.now().strftime('%H%M%S')}",
                "status":   "accepted",
                "ticker":   ticker,
                "side":     side,
                "qty":      qty,
                "price":    price,
            }
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{TOSS_BASE_URL}/v1/orders",
                headers=self._headers(),
                json={"ticker": ticker, "side": side,
                      "quantity": qty, "price": price,
                      "orderType": "LIMIT"},
                timeout=10
            )
            r.raise_for_status()
            return r.json()

    # ── 캔들 데이터 (차트용) ───────────────────
    async def get_candles(self, ticker: str, count: int = 30) -> list:
        if self.is_mock:
            base_price = MOCK_STOCKS.get(ticker, {}).get("price", 50000)
            candles = []
            price = base_price * 0.95
            for i in range(count):
                open_  = price
                high   = price * (1 + random.uniform(0, 0.02))
                low    = price * (1 - random.uniform(0, 0.02))
                close  = random.uniform(low, high)
                candles.append({
                    "date":  (datetime.now() - timedelta(days=count - i)).strftime("%m/%d"),
                    "open":  int(open_),
                    "high":  int(high),
                    "low":   int(low),
                    "close": int(close),
                    "volume": random.randint(500_000, 15_000_000),
                })
                price = close
            return candles
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{TOSS_BASE_URL}/v1/stock/{ticker}/candles",
                headers=self._headers(),
                params={"period": "1D", "count": count},
                timeout=10
            )
            r.raise_for_status()
            return r.json().get("candles", [])
