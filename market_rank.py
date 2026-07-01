"""
주식 순위 (거래대금/거래량/시가총액/상승률/하락률/인기).

토스증권 Open API 에는 순위 엔드포인트가 없어, 네이버 금융 모바일 API 를 사용합니다.
(공개 JSON, 추가 라이브러리 불필요. 조회 전용 — 주문과 무관)
"""

import json
import urllib.request

BASE = "https://m.stock.naver.com/api/stocks"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")


def _fetch(seg: str, market: str, pages: int = 1, size: int = 100) -> list:
    out = []
    for p in range(1, pages + 1):
        d = json.loads(_get(f"{BASE}/{seg}/{market}?page={p}&pageSize={size}"))
        s = d.get("stocks", [])
        out += s
        if len(s) < size:
            break
    return out


def _num(v) -> int:
    try:
        return int(str(v).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0


def _row(rank: int, s: dict) -> dict:
    return {
        "rank": rank,
        "code": s.get("itemCode", ""),
        "name": s.get("stockName", ""),
        "price": s.get("closePrice", ""),
        "changePct": s.get("fluctuationsRatio", "0"),
        "change": s.get("compareToPreviousClosePrice", ""),
        "value": s.get("accumulatedTradingValueKrwHangeul", ""),
        "volume": s.get("accumulatedTradingVolume", ""),
        "cap": s.get("marketValueHangeul", ""),
        "at": s.get("localTradedAt", ""),      # 기준 시각(당일)
        "status": s.get("marketStatus", ""),   # OPEN / CLOSE
    }


# 표시명 → (kind, 설명)
KINDS = {
    "1": ("value", "거래대금"),
    "2": ("volume", "거래량"),
    "3": ("cap", "시가총액"),
    "4": ("up", "상승률"),
    "5": ("down", "하락률"),
    "6": ("search", "인기검색"),
}
MARKETS = {"1": ("KOSPI", "코스피"), "2": ("KOSDAQ", "코스닥"), "3": ("ALL", "통합")}


def ranking(kind: str, market: str = "KOSPI", count: int = 20) -> list:
    markets = ["KOSPI", "KOSDAQ"] if market == "ALL" else [market]

    if kind in ("up", "down", "cap", "search"):
        seg = {"up": "up", "down": "down", "cap": "marketValue", "search": "searchTop"}[kind]
        stocks = []
        for m in markets:
            stocks += _fetch(seg, m, pages=1, size=min(count, 100))
        if kind == "cap":
            stocks.sort(key=lambda s: _num(s.get("marketValueRaw")), reverse=True)
        elif kind == "up":
            stocks.sort(key=lambda s: float(s.get("fluctuationsRatio") or 0), reverse=True)
        elif kind == "down":
            stocks.sort(key=lambda s: float(s.get("fluctuationsRatio") or 0))
    else:  # value / volume — 시총 상위 300 를 받아 해당 지표로 재정렬
        key = {"value": "accumulatedTradingValueRaw",
               "volume": "accumulatedTradingVolumeRaw"}[kind]
        stocks = []
        for m in markets:
            stocks += _fetch("marketValue", m, pages=3, size=100)
        stocks.sort(key=lambda s: _num(s.get(key)), reverse=True)

    return [_row(i + 1, s) for i, s in enumerate(stocks[:count])]
