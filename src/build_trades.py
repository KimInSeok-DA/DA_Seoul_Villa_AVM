"""매매 실거래를 정제하고 건물 정보·공시가격을 붙인다 → data/processed/trades.csv

사용: python src/build_trades.py
입력: data/raw/trade_all.csv(src/collect_trades.py), data/reference/법정동코드표,
      data/processed/apt_price.csv, data/processed/bld_title.csv
판단 근거는 docs/의사결정/1007_04_실거래_정제.md

단계
1. 형식 정리: 금액(만원, 쉼표) → 원, 날짜·면적·층 숫자, 지번 → PNU
2. 결측: 거래유형(2021-11 이전)·매도/매수 구분(2023-12 이전)은 신고 항목이 생기기 전이라 비어 있음 → '미상'
3. 해제 거래 제외
4. 공시가격 연결: 같은 지번·층·전용면적의 호 → 실거래가/공시가격 비율
5. 이상치: 비율(로그)의 수정 Z-점수를 같은 구·같은 연도 안에서 계산(중앙값·MAD)
   - z < -3.5 → 제외(사정 개입 의심: 특수관계 직거래·지분 거래 등)
   - z > +3.5 → 남기고 premium_flag 표시(재개발 기대 프리미엄 등 정상 거래일 수 있음)
   - 공시가격이 없는 거래는 같은 법정동·연도의 ㎡당 가격으로 같은 계산
   - 공시 연도가 2026이 아닌 거래(보충 연도)도 비율이 체계적으로 높아 ㎡당 가격 기준으로 판정
6. 같은 날 같은 지번·층·면적·금액 거래 묶음은 남기고 dup_group_size 표시
   - 일괄 매매 합계 가격 제외(1007_11): 여러 호를 한 번에 사고 판 거래는 호마다 합계 금액이 적혀 있다
7. 표제부(건물 정보) 연결
   - 재건축 전 거래 제외(1007_11): 지금 표제부 건물의 사용승인 전에 옛 건물로 거래된 것
   - 철거된 건물 거래 제외(1008_02): 현행 대장에 건물이 없는 지번에서 폐쇄말소대장의 말소일 이전 거래.
     말소일 뒤 거래(새 건물, 아직 대장에 없음)는 남기고, 옛 건물 공시가격으로 채운 건물 정보는 비운다
8. 파생 변수(연식·지하·최상층)와 층 정합성 불일치 표시
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_buildings import load_dong_codes, to_pnu  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "trade_all.csv"
PRICE = ROOT / "data" / "processed" / "apt_price.csv"
TITLE = ROOT / "data" / "processed" / "bld_title.csv"
CLOSED = ROOT / "data" / "reference" / "closed_titles.csv"  # 폐쇄말소대장 표제부(src/collect_closed_titles.py)
OUT = ROOT / "data" / "processed" / "trades.csv"
Z_CUT = 3.5  # Iglewicz & Hoaglin(1993) 수정 Z-점수 권고 기준
# 일괄 매매: 호마다 비율이 구·연도 시장 중앙값의 3배 이상인데 묶음 합계로는 0.5~1.5배. 2.5배로 하면 신축 분양(층만 다른 같은 면적 호를
# 같은 ㎡단가로 판 것 — 묶음 크기가 2·3호로 달라도 ㎡당 가격이 같아 합계가 아님)까지 잡혀 3배로 둠(1007_11)
BULK_HIGH, BULK_SUM = 3.0, (0.5, 1.5)
REBUILT_GAP = 5  # 재건축 전 거래: 거래의 건축년도가 사용승인 연도보다 5년 넘게 이름


def apr_date(v):
    """표제부 사용승인일(YYYYMMDD, 일부 YYYYMM) → 날짜"""
    s = v.astype("Int64").astype(str)
    s = s.where(s.str.len() != 6, s + "01")
    return pd.to_datetime(s, format="%Y%m%d", errors="coerce")


def modified_z(x, groups):
    """중앙값·MAD 기반 수정 Z-점수. 0.6745 = 1/1.4826 (정규분포에서 MAD를 표준편차로 환산)"""
    med = x.groupby(groups).transform("median")
    mad = (x - med).abs().groupby(groups).transform("median")
    return 0.6745 * (x - med) / mad.replace(0, np.nan)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    log = []

    def step(name, n, note=""):
        log.append((name, n, note))
        print(f"{name:<28} {n:>7,} {note}")

    t = pd.read_csv(RAW, dtype=str, keep_default_na=False)
    step("원본 매매", len(t))

    # 1. 형식 정리
    codes = load_dong_codes()
    n0 = len(t)
    t = t.merge(codes, on=["sggCd", "umdNm"], how="left", validate="many_to_one")
    assert len(t) == n0 and t["bjd_cd"].notna().all(), "법정동코드 매핑 실패"
    t["pnu"] = [to_pnu(b, j) for b, j in zip(t["bjd_cd"], t["jibun"])]
    t["price"] = t["dealAmount"].str.replace(",", "").astype("int64") * 10000
    t["area_m2"] = t["excluUseAr"].astype(float)
    t["floor"] = t["floor"].astype(int)
    t["build_year"] = t["buildYear"].astype(int)
    t["deal_date"] = pd.to_datetime(t["dealYear"] + "-" + t["dealMonth"].str.zfill(2) + "-" + t["dealDay"].str.zfill(2))
    t["deal_year"] = t["deal_date"].dt.year
    # 2. 결측: 신고 항목이 생기기 전 거래
    for src, dst in [("dealingGbn", "dealing_type"), ("slerGbn", "seller_type"), ("buyerGbn", "buyer_type")]:
        t[dst] = t[src].str.strip().replace("", "미상")
    # 3. 해제 거래 제외
    cancelled = t["cdealType"].str.strip() != ""
    t = t[~cancelled].copy()
    step("해제 거래 제외", int(cancelled.sum()), f"→ {len(t):,}건")

    # 4. 공시가격 연결(같은 지번·층·전용면적 호, 여러 호면 중앙값, 가장 최근 공시 연도)
    ap = pd.read_csv(PRICE, dtype={"pnu": str})
    unit = (ap.groupby(["pnu", "floor", "area_m2", "stdr_year"], as_index=False)["price_public"].median()
            .sort_values("stdr_year").drop_duplicates(["pnu", "floor", "area_m2"], keep="last")
            .rename(columns={"stdr_year": "public_year"}))
    n0 = len(t)
    t = t.merge(unit, on=["pnu", "floor", "area_m2"], how="left", validate="many_to_one")
    assert len(t) == n0
    t["public_ratio"] = t["price"] / t["price_public"]
    step("공시가격 연결됨", int(t["price_public"].notna().sum()), f"({t['price_public'].notna().mean():.1%})")

    # 5. 이상치
    # 공시 연도가 2026이 아닌 거래(보충 연도, 대부분 철거 건물)는 공시가격이 낮아 비율이 체계적으로 높다
    # (비율 중앙값 2.36 vs 1.64) → 비율 기준에서 빼고 ㎡당 가격 기준으로 판정
    ratio_ok = t["public_year"] == 2026
    z_ratio = modified_z(np.log(t["public_ratio"].where(ratio_ok)), [t["sggCd"], t["deal_year"]])
    z_unit = modified_z(np.log(t["price"] / t["area_m2"]), [t["bjd_cd"], t["deal_year"]])
    t["outlier_z"] = z_ratio.fillna(z_unit)
    t["outlier_basis"] = np.where(z_ratio.notna(), "공시가격 비율(2026)", np.where(z_unit.notna(), "㎡당 가격", "판정 불가"))
    low = t["outlier_z"] < -Z_CUT
    step("낮은 이상치 제외(z<-3.5)", int(low.sum()),
         f"직거래 {int((low & (t['dealing_type'] == '직거래')).sum())}, ㎡당 가격 기준 {int((low & (t['outlier_basis'] == '㎡당 가격')).sum())}")
    print("   판정 기준별 건수:", t["outlier_basis"].value_counts().to_dict())
    t = t[~low].copy()
    t["premium_flag"] = t["outlier_z"] > Z_CUT
    step("높은 이상치 표시만(z>3.5)", int(t["premium_flag"].sum()))

    # 6. 같은 날 같은 조건 묶음 표시
    key = ["pnu", "floor", "area_m2", "price", "deal_date"]
    t["dup_group_size"] = t.groupby(key)["price"].transform("size")
    step("같은 날 같은 조건 묶음(표시)", int((t["dup_group_size"] > 1).sum()))
    # 일괄 매매 합계 가격: 같은 법정동·날짜·금액에 서로 다른 호가 2건 이상이고, 호마다 비율은 같은 구·연도 중앙값의
    # 3배 이상인데 금액을 묶음 공시가격 합으로 나누면 중앙값 수준 → 금액은 여러 호의 합계(호 단가가 아님).
    # 기준은 2026 공시가격 거래의 비율 중앙값(시장 수준). 보충 연도 공시가격 거래도 같은 기준으로 본다
    med = t["public_ratio"].where(ratio_ok).groupby([t["sggCd"], t["deal_year"]]).transform("median")
    g = t.groupby(["bjd_cd", "deal_date", "price"])
    n = g["price"].transform("size")
    distinct = (g["pnu"].transform("nunique") + g["floor"].transform("nunique") + g["area_m2"].transform("nunique")) > 3
    rel = t["public_ratio"] / med
    all_high = (rel.isna() | (rel >= BULK_HIGH)).groupby([t["bjd_cd"], t["deal_date"], t["price"]]).transform("all")
    sum_rel = t["price"] / (g["price_public"].transform("mean") * n) / med  # 공시가격 없는 호는 묶음 평균으로 채운 합계
    bulk = (n >= 2) & distinct & (g["price_public"].transform("count") >= 2) & all_high & sum_rel.between(*BULK_SUM)
    step("일괄 매매 합계 가격 제외", int(bulk.sum()), f"묶음 {t[bulk].groupby(['bjd_cd', 'deal_date', 'price']).ngroups}개")
    t = t[~bulk].copy()

    # 7. 표제부 연결
    title = pd.read_csv(TITLE, dtype={"pnu": str}).drop(columns=["bld_nm"])
    n0 = len(t)
    t = t.merge(title, on="pnu", how="left", validate="many_to_one")
    assert len(t) == n0
    step("표제부 연결됨", int(t["title_source"].notna().sum()), str(t["title_source"].value_counts().to_dict()))
    t["elevator"] = t["elevator"].map({True: 1, False: 0, "True": 1, "False": 0}).astype("Int64")
    # 재건축 전 거래: 지번은 같지만 지금 표제부의 건물이 서기 전 옛 건물의 거래 → 건물 정보가 맞지 않아 제외
    apr = apr_date(t["use_apr_date"])
    rebuilt = (t["deal_date"] < apr) & (t["build_year"] < apr.dt.year - REBUILT_GAP)
    step("재건축 전 거래 제외", int(rebuilt.sum()), f"건물 {t.loc[rebuilt, 'pnu'].nunique()}개")
    t = t[~rebuilt].copy()
    # 철거된 건물 거래: 현행 대장에 없는 지번(1007_02)은 대부분 거래 뒤 철거되어 폐쇄말소대장으로 옮겨진 건물
    closed = pd.read_csv(CLOSED, dtype={"pnu": str}, encoding="utf-8-sig")
    last_ersr = pd.to_datetime(closed["ersr_date"], errors="coerce").groupby(closed["pnu"]).max()
    ersr = t["pnu"].map(last_ersr)
    no_title = t["title_source"] != "건축물대장"
    demolished = no_title & ersr.notna() & (t["deal_date"] <= ersr)
    newer = no_title & ersr.notna() & (t["deal_date"] > ersr)
    step("철거된 건물 거래 제외", int(demolished.sum()),
         f"건물 {t.loc[demolished, 'pnu'].nunique()}개(대장 없는 지번 {t.loc[no_title, 'pnu'].nunique()}개 중 말소 기록 "
         f"{t.loc[no_title & ersr.notna(), 'pnu'].nunique()}개), 말소 뒤 새 건물 거래 {int(newer.sum())}건은 남김")
    t.loc[newer, ["n_dong", "grnd_flr", "ugrnd_flr", "hhld_cnt"]] = np.nan  # 옛 건물 공시가격으로 채운 값
    t.loc[newer, "title_source"] = "없음"
    t = t[~demolished].copy()

    # 8. 파생 변수·정합성 표시
    t["age"] = t["deal_year"] - t["build_year"]  # 건축년도·거래연도 대신 연식 하나만(완전 공선)
    t["is_basement"] = (t["floor"] < 0).astype(int)
    t["is_top_floor"] = (t["floor"] == t["grnd_flr"]).astype(int)
    t["floor_mismatch"] = ((t["floor"] > t["grnd_flr"]) | ((t["floor"] < 0) & (t["ugrnd_flr"] == 0))).fillna(False)
    step("층 정합성 불일치(표시)", int(t["floor_mismatch"].sum()), "거래 층 > 지상층수 또는 지하 거래인데 지하층수 0")

    out = t[["pnu", "bjd_cd", "sggCd", "umdNm", "jibun", "mhouseNm", "houseType", "deal_date", "deal_year",
             "price", "area_m2", "floor", "build_year", "dealing_type", "seller_type", "buyer_type",
             "price_public", "public_year", "public_ratio", "outlier_z", "outlier_basis", "premium_flag",
             "dup_group_size", "age", "is_basement", "is_top_floor", "floor_mismatch", "n_dong", "elevator", "grnd_flr", "ugrnd_flr", "hhld_cnt", "parking_cnt",
             "use_apr_date", "structure", "title_source"]].rename(columns={
        "sggCd": "sgg_cd", "umdNm": "dong", "mhouseNm": "bld_nm", "houseType": "house_type"})
    out = out.sort_values(["deal_date", "pnu"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    step("최종", len(out), f"→ {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
