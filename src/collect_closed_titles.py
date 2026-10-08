"""서울시 폐쇄말소대장 표제부를 받아 권역 3개 구만 남긴다 → data/raw/closed_titles.csv(원본 열 전체)
                                                     → data/reference/closed_titles.csv(PNU·말소일 등 정제)

사용: python src/collect_closed_titles.py   (환경변수 SEOUL_OPEN_API_KEY, 서울 열린데이터광장 인증키)
      python src/collect_closed_titles.py --build-only   (받아 둔 원본으로 정제 파일만 다시 만듦)

- 출처: 서울 열린데이터광장 OA-22432 "서울시 폐쇄말소대장 표제부"(Open API `vBigDjrShTitle`,
  원본 서울 건축주택 종합정보시스템, 공공누리 1유형: 출처표시)
- 지번으로 골라 조회하는 요청 인자가 없어 서울 전체를 1,000건씩 받고 3개 구만 남긴다
- 페이지별 결과를 data/raw/closed_titles/에 저장해, 중간에 멈춰도 다시 실행하면 이어 받는다
- 쓰임: 현행 건축물대장에 없는 지번의 거래가 철거(말소)된 옛 건물의 거래인지 말소일로 확인(1008_02)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "closed_titles"
OUT = ROOT / "data" / "raw" / "closed_titles.csv"
REF = ROOT / "data" / "reference" / "closed_titles.csv"
CODE_CSV = ROOT / "data" / "reference" / "법정동코드_국토교통부_20260630.csv"
SERVICE = "vBigDjrShTitle"
PAGE_SIZE = 1000
SGG_NAMES = ["서울특별시 강서구", "서울특별시 관악구", "서울특별시 강남구"]


def fetch(key, start):
    url = f"http://openapi.seoul.go.kr:8088/{key}/json/{SERVICE}/{start}/{start + PAGE_SIZE - 1}/"
    for wait in (2, 4, 8, 16, None):
        try:
            r = requests.get(url, timeout=60)
            body = r.json()[SERVICE]
            if body["RESULT"]["CODE"] == "INFO-000":
                return body
            err = body["RESULT"]
        except Exception as e:  # 일시 오류는 기다렸다 다시
            err = repr(e)
        if wait is None:
            raise RuntimeError(f"{start}: {err}")
        time.sleep(wait)


def build_reference(df):
    """원본 → PNU별 말소 기록(동 단위 1행). 블록 지번(택지개발 블록)은 PNU로 바꿀 수 없어 뺀다"""
    code = pd.read_csv(CODE_CSV, dtype=str, encoding="utf-8-sig")
    code = code[(code["시도명"] == "서울특별시") & code["읍면동명"].notna() & code["리명"].isna()]
    code = code.assign(SGG_CD_NM="서울특별시 " + code["시군구명"]).rename(columns={"읍면동명": "STDG_CD_NM", "법정동코드": "bjd_cd"})
    n0 = len(df)
    d = df.merge(code[["SGG_CD_NM", "STDG_CD_NM", "bjd_cd"]], on=["SGG_CD_NM", "STDG_CD_NM"], how="left", validate="many_to_one")
    assert len(d) == n0
    ok = d["PLOT_SE_CD_NM"].isin(["대지", "산"]) & d["bjd_cd"].notna() & d["MN_LOTNO"].astype(str).str.fullmatch(r"\d+")
    print(f"PNU로 바꿀 수 있는 행 {int(ok.sum()):,} / {n0:,} (블록·법정동 불일치 {int((~ok).sum()):,} 제외)")
    d = d[ok]
    sub = d["SUB_LOTNO"].fillna("").astype(str).replace("", "0")
    out = pd.DataFrame({
        "pnu": d["bjd_cd"] + d["PLOT_SE_CD_NM"].map({"대지": "1", "산": "2"}) + d["MN_LOTNO"].astype(str).str.zfill(4) + sub.str.zfill(4),
        "ersr_date": d["CLSG_ERSR_YMD"], "ersr_kind": d["CLSG_ERSR_SE_CD_NM"], "main_annex": d["MANX_SE_CD_NM"],
        "main_usage": d["MN_USG_CD_NM"], "etc_usage": d["ETC_USG_CN"], "use_apr_date": d["USE_APRV_YMD"],
        "hhld_cnt": d["HH_CNT"], "dong_nm": d["DNG_NM"],
    }).sort_values(["pnu", "ersr_date"])
    out.to_csv(REF, index=False, encoding="utf-8-sig")
    print(f"→ {REF.relative_to(ROOT)}: {len(out):,}행, 지번 {out['pnu'].nunique():,}개")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-only", action="store_true")
    if ap.parse_args().build_only:
        return build_reference(pd.read_csv(OUT, dtype=str, encoding="utf-8-sig"))
    load_dotenv(ROOT / ".env")
    key = os.getenv("SEOUL_OPEN_API_KEY")
    if not key:
        sys.exit("SEOUL_OPEN_API_KEY가 없습니다(.env)")
    RAW.mkdir(parents=True, exist_ok=True)
    total = fetch(key, 1)["list_total_count"]
    print(f"서울 전체 {total:,}건, {PAGE_SIZE}건씩 {-(-total // PAGE_SIZE)}페이지")
    t0 = time.time()
    for start in range(1, total + 1, PAGE_SIZE):
        f = RAW / f"{start:07d}.json"
        if f.exists():
            continue
        rows = [x for x in fetch(key, start)["row"] if x["SGG_CD_NM"] in SGG_NAMES]
        f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        if (start // PAGE_SIZE) % 50 == 0:
            print(f"  {start:,} … {time.time() - t0:.0f}초")
    rows = [x for f in sorted(RAW.glob("*.json")) for x in json.loads(f.read_text(encoding="utf-8"))]
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"3개 구 {len(df):,}건 → {OUT.relative_to(ROOT)}: {df['SGG_CD_NM'].value_counts().to_dict()}")
    build_reference(df.astype(str).replace("nan", ""))


if __name__ == "__main__":
    main()
