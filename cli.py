"""
토스증권 Open API  —  cmd 인터랙티브 CLI
실행:  python cli.py            (실행 시 Secret Key 를 안전하게 입력받음)
       python cli.py --mock     (API 키 없이 테스트)

보안:
- Secret Key 는 getpass 로 입력받아 메모리에만 보관합니다.
  화면에 표시되지 않고, 명령 히스토리/파일/환경변수에도 남지 않습니다.
- 모든 매수/매도/정정/취소는 실행 전 내용을 보여주고 확인을 받습니다. (실제 돈)
"""

import os
import re
import sys
import getpass
import unicodedata
from datetime import datetime

# 입출력 인코딩을 UTF-8 로 고정 — 한글 Windows(cp949)나 파이프/리다이렉트 환경에서
# 한글 입력이 깨지거나, em-dash(—)·박스문자·이모지 출력 시 UnicodeEncodeError 로
# 죽는 것을 방지. (실제 콘솔에서는 무해한 no-op)
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from toss_api import TossAPIClient, TossAPIError, num, STATUS_KO
from stocks import find_stocks, US_TICKERS
import market_rank

# ──────────────────────────────────────────────
#  테마 / 모드
# ──────────────────────────────────────────────
RST = "\033[0m"

# 각 테마: 일반 색 8종 + 차트 색/글자(up/down/body/wick)
THEMES = {
    "1": {  # 컬러 (기본) — 잘 보임
        "label": "컬러(기본)",
        "R": "\033[91m", "G": "\033[92m", "B": "\033[94m", "Y": "\033[93m",
        "C": "\033[96m", "GRY": "\033[90m", "BLD": "\033[1m",
        "up": "\033[91m", "down": "\033[94m", "body": "█", "wick": "│",
    },
    "2": {  # 연한색 — 파스텔, 덜 자극적
        "label": "연한색",
        "R": "\033[38;5;174m", "G": "\033[38;5;108m", "B": "\033[38;5;110m",
        "Y": "\033[38;5;180m", "C": "\033[38;5;109m", "GRY": "\033[38;5;245m",
        "BLD": "", "up": "\033[38;5;174m", "down": "\033[38;5;110m",
        "body": "▓", "wick": "│",
    },
    "3": {  # 흑백 (스텔스) — 회사용, 평범한 로그처럼
        "label": "흑백(스텔스)",
        "R": "\033[37m", "G": "\033[37m", "B": "\033[90m", "Y": "\033[37m",
        "C": "\033[37m", "GRY": "\033[90m", "BLD": "",
        "up": "\033[37m", "down": "\033[90m", "body": "▒", "wick": "┆",
    },
}

# 동적으로 바뀌는 전역 (apply_theme 가 설정)
R = G = B = Y = C = GRY = BLD = ""
UP = DOWN = BODY = WICK = ""
CUR_THEME = "1"
MODE = "hard"  # 'easy' | 'hard'


def apply_theme(key: str):
    global R, G, B, Y, C, GRY, BLD, UP, DOWN, BODY, WICK, CUR_THEME
    t = THEMES.get(key)
    if not t:
        return
    CUR_THEME = key
    R, G, B, Y = t["R"], t["G"], t["B"], t["Y"]
    C, GRY, BLD = t["C"], t["GRY"], t["BLD"]
    UP, DOWN, BODY, WICK = t["up"], t["down"], t["body"], t["wick"]


apply_theme("1")  # 초기값


# ── 한글(전각) 폭을 고려한 정렬 헬퍼 ──
def dwidth(s) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def dtrunc(s, w: int) -> str:
    out, cur = "", 0
    for ch in str(s):
        cw = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if cur + cw > w:
            break
        out, cur = out + ch, cur + cw
    return out


def dcell(s, w: int, right: bool = False) -> str:
    """표시폭 w 에 맞춰 자르고 정렬 (전각=2칸)."""
    s = dtrunc(s, w)
    pad = " " * max(0, w - dwidth(s))
    return (pad + s) if right else (s + pad)


def won(v) -> str:
    n = num(v)
    return f"{n:,.0f}" if isinstance(n, float) and not float(n).is_integer() else f"{int(n):,}"


def sign_color(v) -> str:
    n = num(v)
    return R if n > 0 else (B if n < 0 else GRY)


def hr(ch="─", n=60):
    print(GRY + ch * n + RST)


def title(t):
    print(f"\n{BLD}{C}━━ {t} ━━{RST}")


def ask(prompt, default=None):
    s = input(f"{Y}{prompt}{RST}" + (f" [{default}]" if default is not None else "") + ": ").strip()
    return s or (default if default is not None else "")


def confirm(prompt) -> bool:
    return input(f"{R}{BLD}{prompt} (y/N): {RST}").strip().lower() in ("y", "yes")


