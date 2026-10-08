"""하우스머치 참고 비교(1008_04) — 검증 건물 9건, 입력·학습에 쓰지 않음

사용: python src/compare_housemuch.py
입력: _private/housemuch_values.csv(하우스머치 조회값, 저장소 제외), outputs/calibration_holdout_preds.csv(최종 검증 예측,
      상황 B·면적 있음 — 그 거래를 빼고 낸 추정), data/processed/trades.csv
출력: _private/housemuch_reference.csv(건별, 저장소 제외), 화면에 요약

- 하우스머치 약관(제4조 ③ 추정시세정보 저작권은 회사, 제9조 ④ 정보 복제 금지) 때문에 건별 조회값과 건별 비교표는
  공개 저장소에 두지 않는다. 공개 문서에는 요약 통계만 쓴다(1008_04)
- 조회값 파일 열: dong, jibun, floor, hm_ho, hm_area, hm_mid, hm_low, hm_high(만원) — 사용자가 사이트에서 같은 지번·층·면적의
  호를 직접 조회해 옮겨 적은 것(조회 2026-10-08, 추정 기준일 2026-09-01). 자동 수집하지 않았다
- 9건은 권역마다 3건, 우리 신뢰도 높음·중간·낮음을 1건씩 무작위로 골랐다(2026년 거래, 시드 7)
- 9건뿐이라 성능 비교가 아니라 참고다. 하우스머치는 그 실거래를 알고 낸 값일 수 있다(우리 추정은 그 거래를 뺐다)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avm import PROC, ROOT, SGG_NAME  # noqa: E402

HM_FILE = ROOT / "_private" / "housemuch_values.csv"
OUT = ROOT / "_private" / "housemuch_reference.csv"


def jibun(pnu):
    main, sub = int(pnu[11:15]), int(pnu[15:19])
    return f"{main}-{sub}" if sub else str(main)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not HM_FILE.exists():
        sys.exit(f"{HM_FILE.relative_to(ROOT)}이 없습니다(하우스머치 조회값, 저장소 제외)")
    hm = pd.read_csv(HM_FILE, dtype={"jibun": str, "hm_ho": str}, encoding="utf-8-sig")
    p = pd.read_csv(ROOT / "outputs" / "calibration_holdout_preds.csv", dtype={"pnu": str, "sgg_cd": str})
    p = p[(p["구분"] == "보정") & (p["scenario"] == "B") & (~p["area_blank"])].assign(jibun=lambda d: d["pnu"].map(jibun))
    p["deal_date"] = p["deal_date"].astype(str).str[:10]
    m = hm.merge(p, on=["dong", "jibun", "floor"], how="left", validate="one_to_one")
    assert m["price_est"].notna().all(), "검증 예측과 연결 안 된 건 있음"
    t = pd.read_csv(PROC / "trades.csv", dtype={"pnu": str}, low_memory=False)
    t["deal_date"] = t["deal_date"].astype(str).str[:10]
    m = m.rename(columns={"price": "price_adj"}).merge(  # price_adj: 검증 예측 파일의 실거래가(기준일 환산), 비교는 신고 금액으로
        t[["pnu", "deal_date", "floor", "area_m2", "price", "dealing_type"]], left_on=["pnu", "deal_date", "floor", "true_area"],
        right_on=["pnu", "deal_date", "floor", "area_m2"], how="left")
    assert len(m) == len(hm) and m["price"].notna().all(), "실거래와 한 건씩 연결되지 않음"

    out = pd.DataFrame({
        "권역": m["sgg_cd"].map(SGG_NAME), "주소": m["dong"] + " " + m["jibun"], "층": m["floor"], "전용면적": m["true_area"],
        "거래일": m["deal_date"], "거래유형": m["dealing_type"], "실거래가": m["price"],
        "우리_추정": m["price_est"].round(-5), "우리_하한": m["price_low"].round(-5), "우리_상한": m["price_high"].round(-5),
        "우리_신뢰도": m["confidence"].round(2),
        "HM_중위": m["hm_mid"] * 1e4, "HM_하한": m["hm_low"] * 1e4, "HM_상한": m["hm_high"] * 1e4,
        "HM_호": m["hm_ho"], "HM_전용면적": m["hm_area"],
    })
    out["우리_오차"] = (out["우리_추정"] / out["실거래가"] - 1).round(3)
    out["HM_오차"] = (out["HM_중위"] / out["실거래가"] - 1).round(3)
    out["우리_범위안"] = out["실거래가"].between(out["우리_하한"], out["우리_상한"])
    out["HM_범위안"] = out["실거래가"].between(out["HM_하한"], out["HM_상한"])
    out["우리÷HM"] = (out["우리_추정"] / out["HM_중위"] - 1).round(3)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")

    pd.set_option("display.width", 250)
    print(out[["주소", "거래유형", "실거래가", "우리_추정", "우리_오차", "우리_신뢰도", "우리_범위안", "HM_중위", "HM_오차", "HM_범위안", "우리÷HM"]].to_string(index=False))
    for name, s in [("9건", out), ("중개거래 7건", out[out["거래유형"] == "중개거래"])]:
        print(f"{name}: 중앙값 |오차| 우리 {s['우리_오차'].abs().median():.1%} / HM {s['HM_오차'].abs().median():.1%}, "
              f"±20% 안 우리 {(s['우리_오차'].abs() <= .2).sum()} / HM {(s['HM_오차'].abs() <= .2).sum()}, "
              f"범위 안 우리 {s['우리_범위안'].sum()} / HM {s['HM_범위안'].sum()}, 우리와 HM 차이 중앙값 {s['우리÷HM'].abs().median():.1%}")


if __name__ == "__main__":
    main()
