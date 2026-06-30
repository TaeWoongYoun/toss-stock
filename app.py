"""
toss-tui  —  토스증권 오픈 API TUI 클라이언트
실행: python app.py
API 키가 있으면: TOSS_CLIENT_ID=xxx TOSS_CLIENT_SECRET=yyy python app.py
"""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, DataTable, Label, Static, Input, Button, Log
)
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.binding import Binding
from textual.screen import Screen
from textual import work
from textual.css.query import NoMatches
import asyncio
import sys
import getpass
from toss_api import TossAPIClient, MOCK_STOCKS

# ──────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────
CSS = """
/* 기본 배경 */
Screen {
    background: #0d0d14;
    color: #e2e8f0;
}

/* 헤더/푸터 */
Header {
    background: #1a1a2e;
    color: #60a5fa;
    text-style: bold;
}
Footer {
    background: #1a1a2e;
    color: #475569;
}

/* 탭 바 */
#tab-bar {
    height: 3;
    background: #111827;
    border-bottom: solid #1e3a5f;
}
.tab {
    width: 1fr;
    height: 3;
    content-align: center middle;
    color: #64748b;
    border: none;
    background: transparent;
    text-style: none;
}
.tab:hover {
    color: #93c5fd;
    background: #1e2d42;
}
.tab.-active {
    color: #3b82f6;
    text-style: bold;
    background: #1e2d42;
    border-bottom: solid #3b82f6;
}

/* 패널 */
.panel {
    padding: 1 2;
    height: 1fr;
}

/* 카드 */
.card {
    border: solid #1e3a5f;
    background: #111827;
    padding: 1 2;
    margin: 0 1 1 0;
}
.card-title {
    color: #60a5fa;
    text-style: bold;
    margin-bottom: 1;
}

/* 상단 요약 박스 */
#summary-row {
    height: 7;
    margin-bottom: 1;
}
.stat-card {
    width: 1fr;
    height: 7;
    border: solid #1e3a5f;
    background: #0f172a;
    padding: 1 2;
    margin-right: 1;
    content-align: center middle;
}
.stat-label {
    color: #64748b;
    text-align: center;
}
.stat-value {
    text-align: center;
    text-style: bold;
    color: #e2e8f0;
}
.stat-value.up   { color: #f87171; }
.stat-value.down { color: #60a5fa; }

/* 테이블 공통 */
DataTable {
    background: #0f172a;
    border: solid #1e3a5f;
    height: 1fr;
}
DataTable > .datatable--header {
    background: #1a1a2e;
    color: #60a5fa;
    text-style: bold;
}
DataTable > .datatable--cursor {
    background: #1e3a5f;
    color: #e2e8f0;
}

/* 주문 폼 */
#order-form {
    width: 40;
    border: solid #1e3a5f;
    background: #0f172a;
    padding: 1 2;
    margin-left: 1;
}
#order-form Label {
    color: #64748b;
    margin-top: 1;
}
#order-form Input {
    background: #1a1a2e;
    border: solid #1e3a5f;
    color: #e2e8f0;
    margin-bottom: 1;
}
#order-form Input:focus {
    border: solid #3b82f6;
}
.btn-buy {
    background: #991b1b;
    color: white;
    width: 1fr;
    margin-right: 1;
}
.btn-sell {
    background: #1e40af;
    color: white;
    width: 1fr;
}
.btn-buy:hover  { background: #ef4444; }
.btn-sell:hover { background: #3b82f6; }

/* 차트 */
#chart-area {
    height: 22;
    border: solid #1e3a5f;
    background: #0f172a;
    padding: 1 2;
    margin-bottom: 1;
}

/* 로그 */
#trade-log {
    height: 1fr;
    border: solid #1e3a5f;
    background: #0a0f1a;
}

/* 상태 표시 */
#status-bar {
    height: 1;
    background: #111827;
    color: #475569;
    padding: 0 2;
    dock: bottom;
}
.mock-badge {
    color: #f59e0b;
}
.live-badge {
    color: #22c55e;
}

/* 수익/손실 색 */
.profit { color: #f87171; }
.loss   { color: #60a5fa; }
.flat   { color: #94a3b8; }
"""