# ──────────────────────────────────────────────
#  종목명/코드 → 코드  (한글 검색 지원)
# ──────────────────────────────────────────────
def resolve_symbol(client, query):
    """종목명/코드/티커를 코드로 변환. 국장(6자리)·미장(티커)·한글이름 모두 지원."""
    q = (query or "").strip()
    if not q:
        return None
    if re.fullmatch(r"\d{6}", q):            # 국내 6자리 코드
        return q
    matches = find_stocks(q)
    # 정확히 일치하는 이름이 있으면 우선 사용
    if matches and matches[0][0].replace(" ", "").lower() == q.replace(" ", "").lower():
        name, code = matches[0]
        print(f"{G}  → {name} ({code}){RST}")
        return code
    up = q.upper()
    if up in US_TICKERS:                     # 알려진 미국 티커 (예: AAPL, QQQ)
        return up
    if not matches and re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", up):  # 목록에 없어도 티커 형태면 시도
        return up
    if not matches:
        print(f"{Y}  '{q}' 종목을 못 찾았어요. 6자리 코드로 입력하거나 토스앱에서 코드를 확인해 주세요.{RST}")
        return None
    if len(matches) == 1:
        name, code = matches[0]
    else:
        print(f"{GRY}  여러 종목이 검색됐어요:{RST}")
        for i, (nm, cd) in enumerate(matches[:15], 1):
            print(f"    {i}. {nm} ({cd})")
        sel = ask("번호 선택(취소=빈칸)")
        if not sel.isdigit() or not (1 <= int(sel) <= len(matches[:15])):
            return None
        name, code = matches[int(sel) - 1]
    print(f"{G}  → {name} ({code}){RST}")
    return code


def ask_symbol(client, label="종목명 또는 코드 (예: 삼성전자)", default="삼성전자"):
    return resolve_symbol(client, ask(label, default))


def kr_market_hint(sym):
    """국장(6자리) 종목인데 정규장 시간이 아니면 경고 문구 반환. (사용자 PC 시계=KST 가정)"""
    if not re.fullmatch(r"\d{6}", sym or ""):
        return None  # 미장 등은 제외
    now = datetime.now()
    if now.weekday() >= 5:
        return "주말에는 국장이 닫혀 있어요. 평일 09:00~15:30 에 주문하세요."
    hm = now.hour * 60 + now.minute
    if hm < 9 * 60 or hm > 15 * 60 + 30:
        return ("지금은 국장 정규장(09:00~15:30) 시간이 아니에요. "
                "장 시간이 아니면 주문이 거절(order-hours-closed)될 수 있어요.")
    return None


def resolve_many(client, raw):
    """콤마로 구분된 이름/코드 → 코드 리스트."""
    codes = []
    for part in raw.split(","):
        c = resolve_symbol(client, part)
        if c:
            codes.append(c)
    return codes


def quote_head(client, sym):
    """차트 헤더용 (종목명, 현재가, 전일대비 등락, 등락률). 현재가 메뉴와 동일 기준."""
    try:
        q = client.get_all_quotes([sym]).get(sym, {})
        return (q.get("name") or sym, q.get("price"), q.get("change"), q.get("change_pct"))
    except Exception:
        return sym, None, None, None


def fetch_1m_today(client, sym, max_pages=8):
    """1분봉을 페이지네이션으로 수집해 '가장 최근 거래일' 하루치만 반환."""
    collected = {}
    before = None
    latest_date = None
    for _ in range(max_pages):
        page = client.get_candles_raw(sym, "1m", 200, before=before)
        cs = page.get("candles", [])
        if not cs:
            break
        dates = [(c.get("timestamp", "") or "")[:10] for c in cs]
        if latest_date is None:
            latest_date = max(dates)
        for c in cs:
            collected[c.get("timestamp")] = c
        before = page.get("nextBefore")
        if min(dates) < latest_date or not before:  # 이전 거래일까지 닿음 → 오늘 다 모음
            break
    return [c for c in collected.values()
            if (c.get("timestamp", "") or "")[:10] == latest_date]


def agg_candles(candles, minutes=10):
    """1분봉을 N분봉으로 묶기 (토스 API 는 1m/1d 만 제공)."""
    cs = sorted(candles, key=lambda c: c.get("timestamp", ""))
    buckets = {}
    order = []
    for c in cs:
        ts = c.get("timestamp", "")
        hourkey = ts[:13]            # YYYY-MM-DDTHH
        mn = int(ts[14:16]) if len(ts) >= 16 and ts[14:16].isdigit() else 0
        key = f"{hourkey}:{mn // minutes}"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(c)
    out = []
    for key in order:
        g = buckets[key]
        out.append({
            "timestamp": g[0].get("timestamp"),
            "openPrice": g[0].get("openPrice"),
            "highPrice": str(max(num(x.get("highPrice")) for x in g)),
            "lowPrice": str(min(num(x.get("lowPrice")) for x in g)),
            "closePrice": g[-1].get("closePrice"),
            "volume": str(sum(num(x.get("volume")) for x in g)),
        })
    return out


