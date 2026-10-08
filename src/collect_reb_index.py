"""한국부동산원 연립/다세대 월간 매매 지수(서울·권역)를 받는다 → data/reference/reb_villa_index.csv

사용: python src/collect_reb_index.py   (환경변수 REB_API_KEY, R-ONE 부동산통계정보시스템 Open API 인증키)

- 출처: 한국부동산원 R-ONE Open API `SttsApiTblData`(공공데이터포털 15134761, 이용허락범위 제한 없음)
  - A_2024_00080 (월) 매매가격지수_연립/다세대: 전국주택가격동향조사(표본 조사), 서울·권역 단위, 2026.06 = 100
  - A_2024_00185 (월) 지역별 매매지수_연립/다세대: 공동주택 실거래가격지수(신고된 거래), 서울 단위
- 쓰임: 직접 만든 구별 시점 지수(src/avm.py TimeIndex)가 공식 지수와 같은 방향으로 움직이는지 검증(1008_03).
  모델 입력으로는 쓰지 않는다
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "reference" / "reb_villa_index.csv"
URL = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
SERIES = [  # (통계표, 지역 분류 ID, 이름)
    ("A_2024_00080", "500008", "서울(동향조사)"),
    ("A_2024_00080", "520014", "서남권(동향조사)"),  # 강서·관악 포함
    ("A_2024_00080", "520015", "동남권(동향조사)"),  # 강남 포함
    ("A_2024_00185", "500007", "서울(실거래)"),
]


def fetch(key, statbl, cls):
    rows, page = [], 1
    while True:
        q = f"KEY={key}&Type=json&pIndex={page}&pSize=1000&STATBL_ID={statbl}&DTACYCLE_CD=MM&CLS_ID={cls}"
        d = json.load(urllib.request.urlopen(urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "Mozilla/5.0"}), timeout=60))
        if "SttsApiTblData" not in d:
            raise RuntimeError(f"{statbl} {cls}: {d}")
        head, part = d["SttsApiTblData"][0]["head"], d["SttsApiTblData"][1]["row"]
        rows += part
        if len(rows) >= head[0]["list_total_count"] or not part:
            return rows
        page += 1


def main():
    load_dotenv(ROOT / ".env")
    key = os.getenv("REB_API_KEY")
    if not key:
        sys.exit("REB_API_KEY가 없습니다(.env)")
    frames = []
    for statbl, cls, name in SERIES:
        rows = fetch(key, statbl, cls)
        df = pd.DataFrame(rows)
        df = df[df["ITM_NM"] == "지수"] if "ITM_NM" in df else df
        frames.append(pd.DataFrame({"series": name, "statbl_id": statbl, "cls_id": cls, "region": df["CLS_FULLNM"],
                                    "month": pd.to_datetime(df["WRTTIME_IDTFR_ID"], format="%Y%m").dt.to_period("M").astype(str),
                                    "index": df["DTA_VAL"].astype(float)}))
        print(f"{name}: {len(df)}개월 {df['WRTTIME_IDTFR_ID'].min()}～{df['WRTTIME_IDTFR_ID'].max()}")
    out = pd.concat(frames).sort_values(["series", "month"])
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"→ {OUT.relative_to(ROOT)}: {len(out)}행")


if __name__ == "__main__":
    main()
