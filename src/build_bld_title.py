"""건축물대장 표제부 원본(JSON)을 지번(PNU) 단위 건물 정보로 정제한다 → data/processed/bld_title.csv

사용: python src/build_bld_title.py

한 지번에 주건축물이 여러 동이면 지번 단위로 합친다(의사결정 1007_01, A안).
- 대상: 주건축물 중 공동주택(다세대·연립) 동. 그런 동이 없으면 주건축물 전체
- 승강기 있음=어느 동이든, 층수=최대, 세대수·주차·연면적=합계
- 사용승인일·구조·용도: 세대수가 가장 많은 동(대표 동)

현행 대장에 건물이 없는 지번(대부분 철거·재건축으로 폐쇄말소대장으로 옮겨진 경우)은 결측으로 남기되(의사결정 1007_02)
- 지상·지하 층수와 세대수는 공시가격(data/processed/apt_price.csv)의 층·호 수로 채운다
- 승강기·주차·사용승인일 등은 비워 두고 `title_source`로 출처를 표시한다
  (건축물대장 / 공시가격 대체 / 없음). 건축년도는 모델 단계에서 실거래 buildYear를 쓴다
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "bld_title"
OUT = ROOT / "data" / "processed" / "bld_title.csv"
PRICE = ROOT / "data" / "processed" / "apt_price.csv"
RESIDENTIAL = r"다세대|연립|공동주택|도시형"
NUM_COLS = ["rideUseElvtCnt", "emgenUseElvtCnt", "grndFlrCnt", "ugrndFlrCnt", "hhldCnt", "totArea",
            "platArea", "indrAutoUtcnt", "oudrAutoUtcnt", "indrMechUtcnt", "oudrMechUtcnt"]


def items(path):
    j = json.loads(path.read_text(encoding="utf-8"))
    it = j["response"]["body"].get("items") or {}
    it = it.get("item", []) if isinstance(it, dict) else []
    return it if isinstance(it, list) else [it]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    files = sorted(RAW.glob("*.json"))
    rows = []
    for f in files:
        for x in items(f):
            x["pnu"] = f.stem
            rows.append(x)
    b = pd.DataFrame(rows)
    main_b = b[b["mainAtchGbCdNm"] == "주건축물"].copy()
    for c in NUM_COLS:
        main_b[c] = pd.to_numeric(main_b[c], errors="coerce").fillna(0)
    main_b["residential"] = (main_b["mainPurpsCdNm"].eq("공동주택")
                             | main_b["etcPurps"].fillna("").str.contains(RESIDENTIAL))
    has_res = main_b.groupby("pnu")["residential"].transform("any")
    use = main_b[main_b["residential"] | ~has_res].copy()
    print(f"원본 지번 {len(files):,}개, 건물 없음 {len(files) - b['pnu'].nunique():,}개, "
          f"주건축물 {len(main_b):,}동 → 사용 {len(use):,}동 (비주거 동 제외 {len(main_b) - len(use):,}동)")

    use["parking"] = use[["indrAutoUtcnt", "oudrAutoUtcnt", "indrMechUtcnt", "oudrMechUtcnt"]].sum(axis=1)
    rep = use.sort_values(["pnu", "hhldCnt"], ascending=[True, False]).drop_duplicates("pnu").set_index("pnu")
    g = use.groupby("pnu")
    out = pd.DataFrame({
        "n_dong": g.size(),
        "residential_only": g["residential"].all(),
        "elevator": (g["rideUseElvtCnt"].sum() + g["emgenUseElvtCnt"].sum()) > 0,
        "grnd_flr": g["grndFlrCnt"].max().astype(int),
        "ugrnd_flr": g["ugrndFlrCnt"].max().astype(int),
        "hhld_cnt": g["hhldCnt"].sum().astype(int),
        "parking_cnt": g["parking"].sum().astype(int),
        "tot_area_m2": g["totArea"].sum().round(2),
        "plat_area_m2": rep["platArea"],
        "use_apr_date": rep["useAprDay"].str.strip(),
        "use_apr_year_min": g["useAprDay"].apply(lambda s: s.str[:4].replace("", pd.NA).dropna().astype(int).min()),
        "use_apr_year_max": g["useAprDay"].apply(lambda s: s.str[:4].replace("", pd.NA).dropna().astype(int).max()),
        "structure": rep["strctCdNm"],
        "main_purpose": rep["mainPurpsCdNm"],
        "etc_purpose": rep["etcPurps"],
        "bld_nm": rep["bldNm"].str.strip(),
    }).reset_index()

    out["title_source"] = "건축물대장"
    print(f"건축물대장 지번 {len(out):,}개: 여러 동 {int((out['n_dong'] > 1).sum()):,}개, "
          f"승강기 있음 {out['elevator'].mean():.1%}")

    # 현행 대장에 건물이 없는 지번 → 공시가격으로 층수·세대수만 채우고 나머지는 결측
    missing = sorted({f.stem for f in files} - set(out["pnu"]))
    price = pd.read_csv(PRICE, dtype={"pnu": str})
    price = price[price["pnu"].isin(missing)]
    latest = price[price["stdr_year"] == price.groupby("pnu")["stdr_year"].transform("max")]
    pg = latest.groupby("pnu")
    fill = pd.DataFrame({
        "pnu": missing,
    }).set_index("pnu")
    fill["grnd_flr"] = pg["floor"].max().clip(lower=0)
    fill["ugrnd_flr"] = (-pg["floor"].min()).clip(lower=0)
    fill["hhld_cnt"] = pg.size()
    fill["title_source"] = ["공시가격 대체" if p in pg.groups else "없음" for p in fill.index]
    fill = fill.reset_index()
    print(f"현행 대장에 건물 없음 {len(missing):,}개 → 공시가격 대체 {int((fill['title_source'] == '공시가격 대체').sum())}개, "
          f"없음 {int((fill['title_source'] == '없음').sum())}개")
    out = pd.concat([out, fill], ignore_index=True)
    for c in ["n_dong", "grnd_flr", "ugrnd_flr", "hhld_cnt", "parking_cnt", "use_apr_year_min", "use_apr_year_max"]:
        out[c] = out[c].astype("Int64")
    out["elevator"] = out["elevator"].astype("boolean")
    out["residential_only"] = out["residential_only"].astype("boolean")
    out = out.sort_values("pnu").reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"저장: {OUT.relative_to(ROOT)} ({len(out):,}행, {OUT.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