def render_chart(candles, height=14, name="", code="", price=None, change=None, pct=None):
    """터미널 캔들 차트 (빨강=상승, 파랑=하락).
    price/change/pct 를 주면 헤더에 전일대비 등락으로 표시(다른 화면과 동일 기준)."""
    cs = sorted(candles, key=lambda c: c.get("timestamp", ""))
    if not cs:
        return f"{GRY}(데이터 없음){RST}"
    O = [num(c.get("openPrice")) for c in cs]
    H = [num(c.get("highPrice")) for c in cs]
    L = [num(c.get("lowPrice")) for c in cs]
    C_ = [num(c.get("closePrice")) for c in cs]
    n = len(cs)
    maxP, minP = max(H), min(L)
    span = (maxP - minP) or 1

    def Y(p):
        return int(round((maxP - p) / span * (height - 1)))

    out = []
    if change is not None and pct is not None:   # 전일대비(현재가 메뉴와 동일)
        shown = price if price is not None else C_[-1]
        dcol = UP if change >= 0 else DOWN
        label = "전일대비"
        head = f"{dcol}{change:+,.0f} ({pct:+.2f}%){RST}"
    else:                                         # 폴백: 차트 구간 변동
        shown = C_[-1]
        diff = C_[-1] - C_[0]
        dcol = UP if diff >= 0 else DOWN
        label = "구간"
        head = f"{dcol}{diff:+,.0f} ({(diff / C_[0] * 100) if C_[0] else 0:+.2f}%){RST}"
    out.append(f"{BLD}{C}{name} ({code}){RST}  현재가 {BLD}{shown:,.0f}{RST}  "
               f"{head}  {GRY}{label} · [{n}봉]{RST}")

    for r in range(height):
        cells = []
        for i in range(n):
            hy, ly = Y(H[i]), Y(L[i])
            bt, bb = Y(max(O[i], C_[i])), Y(min(O[i], C_[i]))
            col = UP if C_[i] >= O[i] else DOWN
            if bt <= r <= bb:
                ch = BODY
            elif hy <= r <= ly:
                ch = WICK
            else:
                ch = " "
            cells.append(f"{col}{ch}{RST}" if ch != " " else " ")
        price = maxP - (r / (height - 1)) * span
        out.append(f"{GRY}{price:>10,.0f}{RST} │" + "".join(cells))

    axis = f"{' ':>10} └" + "─" * n
    t0, t1 = cs[0].get("timestamp", "") or "", cs[-1].get("timestamp", "") or ""
    if t0[:10] == t1[:10] and len(t0) >= 16:   # 같은 날(장중) → 시:분 표시
        d0, d1 = t0[11:16], t1[11:16]
    else:
        d0, d1 = t0[:10], t1[:10]
    out.append(axis)
    out.append(f"{' ':>12}{GRY}{d0}{' ' * max(1, n - len(d0) - len(d1))}{d1}{RST}")
    return "\n".join(out)


def official_name(client, code):
    """API 로 실제 종목명 확인 (오주문 방지). 실패 시 코드 그대로."""
    try:
        info = client.get_stocks([code])
        if info:
            return info[0].get("name") or code
    except Exception:
        pass
    return code


# ──────────────────────────────────────────────
#  로그인 / 계좌선택
# ──────────────────────────────────────────────
def login(mock: bool) -> TossAPIClient:
    print(f"\n{BLD}{C}토스증권 Open API CLI{RST}")
    hr()
    if mock:
        print(f"{Y}● MOCK 모드{RST} — 가상 데이터, 실제 주문 없음")
        client = TossAPIClient(mock=True)
        client.authorize()
        return client

    # API Key (덜 민감 → 입력은 보이게, 환경변수 있으면 생략)
    cid = os.getenv("TOSS_CLIENT_ID")
    if cid:
        print(f"{GRY}API Key: 환경변수(TOSS_CLIENT_ID) 사용{RST}")
    else:
        cid = input(f"{Y}🪪 API Key(client_id) 입력: {RST}").strip()
    # Secret Key (민감 → 화면 비표시)
    secret = os.getenv("TOSS_CLIENT_SECRET")
    if secret:
        print(f"{GRY}Secret Key: 환경변수(TOSS_CLIENT_SECRET) 사용{RST}")
    else:
        print(f"{GRY}Secret Key 는 화면에 표시되지 않습니다.{RST}")
        secret = getpass.getpass(f"{Y}🔑 Secret Key 입력: {RST}").strip()
    if not (cid and secret):
        print(f"{R}API Key / Secret Key 가 비어 있습니다. 종료합니다.{RST}")
        sys.exit(1)

    client = TossAPIClient(client_id=cid, client_secret=secret, mock=False)
    try:
        print(f"{GRY}인증 중...{RST}")
        client.authorize()
    except TossAPIError as e:
        print(f"{R}인증 실패: {e}{RST}")
        sys.exit(1)
    except Exception as e:
        print(f"{R}연결 실패: {e}{RST}")
        sys.exit(1)

    print(f"{G}● LIVE 모드 인증 성공{RST}")
    select_account(client)
    return client


