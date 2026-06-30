"""
토스증권 Open API 클라이언트  (실제 스펙 기반)
─────────────────────────────────────────────
- OpenAPI 3.1.0 / v1.1.5  (https://developers.tossinvest.com/docs)
- Base URL: https://openapi.tossinvest.com
- 인증: OAuth2 Client Credentials  →  POST /oauth2/token
- 공통 헤더: Authorization: Bearer {token}
            계좌/자산/주문 API 는 X-Tossinvest-Account: {accountSeq} 추가
- 가격/수량은 모두 문자열(decimal) 로 주고받음
- side: BUY / SELL,  orderType: LIMIT / MARKET

보안:
- client_secret 은 절대 코드/파일에 저장하지 않습니다. 실행 시 입력받아 메모리에만 둡니다.
- client_id(API Key) 는 상대적으로 덜 민감하므로 기본값으로 둘 수 있으나 환경변수 우선.

Mock 모드:
- secret 없이 생성하면 Mock 모드로 동작(테스트/오프라인용). 실제 주문은 발생하지 않습니다.
"""

from __future__ import annotations

import os
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Any

import httpx

BASE_URL = "https://openapi.tossinvest.com"

# 사용자가 공유한 API Key (덜 민감). 환경변수 TOSS_CLIENT_ID 가 있으면 그것을 우선 사용.
DEFAULT_CLIENT_ID = "tsck_live_hAVDHLehDKDfeB6EtseqOx"


# ──────────────────────────────────────────────
# 예외
# ──────────────────────────────────────────────
class TossAPIError(Exception):
    """API 가 에러 envelope 또는 OAuth2 에러를 반환했을 때."""

    def __init__(self, status: int, code: str, message: str,
                 request_id: Optional[str] = None, data: Any = None):
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.data = data
        super().__init__(f"[{status} {code}] {message}")


# ──────────────────────────────────────────────
# 유틸 — 문자열 decimal → 숫자
# ──────────────────────────────────────────────
def num(s: Any, default: float = 0) -> float | int:
    if s is None:
        return default
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return default


# ──────────────────────────────────────────────
# Mock 데이터 (secret 없이 테스트 가능)
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

WATCHLIST = list(MOCK_STOCKS.keys())  # 시세 탭 기본 관심종목

# 주문 상태(영문 enum) → 한글
STATUS_KO = {
    "PENDING": "접수", "PENDING_CANCEL": "취소중", "PENDING_REPLACE": "정정중",
    "PARTIAL_FILLED": "부분체결", "FILLED": "체결", "CANCELED": "취소",
    "REJECTED": "거부", "CANCEL_REJECTED": "취소거부", "REPLACE_REJECTED": "정정거부",
    "REPLACED": "정정완료",
}


