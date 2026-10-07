"""실행 중 조회(1007_12): 사전 수집 데이터에 없는 지번의 공시가격·건축물대장 표제부를 predict.py 실행 중에 API로 받는다

- 언제: 입력 지번이 수집 데이터에 없을 때만(공시가격 없음 → VWorld, 표제부 없음 → 건축HUB). 수집된 지번은 부르지 않는다
- 키: 환경변수 VWORLD_API_KEY·DATA_GO_KR_API_KEY(.env도 읽음). 키가 없거나 조회가 실패하면 지금처럼 추정을 계속하고
  basis에 이유를 적는다 — 평가 환경에 키가 없어도 predict.py는 그대로 돈다
- 정제 규칙은 수집 데이터와 같다: 공시가격은 build_apt_price.py(중복 제거·호 표기 통일·2026 없으면 2025→2020 최근 연도),
  표제부는 build_bld_title.py(주건축물 중 공동주택 동을 지번 단위로 합침, 대표 동 = 세대수 최대)와 ml.load_buildings
- 받은 값은 이번 실행의 메모리에서만 쓰고 파일로 저장하지 않는다
"""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ho import ho_key

ROOT = Path(__file__).resolve().parents[1]
PRICE_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"
TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
REPO_URL = "https://github.com/KimInSeok-DA/DA_Seoul_Villa_AVM"  # VWorld 키 발급 시 등록한 서비스 URL
PRICE_YEARS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020"]
RESIDENTIAL = r"다세대|연립|공동주택|도시형"
TIMEOUT = 15
RETRY_WAITS = (2, 4, 8)  # 건축HUB는 간헐적으로 503 SERVICETIMEOUT_ERROR → 짧게 기다렸다 다시(수집 때는 5·15·30초)
BUDGET_SEC = 600  # 실행 중 조회에 쓰는 시간 상한(20건 30분 제한 안에서 모델 학습 시간을 남김). 넘으면 조회하지 않음


class LiveLookup:
    def __init__(self):
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        self.keys = {"price": os.getenv("VWORLD_API_KEY"), "title": os.getenv("DATA_GO_KR_API_KEY")}
        self.cache = {}  # (종류, pnu) → 결과(같은 지번이 여러 행 들어와도 한 번만 부름)
        self.spent = 0.0

    # ------------------------------------------------------------ 입력 1건
    def fill(self, refs, pnu, ml=None):
        """pnu에 없는 정보만 조회해 refs(공시가격)·ml(건물 변수)에 넣는다 → basis에 붙일 메모 목록"""
        notes = []
        if pnu not in refs.ap_by_pnu:
            ap, note = self._get("price", pnu, self.price)
            if ap is not None and len(ap):
                refs.ap_by_pnu[pnu] = ap
            notes.append(note)
        if ml is not None and pnu not in ml.bld.index:
            row, note = self._get("title", pnu, self.title)
            if row is None and pnu in refs.ap_by_pnu:  # 현행 대장에 건물 없음 → 1007_02처럼 공시가격으로 층수·세대수만
                row = title_from_price(refs.ap_by_pnu[pnu])
            if row is not None and pd.isna(row["build_year"]):  # 연식은 ml.load_buildings처럼 그 지번 거래의 건축년도 중앙값
                by = refs.trades.loc[refs.trades["pnu"] == pnu, "build_year"]
                row["build_year"] = by.median() if len(by) else np.nan
            if row is not None:
                ml.bld.loc[pnu] = row
            notes.append(note)
        return notes

    def _get(self, kind, pnu, fn):
        name = {"price": "공시가격", "title": "건축물대장"}[kind]
        if (kind, pnu) not in self.cache:
            if not self.keys[kind]:
                self.cache[kind, pnu] = (None, f"{name} 실행 중 조회 못 함(키 없음)")
            elif self.spent > BUDGET_SEC:
                self.cache[kind, pnu] = (None, f"{name} 실행 중 조회 생략(조회 시간 상한 초과)")
            else:
                t0 = time.time()
                try:
                    val, desc = fn(pnu)
                    self.cache[kind, pnu] = (val, f"{name} 실행 중 조회({desc})")
                except Exception as e:  # 네트워크·응답 오류 → 조회 없이 추정 계속
                    self.cache[kind, pnu] = (None, f"{name} 실행 중 조회 실패({str(e)[:40] or type(e).__name__})")
                self.spent += time.time() - t0
        return self.cache[kind, pnu]

    # ------------------------------------------------------------ 공시가격(VWorld)
    def price(self, pnu):
        import requests
        for year in PRICE_YEARS:
            r = requests.get(PRICE_URL, timeout=TIMEOUT, params={
                "key": self.keys["price"], "domain": REPO_URL, "pnu": pnu, "stdrYear": year,
                "format": "json", "numOfRows": 1000, "pageNo": 1})
            body = r.json().get("apartHousingPrices", {})
            if body.get("resultCode") and body["resultCode"] not in ("INFO-000", "INFO-200"):
                raise RuntimeError(f"VWorld {body['resultCode']}")
            fl = body.get("field", [])
            if fl:
                return clean_price(fl), f"VWorld {year}년 {len(fl)}행"
        return None, "VWorld 공시가격 없음"

    # ------------------------------------------------------------ 표제부(건축HUB)
    def title(self, pnu):
        import requests
        params = {"serviceKey": self.keys["title"], "sigunguCd": pnu[:5], "bjdongCd": pnu[5:10],
                  "platGbCd": "0" if pnu[10] == "1" else "1", "bun": pnu[11:15], "ji": pnu[15:19],
                  "numOfRows": 100, "pageNo": 1, "_type": "json"}
        for wait in (*RETRY_WAITS, None):
            r = requests.get(TITLE_URL, timeout=TIMEOUT, params=params)
            if "SERVICETIMEOUT" not in r.text:
                break
            if wait is None:
                raise RuntimeError("건축HUB 서버 응답 없음(SERVICETIMEOUT)")
            time.sleep(wait)
        j = r.json()["response"]
        if j["header"]["resultCode"] not in ("00", "000"):
            raise RuntimeError(f"건축HUB {j['header']['resultCode']}")
        it = (j["body"].get("items") or {})
        it = it.get("item", []) if isinstance(it, dict) else []
        it = it if isinstance(it, list) else [it]
        row = summarize_title(it)
        return row, (f"건축HUB {len(it)}동" if row is not None else "건축HUB 건물 없음")