def select_account(client: TossAPIClient):
    accts = client.accounts
    if not accts:
        print(f"{Y}계좌가 없습니다.{RST}")
        return
    if len(accts) == 1:
        client.account_seq = accts[0]["accountSeq"]
    else:
        title("계좌 선택")
        for i, a in enumerate(accts):
            print(f"  {i+1}. {a.get('accountNo')}  ({a.get('accountType')})  seq={a.get('accountSeq')}")
        idx = ask("계좌 번호 선택", "1")
        try:
            client.account_seq = accts[int(idx) - 1]["accountSeq"]
        except Exception:
            client.account_seq = accts[0]["accountSeq"]
    print(f"{G}선택 계좌 seq={client.account_seq}{RST}")


# ──────────────────────────────────────────────
#  공통 출력 헬퍼
# ──────────────────────────────────────────────
def err(e):
    if isinstance(e, TossAPIError):
        print(f"{R}오류 [{e.status} {e.code}] {e.message}{RST}")
        if e.data:
            print(f"{GRY}  힌트: {e.data}{RST}")
    else:
        print(f"{R}오류: {e}{RST}")


# ──────────────────────────────────────────────
#  1. 계좌 / 자산
# ──────────────────────────────────────────────
def menu_account(client):
    while True:
        title("계좌 / 자산")
        print("  1) 보유주식 (내 주식 조회)   2) 매수가능금액   3) 계좌목록   4) 매매수수료   0) 뒤로")
        c = ask("선택")
        try:
            if c == "1":
                show_holdings(client)
            elif c == "2":
                cur = ask("통화 (KRW/USD)", "KRW").upper()
                bp = client.get_buying_power(cur)
                print(f"  {BLD}매수가능: {won(bp.get('cashBuyingPower'))} {bp.get('currency','')}{RST}")
            elif c == "3":
                for a in client.get_accounts():
                    print(f"  • {a.get('accountNo')}  {a.get('accountType')}  seq={a.get('accountSeq')}")
            elif c == "4":
                for cm in client.get_commissions():
                    period = f"{cm.get('startDate') or '-'} ~ {cm.get('endDate') or '현재'}"
                    print(f"  • {cm.get('marketCountry')}  수수료율 {float(cm.get('commissionRate',0))*100:.4f}%  ({period})")
            elif c == "0":
                return
        except Exception as e:
            err(e)


def show_holdings(client):
    ov = client.get_holdings()
    items = ov.get("items", [])
    if not items:
        print(f"{GRY}보유 종목이 없습니다.{RST}")
        return
    hr()
    print(BLD + dcell("종목", 14) + dcell("수량", 7, True) + dcell("평균가", 10, True)
          + dcell("현재가", 10, True) + dcell("평가금액", 12, True)
          + dcell("손익", 12, True) + dcell("수익률", 9, True) + RST)
    hr()
    tot_val = tot_pl = 0
    for it in items:
        mv, pl_o = it.get("marketValue", {}), it.get("profitLoss", {})
        # 토스 앱과 동일하게 매도비용(수수료·세금) 차감 후 값 사용
        val = num(mv.get("amountAfterCost") if mv.get("amountAfterCost") is not None else mv.get("amount"))
        pl = num(pl_o.get("amountAfterCost") if pl_o.get("amountAfterCost") is not None else pl_o.get("amount"))
        rate = num(pl_o.get("rateAfterCost") if pl_o.get("rateAfterCost") is not None else pl_o.get("rate")) * 100
        tot_val += val
        tot_pl += pl
        col = sign_color(pl)
        name = it.get("name") or it.get("symbol")
        print(dcell(name, 14) + f"{won(it.get('quantity')):>7}{won(it.get('averagePurchasePrice')):>10}"
              f"{won(it.get('lastPrice')):>10}{won(val):>12}"
              f"{col}{pl:>+12,.0f}{RST}{col}{rate:>+8.2f}%{RST}")
    hr()
    # 총계: overview 의 차감 후 값(krw)이 있으면 그대로 사용(가장 정확)
    mvt = ov.get("marketValue", {}).get("amountAfterCost")
    if isinstance(mvt, dict) and mvt.get("krw") is not None:
        tot_val = num(mvt["krw"])
    plt = ov.get("profitLoss", {}).get("amountAfterCost")
    if isinstance(plt, dict) and plt.get("krw") is not None:
        tot_pl = num(plt["krw"])
    col = sign_color(tot_pl)
    print(f"{BLD}총 평가금액 {won(tot_val)}   총 손익 {col}{tot_pl:>+,.0f}{RST}")