# ──────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────
def fmt_price(p: int) -> str:
    return f"{p:,}"

def fmt_change(c: float, pct: float) -> tuple[str, str]:
    if c > 0:
        return f"+{c:,.0f} (+{pct:.2f}%)", "up"
    elif c < 0:
        return f"{c:,.0f} ({pct:.2f}%)", "down"
    return f"0 (0.00%)", "flat"

def spark_bar(values: list, width: int = 30, height: int = 6) -> str:
    """ASCII 스파크라인 차트"""
    if not values:
        return ""
    mn, mx = min(values), max(values)
    span = mx - mn or 1
    bars = "▁▂▃▄▅▆▇█"
    lines = []
    normalized = [int((v - mn) / span * (height - 1)) for v in values[-width:]]
    for row in range(height - 1, -1, -1):
        line = ""
        for v in normalized:
            line += "█" if v >= row else " "
        lines.append(line)
    return "\n".join(lines)


# ──────────────────────────────────────────────────
# 화면 1: 시세 대시보드
# ──────────────────────────────────────────────────
class QuotePanel(Static):
    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            with Horizontal(id="summary-row"):
                yield Static("", id="kospi-card",  classes="stat-card")
                yield Static("", id="top-gain",    classes="stat-card")
                yield Static("", id="top-loss",    classes="stat-card")
                yield Static("", id="total-vol",   classes="stat-card")
            yield DataTable(id="quote-table", cursor_type="row")

    def on_mount(self):
        tbl = self.query_one("#quote-table", DataTable)
        tbl.add_columns("종목코드", "종목명", "현재가", "등락", "등락률", "거래량")
        self.refresh_quotes()
        self.set_interval(5, self.refresh_quotes)

    @work(exclusive=True)
    async def refresh_quotes(self):
        api: TossAPIClient = self.app.api
        quotes = await asyncio.to_thread(api.get_all_quotes)

        tbl = self.query_one("#quote-table", DataTable)
        tbl.clear()

        gains, losses = [], []
        total_vol = 0

        for ticker, q in quotes.items():
            change_str, cls = fmt_change(q["change"], q["change_pct"])
            price_str  = fmt_price(q["price"])
            vol_str    = f"{q['volume']:,}"
            total_vol += q["volume"]

            if q["change_pct"] > 0:
                gains.append((q["change_pct"], q["name"]))
                tbl.add_row(ticker, q["name"],
                            f"[bold red]{price_str}[/]",
                            f"[red]{change_str}[/]",
                            f"[red]{change_str}[/]",
                            vol_str)
            elif q["change_pct"] < 0:
                losses.append((q["change_pct"], q["name"]))
                tbl.add_row(ticker, q["name"],
                            f"[bold blue]{price_str}[/]",
                            f"[blue]{change_str}[/]",
                            f"[blue]{change_str}[/]",
                            vol_str)
            else:
                tbl.add_row(ticker, q["name"], price_str, change_str, change_str, vol_str)

        # 요약 카드 업데이트
        kospi = self.query_one("#kospi-card", Static)
        kospi.update(
            "[bold #60a5fa]KOSPI[/]\n"
            "[bold white]2,748.32[/]\n"
            "[red]+12.43 (+0.45%)[/]"
        )
        if gains:
            top = max(gains)
            self.query_one("#top-gain", Static).update(
                "[bold #60a5fa]상승 1위[/]\n"
                f"[bold]{top[1]}[/]\n"
                f"[red]+{top[0]:.2f}%[/]"
            )
        if losses:
            bot = min(losses)
            self.query_one("#top-loss", Static).update(
                "[bold #60a5fa]하락 1위[/]\n"
                f"[bold]{bot[1]}[/]\n"
                f"[blue]{bot[0]:.2f}%[/]"
            )
        self.query_one("#total-vol", Static).update(
            "[bold #60a5fa]총 거래량[/]\n"
            f"[bold]{total_vol:,}[/]\n"
            "[#64748b]주[/]"
        )


