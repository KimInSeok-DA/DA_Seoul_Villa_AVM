"""권역 주변 지하철역 좌표를 Kakao Local 카테고리 검색(SW8)으로 수집한다.

서울교통공사 파일은 1~8호선·9호선 2·3단계만 있어 9호선 1단계·신림선·수인분당선·
신분당선·공항철도가 빠지므로, 전 노선이 나오는 Kakao 카테고리 검색을 쓴다.
한 번 검색에 최대 45건(15건×3쪽)이므로 영역을 격자로 나눠 훑고, 결과가 꽉 차면 더 잘게 나눈다.

출력: data/reference/subway_stations.csv (역·노선 단위, place_id 기준 중복 제거)
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
URL = "https://dapi.kakao.com/v2/local/search/category.json"
# 강서·관악·강남을 감싸는 범위(경계 밖 역도 거리 계산에 필요하므로 여유를 둔다)
BBOX = (126.76, 37.43, 127.14, 37.60)  # (min_x, min_y, max_x, max_y)


def search_rect(rect, headers):
    docs, page = [], 1
    while True:
        r = requests.get(URL, headers=headers, timeout=15, params={
            "category_group_code": "SW8", "rect": ",".join(f"{v:.6f}" for v in rect),
            "page": page, "size": 15})
        r.raise_for_status()
        j = r.json()
        docs += j["documents"]
        time.sleep(0.1)
        if j["meta"]["is_end"]:
            return docs, j["meta"]["total_count"]
        page += 1


def crawl(rect, headers, out):
    docs, total = search_rect(rect, headers)
    if total > len(docs):  # 45건 한도에 걸림 → 4등분
        x0, y0, x1, y1 = rect
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        for sub in [(x0, y0, xm, ym), (xm, y0, x1, ym), (x0, ym, xm, y1), (xm, ym, x1, y1)]:
            crawl(sub, headers, out)
    else:
        out += docs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    headers = {"Authorization": f"KakaoAK {os.getenv('KAKAO_REST_API_KEY')}"}
    out = []
    crawl(BBOX, headers, out)
    df = pd.DataFrame(out).drop_duplicates("id")
    df = df.rename(columns={"id": "place_id", "x": "lon", "y": "lat"})
    df = df[["place_id", "place_name", "category_name", "address_name", "lon", "lat"]]
    path = ROOT / "data" / "reference" / "subway_stations.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"{len(df)}개 역(노선 단위) -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