# ──────────────────────────────────────────────
#  2. 시세
# ──────────────────────────────────────────────
def show_prices(client, codes):
    """현재가 + 등락/등락률 (API 에 없으면 전일 종가로 계산)."""
    quotes = client.get_all_quotes(codes)
    for code in codes:
        q = quotes.get(code)
        if not q:
            print(f"  {code:<8} {GRY}조회 실패{RST}")
            continue
        chg, pct = q.get("change", 0), q.get("change_pct", 0)
        col = UP if chg >= 0 else DOWN
        sg = "+" if chg >= 0 else ""
        print(f"  {GRY}{code:<7}{RST}{BLD}{dcell(q.get('name') or code, 16)}{RST}"
              f"{won(q.get('price')):>11}  {col}{sg}{chg:,.0f} ({sg}{pct:.2f}%){RST}")


def show_ranking(client=None):
    """네이버 금융 기반 주식 순위."""
    title("주식 순위")
    print(f"  {GRY}(출처: 네이버 금융){RST}")
    print("  종류: 1)거래대금  2)거래량  3)시가총액  4)상승률  5)하락률  6)인기검색")
    k = ask("종류 선택", "1")
    kind = market_rank.KINDS.get(k)
    if not kind:
        return
    print("  시장: 1)코스피  2)코스닥  3)통합")
    m = ask("시장 선택", "1")
    market = market_rank.MARKETS.get(m, market_rank.MARKETS["1"])
    try:
        count = int(ask("몇 위까지 볼까요 (1~100)", "20"))
    except ValueError:
        count = 20
    count = min(100, max(1, count))
    print(f"{GRY}  불러오는 중...{RST}")
    try:
        rows = market_rank.ranking(kind[0], market[0], count=count)
    except Exception as e:
        print(f"{R}  순위 조회 실패(네트워크?): {e}{RST}")
        return
    print(f"\n{BLD}{C}[{market[1]}] {kind[1]} 상위 {count}{RST}")
    if rows:
        at = (rows[0].get("at") or "")[:16].replace("T", " ")
        st = {"OPEN": "장중·실시간", "CLOSE": "장마감·당일최종"}.get(rows[0].get("status"), "")
        note = "당일 누적" if kind[0] in ("value", "volume") else "당일 기준"
        print(f"{GRY}  기준: {at}  {st}  ({note}){RST}")
    hr()
    print(f"{GRY}  {'#':>2}. {dcell('종목', 18)} 코드     현재가      등락률   지표{RST}")
    for r in rows:
        pct = float(r["changePct"] or 0)
        col = UP if pct >= 0 else DOWN
        extra = {"value": f"거래대금 {r['value']}", "volume": f"거래량 {r['volume']}",
                 "cap": f"시총 {r['cap']}"}.get(kind[0], "")
        print(f"  {r['rank']:>2}. {BLD}{dcell(r['name'], 18)}{RST} {GRY}{r['code']:<6}{RST} "
              f"{r['price']:>9}  {col}{pct:>+7.2f}%{RST}  {GRY}{extra}{RST}")
    print(f"\n{GRY}  종목명을 그대로 조회/주문에 쓰면 됩니다.{RST}")


