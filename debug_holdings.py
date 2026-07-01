"""
보유주식 원본 응답 확인용 (잔고 계산 진단).
실행:  python debug_holdings.py
→ 출력된 JSON 을 그대로 복사해서 붙여넣어 주세요. (계좌번호/시크릿은 포함되지 않습니다)
"""

import os
import json
import getpass

from toss_api import TossAPIClient


def main():
    cid = os.getenv("TOSS_CLIENT_ID") or input("🪪 API Key(client_id): ").strip()
    sec = os.getenv("TOSS_CLIENT_SECRET") or getpass.getpass("🔑 Secret Key: ").strip()
    c = TossAPIClient(client_id=cid, client_secret=sec, mock=False)
    c.authorize()

    ov = c.get_holdings()
    print("\n===== overview 최상위 키 =====")
    print(list(ov.keys()) if isinstance(ov, dict) else type(ov))

    # 총계 관련(overview) 필드가 있으면 그대로 출력
    for k in ("totalPurchaseAmount", "marketValue", "profitLoss", "dailyProfitLoss"):
        if isinstance(ov, dict) and k in ov and k != "items":
            print(f"\n----- overview.{k} -----")
            print(json.dumps(ov[k], ensure_ascii=False, indent=2))

    items = ov.get("items", []) if isinstance(ov, dict) else []
    print(f"\n===== 보유 종목 수: {len(items)} =====")
    if items:
        print("----- items[0] 전체 -----")
        print(json.dumps(items[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