# ──────────────────────────────────────────────────
# 화면 2: 포트폴리오
# ──────────────────────────────────────────────────
class PortfolioPanel(Static):
    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            with Horizontal(id="summary-row"):
                yield Static("", id="total-value",  classes="stat-card")
                yield Static("", id="total-profit",  classes="stat-card")
                yield Static("", id="profit-pct",    classes="stat-card")
                yield Static("", id="cash-balance",  classes="stat-card")
            yield DataTable(id="portfolio-table", cursor_type="row")

    def on_mount(self):
        tbl = self.query_one("#portfolio-table", DataTable)
        tbl.add_columns("종목명", "보유수량", "평균단가", "현재가", "평가금액", "손익", "수익률")
        self.refresh_portfolio()
        self.set_interval(10, self.refresh_portfolio)

    @work(exclusive=True)
    async def refresh_portfolio(self):
        api: TossAPIClient = self.app.api
        portfolio = await asyncio.to_thread(api.get_portfolio)

        tbl = self.query_one("#portfolio-table", DataTable)
        tbl.clear()

        total_value = 0
        total_profit = 0
        total_cost = 0

        for item in portfolio:
            value  = item["qty"] * item["cur_price"]
            profit = item["profit"]
            pct    = item["profit_pct"]
            total_value  += value
            total_profit += profit
            total_cost   += item["avg_price"] * item["qty"]

            p_color = "red" if profit >= 0 else "blue"
            tbl.add_row(
                item["name"],
                f"{item['qty']:,}주",
                f"{fmt_price(item['avg_price'])}원",
                f"{fmt_price(item['cur_price'])}원",
                f"[bold]{fmt_price(value)}원[/]",
                f"[{p_color}]{'+' if profit >= 0 else ''}{profit:,}원[/]",
                f"[{p_color}]{'+' if pct >= 0 else ''}{pct:.2f}%[/]",
            )

        total_pct = ((total_profit / total_cost) * 100) if total_cost else 0
        p_color   = "red" if total_profit >= 0 else "blue"
        cash      = 3_850_000  # Mock 예수금

        self.query_one("#total-value", Static).update(
            "[bold #60a5fa]총 평가금액[/]\n"
            f"[bold]{fmt_price(total_value)}[/]\n[#64748b]원[/]"
        )
        self.query_one("#total-profit", Static).update(
            "[bold #60a5fa]총 손익[/]\n"
            f"[bold {p_color}]{'+' if total_profit >= 0 else ''}{total_profit:,}[/]\n[#64748b]원[/]"
        )
        self.query_one("#profit-pct", Static).update(
            "[bold #60a5fa]수익률[/]\n"
            f"[bold {p_color}]{'+' if total_pct >= 0 else ''}{total_pct:.2f}%[/]\n"
        )
        self.query_one("#cash-balance", Static).update(
            "[bold #60a5fa]예수금[/]\n"
            f"[bold]{fmt_price(cash)}[/]\n[#64748b]원[/]"
        )