def menu_market(client):
    while True:
        title("시세")
        print("  1) 현재가   2) 호가   3) 체결내역   4) 캔들   5) 상/하한가")
        print("  6) 종목정보   7) 매수유의   8) 📈 차트   9) 🏆 순위   0) 뒤로")
        c = ask("선택")
        try:
            if c == "1":
                codes = resolve_many(client, ask("종목명/코드 (콤마로 여러개)", "삼성전자,SK하이닉스"))
                if not codes:
                    continue
                show_prices(client, codes)
            elif c == "2":
                sym = ask_symbol(client)
                if not sym:
                    continue
                ob = client.get_orderbook(sym)
                print(f"{GRY}--- 매도호가 ---{RST}")
                for a in reversed(ob.get("asks", [])):
                    print(f"  {B}{won(a['price']):>10}{RST}  {won(a['volume']):>10}")
                print(f"{GRY}--- 매수호가 ---{RST}")
                for b in ob.get("bids", []):
                    print(f"  {R}{won(b['price']):>10}{RST}  {won(b['volume']):>10}")
            elif c == "3":
                sym = ask_symbol(client)
                if not sym:
                    continue
                cnt = int(ask("건수(최대50)", "20"))
                for t in client.get_trades(sym, cnt):
                    print(f"  {t.get('timestamp','')[11:19]}  {won(t['price']):>10}  x {won(t['volume'])}")
            elif c == "4":
                sym = ask_symbol(client)
                if not sym:
                    continue
                itv = ask("봉(1m/1d)", "1d")
                cnt = int(ask("개수(최대200)", "20"))
                page = client.get_candles_raw(sym, itv, cnt)
                for cd in page.get("candles", []):
                    print(f"  {cd.get('timestamp','')[:16]}  O{won(cd['openPrice'])} H{won(cd['highPrice'])} "
                          f"L{won(cd['lowPrice'])} C{won(cd['closePrice'])}  V{won(cd.get('volume'))}")
            elif c == "5":
                sym = ask_symbol(client)
                if not sym:
                    continue
                pl = client.get_price_limits(sym)
                print(f"  상한가 {R}{won(pl.get('upperLimitPrice'))}{RST}   하한가 {B}{won(pl.get('lowerLimitPrice'))}{RST}")
            elif c == "6":
                codes = resolve_many(client, ask("종목명/코드 (콤마로 여러개)", "삼성전자"))
                if not codes:
                    continue
                for s in client.get_stocks(codes):
                    print(f"  {s.get('symbol')} {BLD}{s.get('name','')}{RST} / {s.get('englishName','')}  "
                          f"[{s.get('market','')}/{s.get('securityType','')}/{s.get('status','')}]")
            elif c == "7":
                sym = ask_symbol(client)
                if not sym:
                    continue
                ws = client.get_stock_warnings(sym)
                if not ws:
                    print(f"{G}  유의사항 없음{RST}")
                for w in ws:
                    print(f"  {Y}⚠ {w.get('warningType')}{RST}  {w.get('startDate','')}~{w.get('endDate','')}")
            elif c == "9":
                show_ranking(client)
            elif c == "8":
                sym = ask_symbol(client)
                if not sym:
                    continue
                itv = ask("봉 (1d 일봉 / 1m 분봉)", "1d")
                try:
                    cnt = int(ask("봉 개수(최대120)", "60"))
                except ValueError:
                    cnt = 60
                cnt = min(120, max(5, cnt))  # 5~120 으로 제한
                page = client.get_candles_raw(sym, itv, cnt)
                nm, pr, ch, pc = quote_head(client, sym)
                print()
                print(render_chart(page.get("candles", []), name=nm, code=sym,
                                   price=pr, change=ch, pct=pc))
            elif c == "0":
                return
        except Exception as e:
            err(e)


# ──────────────────────────────────────────────
#  3. 주문
# ──────────────────────────────────────────────
def menu_order(client):
    while True:
        title("주문")
        print("  1) 매수   2) 매도   3) 미체결주문(OPEN)   4) 종료주문(CLOSED)")
        print("  5) 주문 정정   6) 주문 취소   7) 주문상세   8) 판매가능수량   0) 뒤로")
        c = ask("선택")
        try:
            if c == "1":
                place(client, "BUY")
            elif c == "2":
                place(client, "SELL")
            elif c == "3":
                list_orders(client, "OPEN")
            elif c == "4":
                list_orders(client, "CLOSED")
            elif c == "5":
                modify(client)
            elif c == "6":
                cancel(client)
            elif c == "7":
                oid = ask("주문ID")
                show_order(client.get_order(oid))
            elif c == "8":
                sym = ask_symbol(client)
                if not sym:
                    continue
                sq = client.get_sellable_quantity(sym)
                print(f"  판매가능수량: {BLD}{won(sq.get('sellableQuantity'))}{RST}")
            elif c == "0":
                return
        except Exception as e:
            err(e)


def place(client, side):
    side_ko = "매수" if side == "BUY" else "매도"
    sym = resolve_symbol(client, ask(f"[{side_ko}] 종목명 또는 코드"))
    if not sym:
        return
    name = official_name(client, sym)  # 실제 종목명 확인 (오주문 방지)
    otype = ask("호가유형 (LIMIT 지정가 / MARKET 시장가)", "LIMIT").upper()
    qty = ask("수량")
    price = None
    if otype == "LIMIT":
        price = ask("지정가 (원)")
    tif = ask("유효조건 (DAY/CLS)", "DAY").upper()

    # 사전 확인
    title(f"{side_ko} 주문 확인")
    print(f"  계좌seq : {client.account_seq}")
    print(f"  종목    : {BLD}{name}{RST} ({sym})")
    print(f"  구분    : {BLD}{R if side=='BUY' else B}{side_ko}({side}){RST}")
    print(f"  유형    : {otype}  ({tif})")
    print(f"  수량    : {qty}")
    print(f"  가격    : {won(price) if price else '시장가'}")
    if price and qty:
        try:
            print(f"  예상금액: {BLD}{won(float(price)*float(qty))}{RST} 원")
        except Exception:
            pass
    if client.is_mock:
        print(f"  {Y}(MOCK — 실제 체결 없음){RST}")
    hint = kr_market_hint(sym)
    if hint:
        print(f"  {Y}⚠ {hint}{RST}")

    if not confirm(f"위 내용으로 {side_ko} 주문을 전송할까요?"):
        print(f"{GRY}취소했습니다.{RST}")
        return

    # 위에서 이미 금액/내용 확인을 받았으므로 고액주문 플래그를 자동 처리(거절 방지)
    res = client.create_order(symbol=sym, side=side, order_type=otype,
                              quantity=qty, price=price, time_in_force=tif,
                              confirm_high_value=not client.is_mock)
    print(f"{G}{BLD}✔ 주문 전송 완료{RST}  orderId={res.get('orderId')}")


