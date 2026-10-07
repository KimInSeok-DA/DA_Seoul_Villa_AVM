"""보조 API 응답을 지번 하나로 확인한다: Kakao 주소검색, VWorld 지오코더,
건축HUB(표제부·전유공용면적), VWorld 공동주택가격, 전월세 실거래.

사용: python src/probe_apis.py ["서울특별시 관악구 봉천동 1597-30"]
원본 응답은 data/raw/probe/에 저장한다. 키는 출력하지 않는다.
단 Kakao 로컬·VWorld 지오코더 응답은 약관상 저장할 수 없어 화면에만 출력한다(의사결정 1006_04 5절).
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "probe"
REPO_URL = "https://github.com/KimInSeok-DA/DA_Seoul_Villa_AVM"


def save(name, content):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(content)


def show(title, resp, limit=1500):
    print(f"\n===== {title} : HTTP {resp.status_code}")
    print(resp.text[:limit])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(ROOT / ".env")
    data_key = os.getenv("DATA_GO_KR_API_KEY")
    vworld_key = os.getenv("VWORLD_API_KEY")
    kakao_key = os.getenv("KAKAO_REST_API_KEY")
    address = sys.argv[1] if len(sys.argv) > 1 else "서울특별시 관악구 봉천동 1597-30"

    # 1) Kakao 주소검색 → 법정동코드(b_code)·본번·부번·좌표
    r = requests.get("https://dapi.kakao.com/v2/local/search/address.json",
                     params={"query": address},
                     headers={"Authorization": f"KakaoAK {kakao_key}"}, timeout=15)
    show("Kakao 주소검색", r)
    pnu = None
    try:
        a = r.json()["documents"][0]["address"]
        mountain = "2" if a.get("mountain_yn") == "Y" else "1"
        pnu = a["b_code"] + mountain + a["main_address_no"].zfill(4) + (a["sub_address_no"] or "0").zfill(4)
        print("-> PNU:", pnu)
    except (KeyError, IndexError, ValueError) as e:
        print("-> PNU 생성 실패:", repr(e))

    # 2) VWorld 지오코더 (지번)
    r = requests.get("https://api.vworld.kr/req/address",
                     params={"service": "address", "request": "getcoord", "version": "2.0",
                             "crs": "epsg:4326", "address": address, "refine": "true",
                             "simple": "false", "format": "json", "type": "parcel",
                             "key": vworld_key, "domain": REPO_URL}, timeout=15)
    show("VWorld 지오코더", r)

    if not pnu:
        return
    sigungu_cd, bjdong_cd = pnu[:5], pnu[5:10]
    plat_gb = "0" if pnu[10] == "1" else "1"
    bun, ji = pnu[11:15], pnu[15:19]

    # 3) 건축HUB 표제부·전유공용면적
    for op in ["getBrTitleInfo", "getBrExposPubuseAreaInfo"]:
        r = requests.get(f"https://apis.data.go.kr/1613000/BldRgstHubService/{op}",
                         params={"serviceKey": data_key, "sigunguCd": sigungu_cd,
                                 "bjdongCd": bjdong_cd, "platGbCd": plat_gb, "bun": bun,
                                 "ji": ji, "numOfRows": 100, "pageNo": 1, "_type": "json"},
                         timeout=30)
        save(f"bld_{op}.json", r.content)
        show(f"건축HUB {op}", r, 2500)

    # 4) VWorld 공동주택가격 속성조회
    r = requests.get("https://api.vworld.kr/ned/data/getApartHousingPriceAttr",
                     params={"key": vworld_key, "domain": REPO_URL, "pnu": pnu,
                             "format": "json", "numOfRows": 100, "pageNo": 1},
                     timeout=30)
    save("vworld_apart_price.json", r.content)
    show("VWorld 공동주택가격", r, 2500)

    # 5) 전월세 실거래 (관악구 2026-08)
    r = requests.get("https://apis.data.go.kr/1613000/RTMSDataSvcRHRent/getRTMSDataSvcRHRent",
                     params={"serviceKey": data_key, "LAWD_CD": sigungu_cd, "DEAL_YMD": "202608",
                             "pageNo": 1, "numOfRows": 1000}, timeout=30)
    save(f"rent_{sigungu_cd}_202608.xml", r.content)
    print(f"\n===== 전월세 실거래 : HTTP {r.status_code}")
    try:
        root = ET.fromstring(r.content)
        print("resultCode:", root.findtext(".//resultCode"), root.findtext(".//resultMsg"),
              "totalCount:", root.findtext(".//totalCount"))
        items = root.findall(".//item")
        if items:
            for child in items[0]:
                print(f"  {child.tag:24} {(child.text or '').strip()}")
    except ET.ParseError:
        print(r.text[:800])


if __name__ == "__main__":
    main()