# ──────────────────────────────────────────────────
# 화면 3: 주문 (시세 + 주문 폼)
# ──────────────────────────────────────────────────
class OrderPanel(Static):
    def compose(self) -> ComposeResult:
        with Horizontal(classes="panel"):
            with Vertical(id="order-left"):
                yield Static("", id="chart-area")
                yield DataTable(id="order-quote-table", cursor_type="row")
            with Vertical(id="order-form"):
                yield Label("종목코드")
                yield Input(placeholder="예: 005930", id="inp-ticker")
                yield Label("수량")
                yield Input(placeholder="수량 입력", id="inp-qty")
                yield Label("가격")
                yield Input(placeholder="가격 입력", id="inp-price")
                yield Static("", id="order-result", classes="card")
                with Horizontal():
                    yield Button("매수", id="btn-buy",  classes="btn-buy")
                    yield Button("매도", id="btn-sell", classes="btn-sell")

    def on_mount(self):
        tbl = self.query_one("#order-quote-table", DataTable)
        tbl.add_columns("코드", "종목명", "현재가", "등락")
        self.refresh_order_quotes()
        self.set_interval(5, self.refresh_order_quotes)

    @work(exclusive=True)
    async def refresh_order_quotes(self):
        api: TossAPIClient = self.app.api
        quotes = await asyncio.to_thread(api.get_all_quotes)
        tbl = self.query_one("#order-quote-table", DataTable)
        tbl.clear()
        for ticker, q in quotes.items():
            change_str, _ = fmt_change(q["change"], q["change_pct"])
            color = "red" if q["change"] >= 0 else "blue"
            tbl.add_row(
                ticker, q["name"],
                f"[{color}]{fmt_price(q['price'])}[/]",
                f"[{color}]{change_str}[/]"
            )

        # 차트 (삼성전자 기본)
        ticker = self.query_one("#inp-ticker", Input).value or "005930"
        candles = await asyncio.to_thread(api.get_candles, ticker, 40)
        closes  = [c["close"] for c in candles]
        chart   = spark_bar(closes, width=40, height=8)
        name    = quotes.get(ticker, {}).get("name", ticker)
        price   = quotes.get(ticker, {}).get("price", 0)
        self.query_one("#chart-area", Static).update(
            f"[bold #60a5fa]{name} ({ticker})[/]  "
            f"[bold white]{fmt_price(price)}원[/]\n\n"
            f"[#1e40af]{chart}[/]\n"
            f"[#64748b]← 40일 추이[/]"
        )

    async def on_button_pressed(self, event: Button.Pressed):
        side = "매수" if event.button.id == "btn-buy" else "매도"
        ticker = self.query_one("#inp-ticker", Input).value.strip()
        qty_s  = self.query_one("#inp-qty",    Input).value.strip()
        price_s= self.query_one("#inp-price",  Input).value.strip()

        result_widget = self.query_one("#order-result", Static)

        if not (ticker and qty_s and price_s):
            result_widget.update("[red]종목코드, 수량, 가격을 모두 입력해 주세요.[/]")
            return

        try:
            qty   = int(qty_s.replace(",", ""))
            price = int(price_s.replace(",", ""))
        except ValueError:
            result_widget.update("[red]수량/가격은 숫자로 입력해 주세요.[/]")
            return

        result_widget.update("[yellow]주문 처리 중...[/]")
        api: TossAPIClient = self.app.api
        try:
            res = await asyncio.to_thread(api.place_order, ticker, side, qty, price)
        except Exception as e:
            result_widget.update(f"[red]주문 실패: {e}[/]")
            return

        color = "red" if side == "매수" else "blue"
        result_widget.update(
            f"[{color}][bold]{side} 주문 완료[/bold][/]\n"
            f"주문번호: {res['orderId']}\n"
            f"상태: {res['status']}\n"
            f"{ticker} {qty}주 @ {fmt_price(price)}원"
        )
        self.app.query_one("#trade-log", Log).write_line(
            f"[{self.app.api.is_mock and 'MOCK' or 'LIVE'}] "
            f"{side} {ticker} {qty}주 @ {fmt_price(price)}원 → {res['status']}"
        )


# ──────────────────────────────────────────────────
# 화면 4: 주문 내역
# ──────────────────────────────────────────────────
class HistoryPanel(Static):
    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            yield Label("[bold #60a5fa]주문 내역[/]")
            yield DataTable(id="history-table", cursor_type="row")
            yield Log(id="trade-log", highlight=True)

    def on_mount(self):
        tbl = self.query_one("#history-table", DataTable)
        tbl.add_columns("시간", "종목명", "구분", "수량", "가격", "상태")
        self.refresh_history()

    @work(exclusive=True)
    async def refresh_history(self):
        api: TossAPIClient = self.app.api
        orders = await asyncio.to_thread(api.get_orders)
        tbl = self.query_one("#history-table", DataTable)
        tbl.clear()
        for o in orders:
            color = "red" if o["side"] == "매수" else "blue"
            s_color = "green" if o["status"] == "체결" else "yellow"
            tbl.add_row(
                o["time"], o["name"],
                f"[{color}]{o['side']}[/]",
                f"{o['qty']}주",
                f"{fmt_price(o['price'])}원",
                f"[{s_color}]{o['status']}[/]"
            )