def modify(client):
    oid = ask("정정할 주문ID")
    if not oid:
        return
    otype = ask("변경 호가유형 (LIMIT/MARKET)", "LIMIT").upper()
    qty = ask("변경 수량(미변경 시 빈칸)") or None
    price = ask("변경 가격(미변경 시 빈칸)") or None
    if not confirm("주문을 정정할까요?"):
        return
    res = client.modify_order(oid, order_type=otype, quantity=qty, price=price)
    print(f"{G}✔ 정정 완료{RST}  새 orderId={res.get('orderId')}")


def cancel(client):
    oid = ask("취소할 주문ID")
    if not oid:
        return
    if not confirm("정말 이 주문을 취소할까요?"):
        return
    res = client.cancel_order(oid)
    print(f"{G}✔ 취소 완료{RST}  새 orderId={res.get('orderId')}")


def list_orders(client, status):
    sym = ask("종목 필터(빈칸=전체)") or None
    page = client.list_orders(status, symbol=sym, limit=50)
    orders = page.get("orders", [])
    if not orders:
        print(f"{GRY}주문이 없습니다.{RST}")
        return
    hr()
    for o in orders:
        side = o.get("side")
        col = R if side == "BUY" else B
        st = STATUS_KO.get(o.get("status", ""), o.get("status", ""))
        ex = o.get("execution", {})
        filled = num(ex.get("filledQuantity"))
        print(f"  {o.get('orderedAt','')[:19]}  {col}{'매수' if side=='BUY' else '매도'}{RST} "
              f"{o.get('symbol'):<8} {o.get('orderType','')} {won(o.get('price')) if o.get('price') else '시장가':>9} "
              f"x{won(o.get('quantity'))}  [{st} {filled}체결]")
        print(f"    {GRY}orderId={o.get('orderId')}{RST}")
    if page.get("hasNext"):
        print(f"{GRY}  ... 다음 페이지 cursor={page.get('nextCursor')}{RST}")


def show_order(o):
    title("주문 상세")
    side = o.get("side")
    st = STATUS_KO.get(o.get("status", ""), o.get("status", ""))
    ex = o.get("execution", {})
    print(f"  orderId : {o.get('orderId')}")
    print(f"  종목    : {o.get('symbol')}   구분: {'매수' if side=='BUY' else '매도'}   유형: {o.get('orderType')}/{o.get('timeInForce')}")
    print(f"  상태    : {BLD}{st}{RST}")
    print(f"  가격/수량: {won(o.get('price')) if o.get('price') else '시장가'} x {won(o.get('quantity'))}")
    print(f"  체결    : {won(ex.get('filledQuantity'))}주 @ 평균 {won(ex.get('averageFilledPrice'))}  "
          f"수수료 {won(ex.get('commission'))} 세금 {won(ex.get('tax'))}")
    print(f"  주문시각: {o.get('orderedAt')}   결제일: {ex.get('settlementDate')}")


# ──────────────────────────────────────────────
#  4. 시장 정보
# ──────────────────────────────────────────────
def _sess(s):
    if not s:
        return "-"
    a = (s.get("startTime", "") or "")[11:16]
    b = (s.get("endTime", "") or "")[11:16]
    return f"{a} ~ {b}" if a or b else "-"


def show_calendar(data, label):
    title(f"{label} 장 운영")
    if not isinstance(data, dict):
        print(f"  {data}")
        return
    rows = [("오늘", "today"), ("이전 영업일", "previousBusinessDay"),
            ("다음 영업일", "nextBusinessDay")]
    shown = False
    for ko, key in rows:
        day = data.get(key)
        if not isinstance(day, dict):
            continue
        src = day.get("integrated", day)  # KR=integrated, US=동일 구조
        reg, pre, aft = src.get("regularMarket"), src.get("preMarket"), src.get("afterMarket")
        print(f"  {BLD}{ko} {day.get('date','')}{RST}")
        print(f"     정규장 {C}{_sess(reg)}{RST}   장전 {_sess(pre)}   장후 {_sess(aft)}")
        shown = True
    if not shown:  # 예상 못한 구조면 원본 표시
        print(f"  {data}")


