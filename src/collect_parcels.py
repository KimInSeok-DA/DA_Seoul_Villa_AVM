"""권역 3개 구(30개 법정동)의 모든 필지 중심점 좌표와 개별공시지가를 수집한다
→ data/reference/parcels.csv

사용: python src/collect_parcels.py

- 출처: 국토교통부 연속지적도(VWorld 데이터 API `LP_PA_CBND_BUBUN`, data.go.kr 15056910,
  이용허락범위 "제한 없음"). 지오코더(결과 저장 금지)와 달리 저장 가능한 공공데이터다(의사결정 1007_06)
- 법정동코드로 시작하는 PNU를 1,000필지씩 페이지 단위로 받는다
- 필지 경계 도형은 저장하지 않고 중심점(경계 꼭짓점의 넓이 가중 중심)과 속성만 남긴다
- 페이지별 결과를 data/raw/parcels/에 저장해, 중간에 멈춰도 다시 실행하면 이어 받는다
"""
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "parcels"
OUT = ROOT / "data" / "reference" / "parcels.csv"
CODE_CSV = ROOT / "data" / "reference" / "법정동코드_국토교통부_20260630.csv"
URL = "https://api.vworld.kr/req/data"
REPO_URL = "https://github.com/KimInSeok-DA/DA_Seoul_Villa_AVM"
SGG = ["11500", "11620", "11680"]
PAGE_SIZE = 1000


def ring_centroid(ring):
    """다각형 외곽선의 넓이 가중 중심. 넓이가 0이면 꼭짓점 평균.

    경위도(126, 37)를 그대로 곱하면 자릿수 손실로 중심이 필지 밖으로 나간다
    → 첫 꼭짓점을 원점으로 옮겨 계산하고, 결과가 외곽선 범위 밖이면 꼭짓점 평균을 쓴다
    """
    ox, oy = ring[0]
    pts = [(x - ox, y - oy) for x, y in ring]
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    xs, ys = zip(*ring)
    mean = (sum(xs) / len(xs), sum(ys) / len(ys))
    if abs(a) < 1e-20:
        return mean[0], mean[1], 0.0
    x, y = cx / (3 * a) + ox, cy / (3 * a) + oy
    if not (min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys)):
        return mean[0], mean[1], abs(a) / 2
    return x, y, abs(a) / 2


def centroid(geom):
    """MultiPolygon은 외곽선 넓이가 가장 큰 조각의 중심"""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    best = max((ring_centroid(p[0]) for p in polys), key=lambda c: c[2])
    return best[0], best[1]


def fetch_page(key, bjd, page):
    params = {"service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN", "key": key,
              "domain": REPO_URL, "format": "json", "crs": "EPSG:4326", "geometry": "true",
              "attrFilter": f"pnu:like:{bjd}%", "size": PAGE_SIZE, "page": page}
    for wait in (2, 5, 15, None):
        try:
            j = requests.get(URL, params=params, timeout=60).json()["response"]
            if j.get("status") in ("OK", "NOT_FOUND"):
                return j
            err = j.get("error")
        except (requests.RequestException, ValueError, KeyError) as e:
            err = repr(e)
        if wait is None:
            raise RuntimeError(f"{bjd} p{page}: {err}")
        time.sleep(wait)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    key = os.getenv("VWORLD_API_KEY")
    code = pd.read_csv(CODE_CSV, dtype=str, encoding="utf-8-sig")
    dongs = code[code["법정동코드"].str[:5].isin(SGG) & code["읍면동명"].notna() & code["리명"].isna()]
    RAW.mkdir(parents=True, exist_ok=True)
    for bjd, name in zip(dongs["법정동코드"], dongs["읍면동명"]):
        page, total_pages = 1, None
        while total_pages is None or page <= total_pages:
            path = RAW / f"{bjd}_{page:03d}.csv"
            if path.exists() and total_pages is not None:
                page += 1
                continue
            j = fetch_page(key, bjd, page)
            if j.get("status") == "NOT_FOUND":
                break
            total_pages = int(j["page"]["total"])
            if not path.exists():
                rows = []
                for f in j["result"]["featureCollection"]["features"]:
                    p = f["properties"]
                    x, y = centroid(f["geometry"])
                    rows.append({"pnu": p["pnu"], "jibun": p["jibun"], "lon": round(x, 7), "lat": round(y, 7),
                                 "land_price_m2": p.get("jiga"), "land_price_year": p.get("gosi_year")})
                pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
            page += 1
        print(f"{name}({bjd}): {total_pages or 0}쪽")

    df = pd.concat([pd.read_csv(f, dtype=str) for f in sorted(RAW.glob("*.csv"))], ignore_index=True)
    df = df.drop_duplicates("pnu")
    df["land_category"] = df["jibun"].str.extract(r"([가-힣]+)$")[0]  # 지목: 대·도·전 등
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"저장: {OUT.relative_to(ROOT)} ({len(df):,}필지, {OUT.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