class TossAPIClient:
    """동기(sync) 클라이언트. CLI 와 TUI(asyncio.to_thread) 양쪽에서 사용."""

    def __init__(self, client_id: Optional[str] = None,
                 client_secret: Optional[str] = None,
                 mock: Optional[bool] = None):
        self.client_id = client_id or os.getenv("TOSS_CLIENT_ID") or DEFAULT_CLIENT_ID
        self.client_secret = client_secret or os.getenv("TOSS_CLIENT_SECRET") or ""
        # mock 미지정 시: secret 없으면 Mock
        self.is_mock = (not self.client_secret) if mock is None else mock

        self.access_token: Optional[str] = None
        self._token_exp: float = 0.0
        self.accounts: list[dict] = []
        self.account_seq: Optional[int] = None

        self._http = httpx.Client(base_url=BASE_URL, timeout=15.0)

    # ─────────────────────────── 인증 ───────────────────────────
    def authorize(self) -> bool:
        """토큰 발급 + 계좌목록 로드. 성공 시 True."""
        if self.is_mock:
            self.accounts = [{"accountNo": "00000000000", "accountSeq": 1,
                              "accountType": "BROKERAGE"}]
            self.account_seq = 1
            return True
        try:
            self._issue_token()
            self.accounts = self.get_accounts()
            if self.accounts and self.account_seq is None:
                self.account_seq = self.accounts[0]["accountSeq"]
            return True
        except Exception:
            raise

    def _issue_token(self) -> None:
        r = self._http.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if r.status_code != 200:
            try:
                e = r.json()
            except Exception:
                e = {}
            raise TossAPIError(r.status_code,
                               e.get("error", "token_error"),
                               e.get("error_description") or "토큰 발급 실패")
        body = r.json()
        self.access_token = body["access_token"]
        self._token_exp = time.time() + int(body.get("expires_in", 86400)) - 60

    def _ensure_token(self) -> None:
        if self.is_mock:
            return
        if not self.access_token or time.time() >= self._token_exp:
            self._issue_token()

    def _headers(self, account: bool = False) -> dict:
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.access_token}"}
        if account:
            if self.account_seq is None:
                raise TossAPIError(0, "no-account", "선택된 계좌(accountSeq)가 없습니다.")
            h["X-Tossinvest-Account"] = str(self.account_seq)
        return h

    # ─────────────────────── 공통 요청 헬퍼 ───────────────────────
    def _request(self, method: str, path: str, *, account: bool = False,
                 params: Optional[dict] = None, json: Optional[dict] = None,
                 _retry: bool = True) -> Any:
        """성공 시 envelope 의 result 를 반환. 에러 시 TossAPIError."""
        headers = self._headers(account=account)
        if json is not None:
            headers["Content-Type"] = "application/json"
        r = self._http.request(method, path, headers=headers,
                               params=params, json=json)

        # Rate limit → 한 번 재시도
        if r.status_code == 429 and _retry:
            wait = float(r.headers.get("Retry-After", "1") or 1)
            time.sleep(min(wait, 5))
            return self._request(method, path, account=account, params=params,
                                 json=json, _retry=False)

        if r.status_code // 100 != 2:
            self._raise_error(r)

        if not r.content:
            return None
        body = r.json()
        # 성공 envelope: {"result": ...}
        if isinstance(body, dict) and "result" in body:
            return body["result"]
        return body

    @staticmethod
    def _raise_error(r: httpx.Response) -> None:
        try:
            body = r.json()
        except Exception:
            raise TossAPIError(r.status_code, "http-error", r.text[:200] or "요청 실패")
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            raise TossAPIError(r.status_code, err.get("code", "error"),
                               err.get("message", ""), err.get("requestId"),
                               err.get("data"))
        raise TossAPIError(r.status_code, "error", str(body)[:200])

    # ════════════════════════════════════════════════════════════
    #  실제 엔드포인트 (저수준)  — CLI 에서 사용
    # ════════════════════════════════════════════════════════════

    # ── 계좌 / 자산 ──
    def get_accounts(self) -> list[dict]:
        if self.is_mock:
            return [{"accountNo": "00000000000", "accountSeq": 1, "accountType": "BROKERAGE"}]
        res = self._request("GET", "/api/v1/accounts")
        return res if isinstance(res, list) else res.get("accounts", res)

    def get_holdings(self, symbol: Optional[str] = None) -> dict:
        if self.is_mock:
            return self._mock_holdings_overview()
        params = {"symbol": symbol} if symbol else None
        return self._request("GET", "/api/v1/holdings", account=True, params=params)

    def get_buying_power(self, currency: str = "KRW") -> dict:
        if self.is_mock:
            return {"currency": currency, "cashBuyingPower": "3850000"}
        return self._request("GET", "/api/v1/buying-power", account=True,
                             params={"currency": currency})

    def get_sellable_quantity(self, symbol: str) -> dict:
        if self.is_mock:
            held = next((h for h in MOCK_PORTFOLIO if h["ticker"] == symbol), None)
            return {"sellableQuantity": str(held["qty"]) if held else "0"}
        return self._request("GET", "/api/v1/sellable-quantity", account=True,
                             params={"symbol": symbol})

    def get_commissions(self) -> list[dict]:
        if self.is_mock:
            return [{"marketCountry": "KR", "commissionRate": "0.0",
                     "startDate": "2026-01-01", "endDate": "2026-06-30"},
                    {"marketCountry": "KR", "commissionRate": "0.00015",
                     "startDate": "2026-07-01", "endDate": None}]
        res = self._request("GET", "/api/v1/commissions", account=True)
        return res if isinstance(res, list) else res.get("commissions", res)

    # ── 시세 (MARKET_DATA) ──
    def get_prices(self, symbols: list[str] | str) -> list[dict]:
        if isinstance(symbols, list):
            symbols = ",".join(symbols)
        if self.is_mock:
            out = []
            for s in symbols.split(","):
                b = MOCK_STOCKS.get(s, {"price": 50000})
                out.append({"symbol": s, "lastPrice": str(b["price"]),
                            "currency": "KRW",
                            "timestamp": datetime.now().isoformat()})
            return out
        res = self._request("GET", "/api/v1/prices", params={"symbols": symbols})
        return res if isinstance(res, list) else res.get("prices", [res])

    def get_orderbook(self, symbol: str) -> dict:
        if self.is_mock:
            p = MOCK_STOCKS.get(symbol, {"price": 50000})["price"]
            asks = [{"price": str(p + i * 100), "volume": str(random.randint(100, 9000))} for i in range(1, 6)]
            bids = [{"price": str(p - i * 100), "volume": str(random.randint(100, 9000))} for i in range(1, 6)]
            return {"timestamp": datetime.now().isoformat(), "currency": "KRW",
                    "asks": asks, "bids": bids}
        return self._request("GET", "/api/v1/orderbook", params={"symbol": symbol})

    def get_trades(self, symbol: str, count: int = 50) -> list[dict]:
        if self.is_mock:
            p = MOCK_STOCKS.get(symbol, {"price": 50000})["price"]
            return [{"price": str(p + random.randint(-200, 200)),
                     "volume": str(random.randint(1, 500)),
                     "timestamp": datetime.now().isoformat(), "currency": "KRW"}
                    for _ in range(min(count, 50))]
        res = self._request("GET", "/api/v1/trades",
                            params={"symbol": symbol, "count": count})
        return res if isinstance(res, list) else res.get("trades", [])

    def get_price_limits(self, symbol: str) -> dict:
        if self.is_mock:
            p = MOCK_STOCKS.get(symbol, {"price": 50000})["price"]
            return {"timestamp": datetime.now().isoformat(),
                    "upperLimitPrice": str(int(p * 1.3)),
                    "lowerLimitPrice": str(int(p * 0.7)), "currency": "KRW"}
        return self._request("GET", "/api/v1/price-limits", params={"symbol": symbol})

    def get_candles_raw(self, symbol: str, interval: str = "1d", count: int = 100,
                        before: Optional[str] = None, adjusted: bool = True) -> dict:
        if self.is_mock:
            return {"candles": self._mock_candles(symbol, count), "nextBefore": None}
        params = {"symbol": symbol, "interval": interval, "count": count,
                  "adjusted": str(adjusted).lower()}
        if before:
            params["before"] = before
        return self._request("GET", "/api/v1/candles", params=params)

    # ── 종목 정보 ──
    def get_stocks(self, symbols: list[str] | str) -> list[dict]:
        if isinstance(symbols, list):
            symbols = ",".join(symbols)
        if self.is_mock:
            return [{"symbol": s, "name": MOCK_STOCKS.get(s, {}).get("name", s),
                     "market": "KOSPI", "securityType": "STOCK",
                     "status": "ACTIVE", "currency": "KRW"}
                    for s in symbols.split(",")]
        res = self._request("GET", "/api/v1/stocks", params={"symbols": symbols})
        return res if isinstance(res, list) else res.get("stocks", [res])

    def get_stock_warnings(self, symbol: str) -> list[dict]:
        if self.is_mock:
            return []
        res = self._request("GET", f"/api/v1/stocks/{symbol}/warnings")
        return res if isinstance(res, list) else res.get("warnings", [])

    # ── 시장 정보 ──
    def get_exchange_rate(self, base: str = "USD", quote: str = "KRW",
                          date_time: Optional[str] = None) -> dict:
        if self.is_mock:
            return {"baseCurrency": base, "quoteCurrency": quote, "rate": "1380.5",
                    "midRate": "1375", "basisPoint": "40", "rateChangeType": "UP",
                    "validFrom": datetime.now().isoformat(), "validUntil": ""}
        params = {"baseCurrency": base, "quoteCurrency": quote}
        if date_time:
            params["dateTime"] = date_time
        return self._request("GET", "/api/v1/exchange-rate", params=params)

    def get_market_calendar(self, country: str = "KR",
                            date: Optional[str] = None) -> dict:
        if self.is_mock:
            d = date or datetime.now().strftime("%Y-%m-%d")
            def day(dd):
                return {"date": dd, "integrated": {
                    "preMarket": {"startTime": f"{dd}T08:00:00+09:00", "endTime": f"{dd}T09:00:00+09:00"},
                    "regularMarket": {"startTime": f"{dd}T09:00:00+09:00", "endTime": f"{dd}T15:30:00+09:00"},
                    "afterMarket": {"startTime": f"{dd}T15:30:00+09:00", "endTime": f"{dd}T20:00:00+09:00"}}}
            return {"today": day(d), "previousBusinessDay": day(d), "nextBusinessDay": day(d)}
        params = {"date": date} if date else None
        return self._request("GET", f"/api/v1/market-calendar/{country}", params=params)

    # ── 주문 (ORDER) ──
    def create_order(self, *, symbol: str, side: str, order_type: str,
                     quantity: Optional[str] = None, price: Optional[str] = None,
                     order_amount: Optional[str] = None,
                     time_in_force: Optional[str] = None,
                     client_order_id: Optional[str] = None,
                     confirm_high_value: bool = False) -> dict:
        """주문 생성. side: BUY/SELL, order_type: LIMIT/MARKET."""
        body: dict = {"symbol": symbol, "side": side, "orderType": order_type}
        if quantity is not None:
            body["quantity"] = str(quantity)
        if order_amount is not None:
            body["orderAmount"] = str(order_amount)
        if price is not None:
            body["price"] = str(price)
        if time_in_force:
            body["timeInForce"] = time_in_force
        if client_order_id:
            body["clientOrderId"] = client_order_id
        if confirm_high_value:
            body["confirmHighValueOrder"] = True

        if self.is_mock:
            return {"orderId": f"MOCK-{datetime.now().strftime('%H%M%S')}",
                    "clientOrderId": client_order_id}
        return self._request("POST", "/api/v1/orders", account=True, json=body)

    def modify_order(self, order_id: str, *, order_type: str,
                     quantity: Optional[str] = None, price: Optional[str] = None,
                     confirm_high_value: bool = False) -> dict:
        body: dict = {"orderType": order_type}
        if quantity is not None:
            body["quantity"] = str(quantity)
        if price is not None:
            body["price"] = str(price)
        if confirm_high_value:
            body["confirmHighValueOrder"] = True
        if self.is_mock:
            return {"orderId": f"MOCK-MOD-{datetime.now().strftime('%H%M%S')}"}
        return self._request("POST", f"/api/v1/orders/{order_id}/modify",
                             account=True, json=body)

    def cancel_order(self, order_id: str) -> dict:
        if self.is_mock:
            return {"orderId": f"MOCK-CXL-{datetime.now().strftime('%H%M%S')}"}
        return self._request("POST", f"/api/v1/orders/{order_id}/cancel",
                             account=True, json={})

    def list_orders(self, status: str = "OPEN", symbol: Optional[str] = None,
                    date_from: Optional[str] = None, date_to: Optional[str] = None,
                    cursor: Optional[str] = None, limit: int = 20) -> dict:
        """status: OPEN(미체결) / CLOSED(종료)."""
        if self.is_mock:
            return {"orders": self._mock_order_objs(status), "nextCursor": None,
                    "hasNext": False}
        params: dict = {"status": status, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/api/v1/orders", account=True, params=params)

    def get_order(self, order_id: str) -> dict:
        if self.is_mock:
            return self._mock_order_objs("OPEN")[0]
        return self._request("GET", f"/api/v1/orders/{order_id}", account=True)

    # ════════════════════════════════════════════════════════════
    #  고수준 어댑터  — TUI(app.py) 호환용 (기존 dict 형태 유지)
    # ════════════════════════════════════════════════════════════
    def get_quote(self, ticker: str) -> dict:
        if self.is_mock:
            base = MOCK_STOCKS.get(ticker, {"name": ticker, "price": 50000,
                                            "change": 0, "change_pct": 0.0, "volume": 0})
            noise = random.randint(-100, 100)
            return {**base, "price": base["price"] + noise,
                    "timestamp": datetime.now().strftime("%H:%M:%S")}
        return self.get_all_quotes([ticker]).get(ticker, {})

    def get_all_quotes(self, symbols: Optional[list[str]] = None) -> dict:
        """{ticker: {name, price, change, change_pct, volume}} — 시세 탭용."""
        symbols = symbols or WATCHLIST
        if self.is_mock:
            return {t: self.get_quote(t) for t in symbols}

        prices = {p["symbol"]: p for p in self.get_prices(symbols)}
        names = {s["symbol"]: s.get("name", s["symbol"]) for s in self.get_stocks(symbols)}
        out = {}
        for t in symbols:
            cur = num(prices.get(t, {}).get("lastPrice"))
            change = change_pct = vol = 0
            try:  # 전일 종가 대비 등락 + 당일 거래량 (일봉 2개)
                cd = self.get_candles_raw(t, "1d", 2).get("candles", [])
                if cd:
                    today = cd[-1]
                    prev_close = num(cd[-2]["closePrice"]) if len(cd) > 1 else num(today["openPrice"])
                    vol = num(today.get("volume"))
                    if prev_close:
                        change = cur - prev_close
                        change_pct = round(change / prev_close * 100, 2)
            except Exception:
                pass
            out[t] = {"name": names.get(t, t), "price": cur, "change": change,
                      "change_pct": change_pct, "volume": vol,
                      "timestamp": datetime.now().strftime("%H:%M:%S")}
        return out

    def get_portfolio(self) -> list:
        """보유주식 → [{ticker,name,qty,avg_price,cur_price,value,profit,profit_pct}]"""
        if self.is_mock:
            out = []
            for item in MOCK_PORTFOLIO:
                cur = self.get_quote(item["ticker"])["price"]
                cost = item["avg_price"] * item["qty"]
                value = cur * item["qty"]
                profit = value - cost
                out.append({**item, "cur_price": cur, "value": value,
                            "profit": profit,
                            "profit_pct": (profit / cost * 100) if cost else 0})
            return out
        ov = self.get_holdings()
        out = []
        for it in ov.get("items", []):
            out.append({
                "ticker": it["symbol"], "name": it.get("name", it["symbol"]),
                "qty": num(it.get("quantity")),
                "avg_price": num(it.get("averagePurchasePrice")),
                "cur_price": num(it.get("lastPrice")),
                "value": num(it.get("marketValue", {}).get("amount")),
                "profit": num(it.get("profitLoss", {}).get("amount")),
                "profit_pct": round(num(it.get("profitLoss", {}).get("rate")) * 100, 2),
            })
        return out

    def get_orders(self) -> list:
        """주문내역 → [{time,name,side(매수/매도),qty,price,status}]  (TUI 호환)"""
        if self.is_mock:
            return MOCK_ORDERS
        objs = []
        for st in ("OPEN", "CLOSED"):
            try:
                objs += self.list_orders(st, limit=50).get("orders", [])
            except Exception:
                pass
        out = []
        for o in objs:
            out.append({
                "time": (o.get("orderedAt", "") or "")[11:19],
                "ticker": o.get("symbol", ""), "name": o.get("symbol", ""),
                "side": "매수" if o.get("side") == "BUY" else "매도",
                "qty": num(o.get("quantity")), "price": num(o.get("price")),
                "status": STATUS_KO.get(o.get("status", ""), o.get("status", "")),
            })
        return out

    def place_order(self, ticker: str, side: str, qty: int, price: int) -> dict:
        """TUI 호환 지정가 주문. side: '매수'/'매도' 또는 BUY/SELL."""
        side_en = "BUY" if side in ("매수", "BUY", "buy") else "SELL"
        res = self.create_order(symbol=ticker, side=side_en, order_type="LIMIT",
                                quantity=str(qty), price=str(price))
        return {"orderId": res.get("orderId", "-"), "status": "accepted",
                "ticker": ticker, "side": side, "qty": qty, "price": price}

    def get_candles(self, ticker: str, count: int = 30) -> list:
        """차트용 → [{date,open,high,low,close,volume}]  (TUI 호환)"""
        if self.is_mock:
            return self._mock_candles(ticker, count)
        cs = self.get_candles_raw(ticker, "1d", count).get("candles", [])
        return [{"date": (c.get("timestamp", "") or "")[:10],
                 "open": num(c.get("openPrice")), "high": num(c.get("highPrice")),
                 "low": num(c.get("lowPrice")), "close": num(c.get("closePrice")),
                 "volume": num(c.get("volume"))} for c in cs]

    # ─────────────────────── Mock 헬퍼 ───────────────────────
    def _mock_candles(self, ticker: str, count: int) -> list:
        base = MOCK_STOCKS.get(ticker, {}).get("price", 50000)
        candles, price = [], base * 0.95
        for i in range(count):
            high = price * (1 + random.uniform(0, 0.02))
            low = price * (1 - random.uniform(0, 0.02))
            close = random.uniform(low, high)
            candles.append({
                "timestamp": (datetime.now() - timedelta(days=count - i)).strftime("%Y-%m-%dT00:00:00+09:00"),
                "date": (datetime.now() - timedelta(days=count - i)).strftime("%m/%d"),
                "open": int(price), "high": int(high), "low": int(low),
                "close": int(close), "openPrice": str(int(price)),
                "highPrice": str(int(high)), "lowPrice": str(int(low)),
                "closePrice": str(int(close)), "volume": str(random.randint(500_000, 15_000_000)),
            })
            price = close
        return candles

    def _mock_holdings_overview(self) -> dict:
        items = []
        for it in MOCK_PORTFOLIO:
            cur = self.get_quote(it["ticker"])["price"]
            value = cur * it["qty"]
            cost = it["avg_price"] * it["qty"]
            items.append({
                "symbol": it["ticker"], "name": it["name"], "marketCountry": "KR",
                "currency": "KRW", "quantity": str(it["qty"]),
                "lastPrice": str(cur), "averagePurchasePrice": str(it["avg_price"]),
                "marketValue": {"amount": str(value), "purchaseAmount": str(cost),
                                "amountAfterCost": str(value)},
                "profitLoss": {"amount": str(value - cost),
                               "rate": str(round((value - cost) / cost, 4) if cost else 0)},
            })
        return {"items": items}

    def _mock_order_objs(self, status: str) -> list:
        wanted = {"OPEN": {"대기"}, "CLOSED": {"체결"}}.get(status, {"대기", "체결"})
        out = []
        for o in MOCK_ORDERS:
            if o["status"] not in wanted:
                continue
            out.append({
                "orderId": f"MOCK-{o['ticker']}-{o['time'].replace(':','')}",
                "symbol": o["ticker"],
                "side": "BUY" if o["side"] == "매수" else "SELL",
                "orderType": "LIMIT", "timeInForce": "DAY",
                "status": "FILLED" if o["status"] == "체결" else "PENDING",
                "price": str(o["price"]), "quantity": str(o["qty"]),
                "currency": "KRW",
                "orderedAt": f"2026-06-30T{o['time']}+09:00",
                "execution": {"filledQuantity": str(o["qty"] if o["status"] == "체결" else 0)},
            })
        return out

    def close(self):
        try:
            self._http.close()
        except Exception:
            pass