def clean_price(fields):
    """VWorld 공시가격 응답 → apt_price.csv와 같은 열(build_apt_price.py와 같은 규칙)"""
    df = pd.DataFrame(fields).drop_duplicates()
    df = df.sort_values("lastUpdtDt").drop_duplicates(["pnu", "dongNm", "hoNm", "stdrYear"], keep="last")
    df["floor"] = df["floorNm"].astype(int)
    keys = [ho_key(h, f) for h, f in zip(df["hoNm"], df["floor"])]
    return pd.DataFrame({
        "pnu": df["pnu"], "dong_nm": df["dongNm"].str.strip(), "ho_nm": df["hoNm"], "ho_key": [k for k, _ in keys],
        "ho_prefix": [p for _, p in keys], "floor": df["floor"], "area_m2": df["prvuseAr"].astype(float),
        "price_public": df["pblntfPc"].astype("int64"), "stdr_year": df["stdrYear"].astype(int),
        "house_type": df["aphusSeCodeNm"], "complex_nm": df["aphusNm"],
    }).reset_index(drop=True)


def title_from_price(ap):
    """현행 대장에 건물이 없는 지번: 공시가격의 층·호 수로 지상층수·세대수만 채운다(build_bld_title.py와 같은 규칙)"""
    grnd = max(int(ap["floor"].max()), 0)
    hhld = len(ap)
    return {"build_year": np.nan, "elevator": np.nan, "grnd_flr": grnd if grnd > 0 else np.nan,
            "hhld_cnt": hhld if hhld > 0 else np.nan, "parking_cnt": np.nan}


def summarize_title(items):
    """건축HUB 표제부 응답(한 지번) → ml.load_buildings와 같은 건물 변수 1행(build_bld_title.py와 같은 합치기 규칙)"""
    b = pd.DataFrame(items)
    if b.empty or "mainAtchGbCdNm" not in b:
        return None
    b = b[b["mainAtchGbCdNm"] == "주건축물"].copy()
    if b.empty:
        return None
    num = ["rideUseElvtCnt", "emgenUseElvtCnt", "grndFlrCnt", "hhldCnt",
           "indrAutoUtcnt", "oudrAutoUtcnt", "indrMechUtcnt", "oudrMechUtcnt"]
    for c in num:
        b[c] = pd.to_numeric(b.get(c), errors="coerce").fillna(0)
    res = b["mainPurpsCdNm"].eq("공동주택") | b["etcPurps"].fillna("").str.contains(RESIDENTIAL)
    use = b[res] if res.any() else b
    rep = use.sort_values("hhldCnt", ascending=False).iloc[0]
    d = pd.to_numeric(str(rep.get("useAprDay", "")).strip() or np.nan, errors="coerce")
    year = d // 10000 if d >= 1e7 else (d // 100 if d >= 1e5 else np.nan)
    hhld = use["hhldCnt"].sum()
    parking = use[["indrAutoUtcnt", "oudrAutoUtcnt", "indrMechUtcnt", "oudrMechUtcnt"]].sum().sum()
    # ml.load_buildings 결측 규칙(1007_11): 세대수 0·층수 0 → 결측, 세대당 주차 3대 초과 → 결측
    hhld = hhld if hhld > 0 else np.nan
    from ml import MAX_PARKING_PER_HHLD
    return {"build_year": year, "elevator": bool((use["rideUseElvtCnt"] + use["emgenUseElvtCnt"]).sum() > 0),
            "grnd_flr": use["grndFlrCnt"].max() if use["grndFlrCnt"].max() > 0 else np.nan,
            "hhld_cnt": hhld, "parking_cnt": parking if not (parking / hhld > MAX_PARKING_PER_HHLD) else np.nan}
