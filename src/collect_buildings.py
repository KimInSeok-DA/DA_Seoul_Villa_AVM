"""매매 실거래 지번별로 건축물대장 표제부와 공동주택 공시가격을 수집한다.

사용: python src/collect_buildings.py [--what title,price] [--limit N]

- 대상: 매매 실거래 지번(해제 포함 전체). 최근 12개월 거래 지번을 먼저 받는다
- 지번 → PNU: 법정동코드표(data/reference)로 sggCd+umdNm → 10자리, '산' 지번은 산 구분 2
- 지번별 응답을 data/raw/bld_title/, data/raw/apt_price/에 JSON으로 저장하고, 이미 있으면 건너뛴다
  (한도에 걸려 멈춰도 다시 실행하면 이어서 받는다)
- 호별 전유면적(전유부)은 미리 받지 않는다. predict.py가 면적이 빈 입력에 대해서만 실행 중 조회한다
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
RAW = ROOT / "data" / "raw"
CODE_CSV = ROOT / "data" / "reference" / "법정동코드_국토교통부_20260630.csv"
TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
PRICE_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"
REPO_URL = "https://github.com/KimInSeok-DA/DA_Seoul_Villa_AVM"
PRICE_YEAR = "2026"


class QuotaExceeded(Exception):
    pass


def load_dong_codes():
    code = pd.read_csv(CODE_CSV, dtype=str, encoding="utf-8-sig")
    code = code[(code["시도명"] == "서울특별시") & code["읍면동명"].notna() & code["리명"].isna()]
    code["sggCd"] = code["법정동코드"].str[:5]
    return code.rename(columns={"읍면동명": "umdNm", "법정동코드": "bjd_cd"})[["sggCd", "umdNm", "bjd_cd"]]


def to_pnu(bjd_cd, jibun):
    mountain = jibun.startswith("산")
    main, _, sub = jibun.lstrip("산").partition("-")
    return f"{bjd_cd}{'2' if mountain else '1'}{int(main):04d}{int(sub or 0):04d}"


def target_parcels():
    t = pd.read_csv(RAW / "trade_all.csv", dtype=str)
    t = t[t["jibun"].fillna("") != ""]
    t["ym"] = t["dealYear"] + t["dealMonth"].str.zfill(2)
    last = t.groupby(["sggCd", "umdNm", "jibun"])["ym"].max().reset_index()
    p = last.merge(load_dong_codes(), on=["sggCd", "umdNm"], how="left", validate="many_to_one")
    assert p["bjd_cd"].notna().all(), "법정동코드 매핑 실패 지번 있음"
    p["pnu"] = [to_pnu(b, j) for b, j in zip(p["bjd_cd"], p["jibun"])]
    return p.sort_values("ym", ascending=False).reset_index(drop=True)  # 최근 거래 지번부터


def get_json(url, params, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            text = r.text
            if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in text or "EXCEEDS" in text.upper():
                raise QuotaExceeded(text[:200])
            return r.json()
        except (requests.RequestException, ValueError) as e:
            err = repr(e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(err)


def fetch_title(pnu, key):
    j = get_json(TITLE_URL, {"serviceKey": key, "sigunguCd": pnu[:5], "bjdongCd": pnu[5:10],
                             "platGbCd": "0" if pnu[10] == "1" else "1", "bun": pnu[11:15],
                             "ji": pnu[15:19], "numOfRows": 100, "pageNo": 1, "_type": "json"})
    code = j.get("response", {}).get("header", {}).get("resultCode")
    if code not in ("00", "000"):
        raise RuntimeError(f"건축HUB resultCode={code}: {json.dumps(j, ensure_ascii=False)[:200]}")
    return j


def fetch_price(pnu, key):
    j = get_json(PRICE_URL, {"key": key, "domain": REPO_URL, "pnu": pnu, "stdrYear": PRICE_YEAR,
                             "format": "json", "numOfRows": 1000, "pageNo": 1})
    body = j.get("apartHousingPrices", {})
    if "field" not in body and str(body.get("totalCount", "")) not in ("0", ""):
        raise RuntimeError(f"VWorld 응답 이상: {json.dumps(j, ensure_ascii=False)[:200]}")
    if body.get("resultCode") and body.get("resultCode") not in ("INFO-000", "INFO-200"):
        raise RuntimeError(f"VWorld resultCode={body.get('resultCode')} {body.get('resultMsg')}")
    return j


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--what", default="title,price")
    ap.add_argument("--limit", type=int, default=0, help="이번 실행에서 받을 최대 지번 수(0=전부)")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    keys = {"title": os.getenv("DATA_GO_KR_API_KEY"), "price": os.getenv("VWORLD_API_KEY")}
    fetchers = {"title": fetch_title, "price": fetch_price}
    folders = {"title": RAW / "bld_title", "price": RAW / "apt_price"}

    parcels = target_parcels()
    parcels[["sggCd", "umdNm", "jibun", "bjd_cd", "pnu", "ym"]].to_csv(
        ROOT / "data" / "reference" / "trade_parcels.csv", index=False, encoding="utf-8-sig")
    print(f"대상 지번 {len(parcels):,}개 (최근 12개월 거래 {int((parcels['ym'] >= '202510').sum()):,}개 먼저)")

    for what in args.what.split(","):
        folder = folders[what]
        folder.mkdir(parents=True, exist_ok=True)
        todo = [p for p in parcels["pnu"] if not (folder / f"{p}.json").exists()]
        if args.limit:
            todo = todo[:args.limit]
        print(f"[{what}] 남은 {len(todo):,}개")
        done = 0
        try:
            for pnu in todo:
                try:
                    j = fetchers[what](pnu, keys[what])
                except RuntimeError as e:
                    print(f"  실패 {pnu}: {e}")
                    continue
                (folder / f"{pnu}.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
                done += 1
                if done % 500 == 0:
                    print(f"  {what} {done:,}/{len(todo):,}")
                time.sleep(0.05)
        except QuotaExceeded as e:
            print(f"[{what}] 일일 한도 도달로 중단 ({done:,}개 받음). 내일 다시 실행하면 이어서 받습니다. {e}")
        print(f"[{what}] 이번 실행 {done:,}개 저장")


if __name__ == "__main__":
    main()
