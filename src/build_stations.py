"""공공데이터 도시철도 역사정보에서 권역 주변 지하철역 좌표를 뽑는다 → data/reference/subway_stations.csv

사용: python src/build_stations.py
입력: data/raw/bulk/전체_도시철도역사정보_20260630.xlsx
      (전국도시철도역사정보표준데이터, data.go.kr 표준데이터 — 사용자가 내려받음)

역 좌표는 저장해 두고 계속 써야 하므로, 결과 저장을 금지하는 지도 API(Kakao 로컬, VWorld 지오코더)가
아니라 저장·재배포가 가능한 공공데이터를 쓴다(의사결정 1006_04 5절).
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "bulk" / "전체_도시철도역사정보_20260630.xlsx"
OUT = ROOT / "data" / "reference" / "subway_stations.csv"
# 강서·관악·강남을 감싸는 범위(경계 밖 역도 거리 계산에 필요하므로 여유를 둔다)
BBOX = (126.76, 37.43, 127.14, 37.60)  # (min_lon, min_lat, max_lon, max_lat)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    d = pd.read_excel(SRC, sheet_name=0, dtype={"역번호": str, "노선번호": str})
    d["lat"] = pd.to_numeric(d["역위도"], errors="coerce")
    d["lon"] = pd.to_numeric(d["역경도"], errors="coerce")
    print(f"원본 {len(d):,}행, 좌표 없음 {int(d[['lat', 'lon']].isna().any(axis=1).sum())}행")
    x0, y0, x1, y1 = BBOX
    inside = d[d["lon"].between(x0, x1) & d["lat"].between(y0, y1)]
    out = pd.DataFrame({
        "station_id": inside["역번호"], "station_nm": inside["역사명"],
        # 노선마다 표기가 다름: '한티역'(분당선) / '선릉'(2호선), '양재(서초구청)' → '한티', '선릉', '양재'
        "station_key": inside["역사명"].astype(str).str.replace(r"\(.*?\)", "", regex=True).str.strip().str.replace(r"역$", "", regex=True),
        "line_nm": inside["노선명"],
        "operator": inside["운영기관명"], "lat": inside["lat"], "lon": inside["lon"],
        "ref_date": pd.to_datetime(inside["데이터기준일자"], errors="coerce").dt.date,  # 일부 행이 1900-01-00
    }).drop_duplicates(["station_key", "line_nm"]).sort_values(["line_nm", "station_key"])
    print(f"권역 주변 {len(out):,}개(역·노선 단위), 역 {out['station_key'].nunique()}개, 노선 {out['line_nm'].nunique()}개")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
