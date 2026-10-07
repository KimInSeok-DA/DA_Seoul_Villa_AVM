"""공시가격 원본(JSON)을 정제해 data/processed/apt_price.csv로 만든다.

사용: python src/build_apt_price.py [--fetch-fallback]

- VWorld 응답은 같은 행을 2번씩 준다 → 완전 중복 행 제거 후 (pnu, 동, 호) 유일성 확인
- 금액·면적·층을 숫자로 바꾸고, 입력 `ho`와 맞출 수 있게 호 표기를 통일한 `ho_key`를 만든다
  예: '301', '3층301호', '3층-301' → '301' / 'B01', '비01', '지층B01', '지하B01' → 'B1'
- 2026년 공시가 없는 지번은 --fetch-fallback으로 2025→2020 순서로 가장 최근 연도를 받아 보충한다
  (data/raw/apt_price_fallback/). 보충 행은 stdr_year로 구분한다
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "apt_price"
FALLBACK = ROOT / "data" / "raw" / "apt_price_fallback"
OUT = ROOT / "data" / "processed" / "apt_price.csv"
PRICE_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"
REPO_URL = "https://github.com/KimInSeok-DA/DA_Seoul_Villa_AVM"
FALLBACK_YEARS = ["2025", "2024", "2023", "2022", "2021", "2020"]


def fields(path):
    j = json.loads(path.read_text(encoding="utf-8"))
    return j.get("apartHousingPrices", {}).get("field", [])  # 결과 없음은 {"response": {"totalCount": "0"}}


SPELLED = [("에이", "A"), ("비이", "B"), ("비", "B"), ("씨", "C"), ("디", "D")]
FLOOR_PREFIX = re.compile(r"^(지상|지하|지층|지)?\d+층-?")
BASEMENT_PREFIX = re.compile(r"^(지하층|지층|지하|지)")
DONG_PREFIX = re.compile(r"(\d{1,4}동-?|\d{3,4}-|[A-Z가-힣]{1,2}-?)(\d{3,4})")


def ho_key(ho, floor):
    """호 표기 통일(입력 `ho`와 맞추기 위한 키)과 호 앞 동 표시를 돌려준다: (ho_key, ho_prefix)

    '301'·'3층301호'·'301(3층)'·'3층(101)'·'제301' → '301', 'B01'·'비01'·'지층B01'·'지하층비01'·'지01' → 'B1',
    '3층1' → '301', '1층가'·'지상1층에이세대' → '1가'·'1A', '2-1' → '2-1',
    '101동201'·'101-201'·'나201'·'A 101' → '201'·'201'·'201'·'101' (앞 표시는 ho_prefix)
    """
    raw = str(ho).strip().replace(" ", "")
    outside = re.sub(r"\(.*?\)", "", raw)
    inside = "".join(re.findall(r"\((.*?)\)", raw))
    out_rest = FLOOR_PREFIX.sub("", outside)
    # '301(3층)'은 바깥이 호, '3층(101)'·'일층(101)'은 괄호 안이 호
    if re.search(r"\d", inside) and not re.search(r"\d", out_rest):
        s = inside
    else:
        # 괄호 안이 숫자 없는 표시('(지층)' 등)면 바깥에 숫자가 있을 때 버린다
        s = outside if re.search(r"\d", outside) else outside + inside
    basement = floor < 0 or bool(re.match(r"^(지층|지하|지\d)", s))
    had_floor = bool(FLOOR_PREFIX.match(s))
    s = FLOOR_PREFIX.sub("", s)
    s = re.sub(r"(호|세대|형)$", "", s).replace("호", "")
    s = re.sub(r"^제", "", s)
    while basement and BASEMENT_PREFIX.match(s):
        s = BASEMENT_PREFIX.sub("", s, count=1)
    for k, v in SPELLED:
        s = s.replace(k, v)
    s = s.upper().strip("-")
    if re.fullmatch(r"B?\d+", s):
        n = int(s.lstrip("B"))
        if basement or s.startswith("B"):
            return f"B{n}", ""
        return (f"{floor}{n:02d}" if had_floor and n < 100 else str(n)), ""
    m = DONG_PREFIX.fullmatch(s)
    if m and not (basement and m.group(1) == "B"):
        n = int(m.group(2))
        return (f"B{n}" if basement else str(n)), m.group(1).rstrip("-")
    if re.fullmatch(r"\d+-\d+", s):
        a, b = s.split("-")
        return f"{int(a)}-{int(b)}", ""
    s = re.sub(r"동$", "", s)
    if not s:
        return (f"B{abs(floor)}" if basement else str(floor)), ""
    if re.fullmatch(r"[A-Z가-힣]", s):  # 층 + 문자 하나
        return f"{'B' if basement else ''}{abs(floor) if basement else floor}{s}", ""
    return ("B" if basement and not s.startswith("B") else "") + s, ""


def fetch_fallback(empty_pnus):
    load_dotenv(ROOT / ".env")
    key = os.getenv("VWORLD_API_KEY")
    FALLBACK.mkdir(parents=True, exist_ok=True)
    for pnu in empty_pnus:
        path = FALLBACK / f"{pnu}.json"
        if path.exists():
            continue
        found = {"apartHousingPrices": {"field": []}}
        for year in FALLBACK_YEARS:
            r = requests.get(PRICE_URL, timeout=30, params={
                "key": key, "domain": REPO_URL, "pnu": pnu, "stdrYear": year,
                "format": "json", "numOfRows": 1000, "pageNo": 1})
            fl = r.json().get("apartHousingPrices", {}).get("field", [])
            time.sleep(0.05)
            if fl:
                found = {"apartHousingPrices": {"field": fl}}
                break
        path.write_text(json.dumps(found, ensure_ascii=False), encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-fallback", action="store_true")
    args = ap.parse_args()

    files = sorted(RAW.glob("*.json"))
    rows, empty = [], []
    for f in files:
        fl = fields(f)
        rows += fl
        if not fl:
            empty.append(f.stem)
    print(f"원본 지번 {len(files):,}개, 2026 공시 없음 {len(empty):,}개, 행 {len(rows):,}")

    if args.fetch_fallback:
        fetch_fallback(empty)
    for f in sorted(FALLBACK.glob("*.json")) if FALLBACK.exists() else []:
        rows += fields(f)

    raw = pd.DataFrame(rows)
    df = raw.drop_duplicates().copy()
    print(f"완전 중복 제거: {len(raw):,} → {len(df):,}행")
    # 과거 연도 응답에는 같은 호가 갱신일(lastUpdtDt)만 다르게 두 번 오는 경우가 있다 → 최신 갱신 1행만 남김
    key = ["pnu", "dongNm", "hoNm", "stdrYear"]
    value_cols = [c for c in df.columns if c not in key + ["lastUpdtDt"]]
    conflict = (df.groupby(key)[value_cols].nunique() > 1).any(axis=1).sum()
    assert conflict == 0, f"같은 호인데 값이 다른 그룹 {conflict}개"
    before = len(df)
    df = df.sort_values("lastUpdtDt").drop_duplicates(key, keep="last").copy()
    print(f"갱신일만 다른 중복 제거: {before:,} → {len(df):,}행")

    df["floor"] = df["floorNm"].astype(int)
    keys = [ho_key(h, fl) for h, fl in zip(df["hoNm"], df["floor"])]
    df["ho_key"] = [k for k, _ in keys]
    df["ho_prefix"] = [p for _, p in keys]
    out = pd.DataFrame({
        "pnu": df["pnu"], "dong_nm": df["dongNm"].str.strip(), "ho_nm": df["hoNm"], "ho_key": df["ho_key"], "ho_prefix": df["ho_prefix"],
        "floor": df["floor"], "area_m2": df["prvuseAr"].astype(float),
        "price_public": df["pblntfPc"].astype("int64"), "stdr_year": df["stdrYear"].astype(int),
        "house_type": df["aphusSeCodeNm"], "complex_nm": df["aphusNm"],
    }).sort_values(["pnu", "dong_nm", "floor", "ho_key"])

    collide = out.duplicated(["pnu", "dong_nm", "ho_prefix", "floor", "ho_key", "stdr_year"], keep=False)
    print(f"ho_key 충돌(같은 지번·동·층·호 앞 표시에서 같은 호): {int(collide.sum())}행, "
          f"{out.loc[collide, 'pnu'].nunique()}개 지번")
    years = out.groupby("pnu")["stdr_year"].max().value_counts().sort_index(ascending=False)
    print("지번별 공시 기준연도:", years.to_dict())
    print(f"보충 후에도 공시 없음: {len(set(empty) - set(out['pnu'])):,}개 지번")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"저장: {OUT.relative_to(ROOT)} ({len(out):,}행, {OUT.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