def menu_info(client):
    while True:
        title("시장 정보")
        print("  1) 환율   2) 국내 장운영(KR)   3) 미국 장운영(US)   0) 뒤로")
        c = ask("선택")
        try:
            if c == "1":
                base = ask("기준통화 (USD/KRW)", "USD").upper()
                quote = ask("표시통화 (KRW/USD)", "KRW").upper()
                xr = client.get_exchange_rate(base, quote)
                arrow = {"UP": R+"▲"+RST, "DOWN": B+"▼"+RST}.get(xr.get("rateChangeType"), "－")
                print(f"  {base}/{quote} = {BLD}{xr.get('rate')}{RST} {arrow}  (기준 {xr.get('midRate')}, {xr.get('basisPoint')}bp)")
            elif c == "2":
                d = ask("날짜(YYYY-MM-DD, 빈칸=오늘)") or None
                show_calendar(client.get_market_calendar("KR", d), "국내(KR)")
            elif c == "3":
                d = ask("날짜(YYYY-MM-DD 미국현지, 빈칸=오늘)") or None
                show_calendar(client.get_market_calendar("US", d), "미국(US)")
            elif c == "0":
                return
        except Exception as e:
            err(e)


# ──────────────────────────────────────────────
#  메인 루프
# ──────────────────────────────────────────────
def mode_label():
    return "쉬움" if MODE == "easy" else "어려움"


def env_badge(client):
    live = (Y + "MOCK" + RST) if client.is_mock else (G + "LIVE" + RST)
    return (f"{live}  모드:{mode_label()}  테마:{THEMES[CUR_THEME]['label']}  "
            f"계좌:{client.account_seq}")


def quick_setup():
    """로그인 직후 테마/모드 빠른 설정 (Enter 로 기본값)."""
    global MODE
    title("화면 설정")
    print("  테마:  1) 컬러(기본)   2) 연한색   3) 흑백(스텔스/회사용)")
    apply_theme(ask("테마 선택", "1") or "1")
    print("  모드:  1) 쉬움(간편)   2) 어려움(전체기능)")
    MODE = "easy" if ask("모드 선택", "2") == "1" else "hard"


def settings(client):
    global MODE
    while True:
        title("설정")
        print(f"  현재 테마: {THEMES[CUR_THEME]['label']}   현재 모드: {mode_label()}")
        print("  1) 테마 변경   2) 모드 변경(쉬움↔어려움)   0) 뒤로")
        c = ask("선택")
        if c == "1":
            print("  1) 컬러(기본)   2) 연한색   3) 흑백(스텔스)")
            apply_theme(ask("테마 번호", CUR_THEME) or CUR_THEME)
            print(f"{G}  → {THEMES[CUR_THEME]['label']} 적용{RST}")
        elif c == "2":
            MODE = "hard" if MODE == "easy" else "easy"
            print(f"{G}  → {mode_label()} 모드로 전환{RST}")
        elif c == "0":
            return


def hard_menu(client):
    title("메인 메뉴")
    print(f"  {env_badge(client)}")
    print("  1) 계좌/자산   2) 시세   3) 주문   4) 시장정보   9) 설정   0) 종료")
    c = ask("선택")
    if c == "1":
        menu_account(client)
    elif c == "2":
        menu_market(client)
    elif c == "3":
        menu_order(client)
    elif c == "4":
        menu_info(client)
    elif c == "9":
        settings(client)
    elif c == "0":
        return False
    return True


def easy_menu(client):
    title("간편 메뉴")
    print(f"  {env_badge(client)}")
    print("  1) 내 주식      2) 현재가       3) 차트")
    print("  4) 사기(매수)   5) 팔기(매도)   6) 미체결/취소")
    print("  7) 🏆 순위      9) 설정         0) 종료")
    c = ask("선택")
    try:
        if c == "1":
            show_holdings(client)
        elif c == "2":
            codes = resolve_many(client, ask("종목명/코드", "삼성전자"))
            if codes:
                show_prices(client, codes)
        elif c == "7":
            show_ranking(client)
        elif c == "3":
            sym = ask_symbol(client)
            if sym:
                p = ask("기간: 1)오늘(10분봉)  2)3개월(일봉)", "1")
                if p == "1":
                    print(f"{GRY}  불러오는 중...{RST}")
                    raw = fetch_1m_today(client, sym)   # 하루치 1분봉
                    candles = agg_candles(raw, 10)       # → 10분봉
                else:
                    candles = client.get_candles_raw(sym, "1d", 60).get("candles", [])
                nm, pr, ch, pc = quote_head(client, sym)
                print()
                print(render_chart(candles, name=nm, code=sym, price=pr, change=ch, pct=pc))
        elif c == "4":
            place(client, "BUY")
        elif c == "5":
            place(client, "SELL")
        elif c == "6":
            list_orders(client, "OPEN")
            if confirm("취소할 주문이 있나요?"):
                cancel(client)
        elif c == "9":
            settings(client)
        elif c == "0":
            return False
    except Exception as e:
        err(e)
    return True


def main():
    mock = "--mock" in sys.argv
    client = login(mock)
    quick_setup()
    try:
        while True:
            ok = easy_menu(client) if MODE == "easy" else hard_menu(client)
            if not ok:
                break
    except (KeyboardInterrupt, EOFError):
        print(f"\n{GRY}종료합니다.{RST}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
