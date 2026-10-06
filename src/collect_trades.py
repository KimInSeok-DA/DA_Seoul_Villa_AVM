"""연립다세대 매매·전월세 실거래를 구·월 단위로 수집한다.

사용: python src/collect_trades.py [--start 202010] [--end 202610] [--refresh-recent 3]

- 원본 XML: data/raw/{kind}/{LAWD_CD}_{YYYYMM}_p{page}.xml (이미 있으면 다시 받지 않음)
- 최근 N개월은 신고·해제가 늦게 반영되므로 매번 다시 받는다(--refresh-recent)
- 수집 기록: data/raw/collect_log.csv (구·월·종류별 totalCount, 받은 건수, 수집 시각)
- 합본: data/raw/{kind}_all.csv
"""
import argparse
import csv
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

LAWD_CDS = {"11500": "강서구", "11620": "관악구", "11680": "강남구"}
ENDPOINTS = {
    "trade": "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "rent": "https://apis.data.go.kr/1613000/RTMSDataSvcRHRent/getRTMSDataSvcRHRent",
}
ROWS = 1000


def months(start, end):
    y, m = int(start[:4]), int(start[4:])
    while f"{y}{m:02d}" <= end:
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch(url, params, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            root = ET.fromstring(r.content)
            code = root.findtext(".//resultCode")
            if code in ("000", "00"):
                return r.content, root
            msg = f"resultCode={code} {root.findtext('.//resultMsg')}"
        except (requests.RequestException, ET.ParseError) as e:
            msg = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(msg)


def collect_month(kind, lawd, ym, key, refresh):
    """한 구·한 달의 모든 페이지를 받아 item 목록과 totalCount를 돌려준다."""
    folder = RAW / kind
    folder.mkdir(parents=True, exist_ok=True)
    items, page, total = [], 1, None
    while True:
        path = folder / f"{lawd}_{ym}_p{page}.xml"
        if path.exists() and not refresh:
            root = ET.parse(path).getroot()
        else:
            content, root = fetch(ENDPOINTS[kind], {"serviceKey": key, "LAWD_CD": lawd,
                                                    "DEAL_YMD": ym, "pageNo": page,
                                                    "numOfRows": ROWS})
            path.write_bytes(content)
            time.sleep(0.2)
        total = int(root.findtext(".//totalCount") or 0)
        items += [{c.tag: (c.text or "").strip() for c in it} for it in root.findall(".//item")]
        if page * ROWS >= total:
            return items, total
        page += 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="202010")
    ap.add_argument("--end", default="202610")
    ap.add_argument("--refresh-recent", type=int, default=3)
    ap.add_argument("--kinds", default="trade,rent")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.getenv("DATA_GO_KR_API_KEY")
    if not key:
        sys.exit(".env에 DATA_GO_KR_API_KEY가 비어 있습니다.")

    all_months = list(months(args.start, args.end))
    recent = set(all_months[-args.refresh_recent:]) if args.refresh_recent else set()
    log_rows = []
    for kind in args.kinds.split(","):
        frames = []
        for lawd, name in LAWD_CDS.items():
            for ym in all_months:
                items, total = collect_month(kind, lawd, ym, key, ym in recent)
                log_rows.append({"kind": kind, "lawd_cd": lawd, "sigungu": name, "ym": ym,
                                 "total_count": total, "received": len(items),
                                 "collected_at": datetime.now().isoformat(timespec="seconds")})
                if len(items) != total:
                    print(f"[경고] {kind} {name} {ym}: totalCount {total} != 받은 {len(items)}")
                if items:
                    df = pd.DataFrame(items)
                    df["query_ym"] = ym
                    frames.append(df)
            print(f"{kind} {name}: 완료")
        out = pd.concat(frames, ignore_index=True)
        out.to_csv(RAW / f"{kind}_all.csv", index=False, encoding="utf-8-sig")
        print(f"{kind}: {len(out):,}건 -> data/raw/{kind}_all.csv")

    with open(RAW / "collect_log.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(log_rows[0]))
        w.writeheader()
        w.writerows(log_rows)


if __name__ == "__main__":
    main()