# ──────────────────────────────────────────────────
# 메인 앱
# ──────────────────────────────────────────────────
class TossTUI(App):
    CSS = CSS
    TITLE = "Toss Securities TUI"
    BINDINGS = [
        Binding("1", "tab('quote')",     "시세",       show=True),
        Binding("2", "tab('portfolio')", "포트폴리오", show=True),
        Binding("3", "tab('order')",     "주문",       show=True),
        Binding("4", "tab('history')",   "주문내역",   show=True),
        Binding("r", "refresh",          "새로고침",   show=True),
        Binding("q", "quit",             "종료",       show=True),
    ]

    current_tab = reactive("quote")

    def __init__(self, api: TossAPIClient | None = None):
        super().__init__()
        self.api = api or TossAPIClient(mock=True)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="tab-bar"):
            yield Button("① 시세",       id="tab-quote",     classes="tab -active")
            yield Button("② 포트폴리오", id="tab-portfolio",  classes="tab")
            yield Button("③ 주문",       id="tab-order",     classes="tab")
            yield Button("④ 주문내역",   id="tab-history",   classes="tab")
        yield QuotePanel(id="panel-quote")
        yield PortfolioPanel(id="panel-portfolio")
        yield OrderPanel(id="panel-order")
        yield HistoryPanel(id="panel-history")
        yield Static("", id="status-bar")
        yield Footer()

    async def on_mount(self):
        # 비실서비스 패널 숨기기
        for pid in ["panel-portfolio", "panel-order", "panel-history"]:
            self.query_one(f"#{pid}").display = False

        # API 초기화
        try:
            await asyncio.to_thread(self.api.authorize)
        except Exception as e:
            self.api.is_mock = True
            self.notify(f"인증 실패 → MOCK 모드: {e}", severity="error")
        mode = "[yellow]MOCK 모드[/]" if self.api.is_mock else "[green]LIVE 모드[/]"
        self.query_one("#status-bar", Static).update(
            f" 토스증권 TUI  |  {mode}  |  "
            f"[#475569]실제 API 키: TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 환경변수 설정[/]"
        )

    def action_tab(self, tab_id: str):
        self.current_tab = tab_id
        panels = {"quote": "panel-quote", "portfolio": "panel-portfolio",
                  "order": "panel-order", "history": "panel-history"}
        tabs   = {"quote": "tab-quote", "portfolio": "tab-portfolio",
                  "order": "tab-order", "history": "tab-history"}
        for pid in panels.values():
            self.query_one(f"#{pid}").display = False
        self.query_one(f"#{panels[tab_id]}").display = True

        for tid in tabs.values():
            self.query_one(f"#{tid}", Button).remove_class("-active")
        self.query_one(f"#{tabs[tab_id]}", Button).add_class("-active")

    def action_refresh(self):
        self.action_tab(self.current_tab)

    async def on_button_pressed(self, event: Button.Pressed):
        tab_map = {
            "tab-quote": "quote", "tab-portfolio": "portfolio",
            "tab-order": "order", "tab-history": "history"
        }
        if event.button.id in tab_map:
            self.action_tab(tab_map[event.button.id])
            event.stop()


def build_client() -> TossAPIClient:
    """실행 시 Secret Key 를 안전하게 입력받아 클라이언트 생성.
    --mock 인자 또는 입력을 비우면 MOCK 모드."""
    if "--mock" in sys.argv:
        print("● MOCK 모드로 실행합니다 (실제 주문 없음).")
        return TossAPIClient(mock=True)

    print("토스증권 TUI — LIVE 모드")
    print("  API Key(client_id): 코드 기본값 또는 TOSS_CLIENT_ID 환경변수 사용")
    print("  Secret Key 는 화면에 표시되지 않습니다. (Enter 만 누르면 MOCK 모드)")
    try:
        secret = getpass.getpass("🔑 Secret Key 입력: ").strip()
    except (KeyboardInterrupt, EOFError):
        secret = ""
    if not secret:
        print("● Secret 미입력 → MOCK 모드로 실행합니다.")
        return TossAPIClient(mock=True)
    return TossAPIClient(client_secret=secret, mock=False)


if __name__ == "__main__":
    TossTUI(api=build_client()).run()
