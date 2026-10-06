"""연립다세대 매매 실거래가 API를 1개 구·1개월만 호출해 실제 응답 필드를 확인한다.

사용: python src/probe_trade_api.py [LAWD_CD] [DEAL_YMD]
기본값은 관악구(11620) 2026-08. 원본 XML은 data/raw/probe/에 저장한다.
"""
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv

URL = "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"
ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    key = os.getenv("DATA_GO_KR_API_KEY")
    if not key:
        sys.exit(".env에 DATA_GO_KR_API_KEY가 비어 있습니다.")

    lawd_cd = sys.argv[1] if len(sys.argv) > 1 else "11620"
    deal_ymd = sys.argv[2] if len(sys.argv) > 2 else "202608"
    params = {"serviceKey": key, "LAWD_CD": lawd_cd, "DEAL_YMD": deal_ymd,
              "pageNo": 1, "numOfRows": 1000}
    resp = requests.get(URL, params=params, timeout=30)
    print("HTTP", resp.status_code)

    out = ROOT / "data" / "raw" / "probe" / f"trade_{lawd_cd}_{deal_ymd}.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    print("saved", out.relative_to(ROOT))

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        print(resp.text[:500])
        return
    print("resultCode:", root.findtext(".//resultCode"), root.findtext(".//resultMsg"))
    print("totalCount:", root.findtext(".//totalCount"))
    items = root.findall(".//item")
    print("items in page:", len(items))
    if items:
        print("\n[첫 거래의 필드]")
        for child in items[0]:
            print(f"  {child.tag:24} {(child.text or '').strip()}")


if __name__ == "__main__":
    main()
