"""시세 산정 핵심 모듈 — 학습·홀드아웃 검증·predict.py가 같은 함수를 쓴다.

구성
- load_refs(): 정제 데이터와 참고표를 읽는다
- parse_address(): 입력 주소(시군구·법정동·지번) → PNU (권역 밖·해석 불가는 예외)
- add_location(): 좌표·개별공시지가·가장 가까운 역 거리
- TimeIndex: 구별 월간 시점 지수(실거래가/공시가격 비율의 월 중앙값, 3개월 이동평균)
- BaselineModel: 기준선 — 공시가격 × 시점 보정한 실거래가/공시가격 비율(같은 건물 → 법정동 → 구),
  공시가격이 없으면 시점 보정한 ㎡당 단가 × 면적
- holdout_split(), evaluate(): 1007_07 검증 설계
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ho import ho_key as normalize_ho  # noqa: E402  표준 라이브러리만 쓰는 호 표기 규칙

PROC = ROOT / "data" / "processed"
REF = ROOT / "data" / "reference"
BASE_DATE = pd.Timestamp("2026-10-06")  # 산출 기준일
LAST_FULL_MONTH = pd.Period("2026-08", "M")  # 09·10월은 신고기한 전이라 덜 들어옴(1007_05)
SGG = {"강서구": "11500", "관악구": "11620", "강남구": "11680"}
SGG_NAME = {v: k for k, v in SGG.items()}


class InputError(Exception):
    """권역 밖·주소 해석 불가 등 fail 사유"""


# ---------------------------------------------------------------- 참고 데이터
@dataclass
class Refs:
    codes: pd.DataFrame
    parcels: pd.DataFrame
    stations: pd.DataFrame
    apt_price: pd.DataFrame
    trades: pd.DataFrame


def load_refs():
    codes = pd.read_csv(REF / "법정동코드_국토교통부_20260630.csv", dtype=str, encoding="utf-8-sig")
    codes = codes[codes["읍면동명"].notna() & codes["리명"].isna() & codes["법정동코드"].str[:5].isin(SGG.values())]
    codes = codes.rename(columns={"법정동코드": "bjd_cd", "읍면동명": "dong"}).assign(sgg_cd=lambda d: d["bjd_cd"].str[:5])
    parcels = pd.read_csv(REF / "parcels.csv", dtype={"pnu": str}).set_index("pnu")
    stations = pd.read_csv(REF / "subway_stations.csv")
    ap = pd.read_csv(PROC / "apt_price.csv", dtype={"pnu": str, "ho_key": str, "ho_nm": str, "dong_nm": str})
    ap = ap[ap["stdr_year"] == ap.groupby("pnu")["stdr_year"].transform("max")]  # 지번별 최신 공시 연도만
    trades = pd.read_csv(PROC / "trades.csv", dtype={"pnu": str, "bjd_cd": str, "sgg_cd": str},
                         parse_dates=["deal_date"], low_memory=False)
    refs = Refs(codes[["sgg_cd", "bjd_cd", "dong"]], parcels, stations, ap, trades)
    refs.ap_by_pnu = dict(tuple(ap.groupby("pnu")))  # 입력마다 전체를 훑지 않게 지번별로 미리 나눔
    return refs


# ---------------------------------------------------------------- 주소 → PNU
def parse_address(refs, sigungu, dong, jibun):
    sigungu, dong, jibun = str(sigungu or "").strip(), str(dong or "").strip(), str(jibun or "").strip()
    sgg = next((code for name, code in SGG.items() if name in sigungu), None)
    if sgg is None or ("서울" not in sigungu and sigungu not in SGG):
        raise InputError(f"권역 밖({sigungu or '시군구 없음'})")
    if sgg == "11500" and dong != "화곡동":
        raise InputError(f"권역 밖(강서구는 화곡동만, 입력 {dong or '법정동 없음'})")
    hit = refs.codes[(refs.codes["sgg_cd"] == sgg) & (refs.codes["dong"] == dong)]
    if hit.empty:
        raise InputError(f"주소 해석 불가(법정동 '{dong}'이 {SGG_NAME[sgg]}에 없음)")
    bjd = hit["bjd_cd"].iloc[0]
    j = jibun.replace("번지", "").replace(" ", "")
    m = re.fullmatch(r"(산)?(\d{1,4})(?:-(\d{1,4}))?", j)
    if not m:
        raise InputError(f"주소 해석 불가(지번 '{jibun}')")
    pnu = f"{bjd}{'2' if m.group(1) else '1'}{int(m.group(2)):04d}{int(m.group(3) or 0):04d}"
    return pnu, bjd, sgg


def parse_floor(floor):
    s = str(floor).strip().upper().replace("층", "")
    m = re.fullmatch(r"(B|지하|지)?\s*(-?\d+)", s)
    if not m:
        raise InputError(f"층 해석 불가('{floor}')")
    n = int(m.group(2))
    return -abs(n) if m.group(1) else n


# ---------------------------------------------------------------- 위치 변수
def add_location(df, refs):
    """pnu → 좌표·㎡당 개별공시지가·가장 가까운 역(이름, 거리 m)"""
    out = df.copy()
    p = refs.parcels.reindex(out["pnu"])
    out["lon"], out["lat"] = p["lon"].to_numpy(), p["lat"].to_numpy()
    out["land_price_m2"] = p["land_price_m2"].to_numpy()
    st = refs.stations
    kx, ky = 111320 * np.cos(np.radians(37.5)), 110540
    dist = np.full(len(out), np.nan)
    name = np.full(len(out), None, dtype=object)
    ok = out["lon"].notna().to_numpy()
    xs, ys = out.loc[ok, "lon"].to_numpy(), out.loc[ok, "lat"].to_numpy()
    for i in range(0, len(xs), 5000):
        d = np.hypot((xs[i:i + 5000, None] - st["lon"].to_numpy()) * kx, (ys[i:i + 5000, None] - st["lat"].to_numpy()) * ky)
        idx = np.where(ok)[0][i:i + 5000]
        dist[idx] = d.min(1)
        name[idx] = st["station_key"].to_numpy()[d.argmin(1)]
    out["station_dist_m"], out["station_nm"] = dist, name
    return out


# ---------------------------------------------------------------- 시점 지수
class TimeIndex:
    """구별 월간 지수 = log(실거래가/2026 공시가격)의 월 중앙값을 3개월 이동평균.
    공시가격이 위치·면적·연식·층을 반영하므로 거래 구성이 달라져도 시장 수준을 비교할 수 있다(1007_04)."""

    def fit(self, trades):
        d = trades[(trades["public_year"] == 2026) & trades["price_public"].notna()].copy()
        d["month"] = d["deal_date"].dt.to_period("M")
        d = d[d["month"] <= LAST_FULL_MONTH]
        d["lr"] = np.log(d["price"] / d["price_public"])
        raw = d.groupby(["sgg_cd", "month"])["lr"].median().unstack(0)
        months = pd.period_range(raw.index.min(), LAST_FULL_MONTH, freq="M")
        raw = raw.reindex(months).interpolate(limit_direction="both")
        self.index = raw.rolling(3, min_periods=1).mean()
        self.counts = d.groupby(["sgg_cd", "month"]).size().unstack(0).reindex(months).fillna(0).astype(int)
        return self

    def adjust(self, sgg_cd, deal_date):
        """거래 시점 → 기준일로 옮기는 로그 보정값(기준 = 마지막 완전한 달)"""
        months = pd.PeriodIndex(pd.to_datetime(deal_date), freq="M")
        months = months.where(months <= LAST_FULL_MONTH, LAST_FULL_MONTH)
        out = np.zeros(len(months))
        for sgg in np.unique(sgg_cd):
            m = np.asarray(sgg_cd) == sgg
            col = self.index[sgg]
            out[m] = col.loc[LAST_FULL_MONTH] - col.reindex(months[m]).to_numpy()
        return out

    def table(self):
        idx = self.index.copy()
        idx.index = idx.index.astype(str)
        return idx


# ---------------------------------------------------------------- 기준선 모델
SHRINK_K = 2  # 같은 건물 사례 n건을 법정동 값 쪽으로 당기는 정도: (n·건물 + k·동)/(n + k)
MIN_BJD = 20  # 법정동 통계를 쓰는 최소 거래 수
Z80 = 1.2816  # 80% 구간


def _robust(g):
    med = g.median()
    return pd.Series({"med": med, "sd": 1.4826 * (g - med).abs().median(), "n": g.size})


class BaselineModel:
    """기준선: 공시가격 × 시점 보정 비율, 없으면 시점 보정 ㎡당 단가 × 면적.
    confidence는 근거의 수준(같은 건물/법정동/구)과 면적·호 추정 여부로 정하는 잠정 규칙이며, 홀드아웃으로 보정한다."""

    def fit(self, trades, time_index):
        t = trades.copy()
        t["adj"] = time_index.adjust(t["sgg_cd"].to_numpy(), t["deal_date"])
        t["lu"] = np.log(t["price"] / t["area_m2"]) + t["adj"]
        ok = (t["public_year"] == 2026) & t["price_public"].notna()
        t["lr"] = np.where(ok, np.log(t["price"] / t["price_public"]) + t["adj"], np.nan)
        self.stats = {}
        for var in ("lr", "lu"):
            d = t.dropna(subset=[var])
            self.stats[var] = {lvl: d.groupby(lvl)[var].apply(_robust).unstack() for lvl in ("pnu", "bjd_cd", "sgg_cd")}
        self.area_by = {lvl: t.groupby(lvl)["area_m2"].median() for lvl in ("pnu", "bjd_cd")}
        self.n_trades = t.groupby("pnu").size()
        return self

    def _level(self, var, pnu, bjd, sgg):
        s = self.stats[var]
        dong = s["bjd_cd"].loc[bjd] if bjd in s["bjd_cd"].index and s["bjd_cd"].loc[bjd, "n"] >= MIN_BJD else None
        area = dong if dong is not None else s["sgg_cd"].loc[sgg]
        area_tier = "법정동" if dong is not None else "구"
        if pnu in s["pnu"].index:
            b = s["pnu"].loc[pnu]
            n = int(b["n"])
            med = (n * b["med"] + SHRINK_K * area["med"]) / (n + SHRINK_K)
            return med, area["sd"] * 0.8, "같은 건물", n, area_tier
        return area["med"], area["sd"], area_tier, int(area["n"]), area_tier

    def predict(self, pnu, bjd, sgg, area_m2, price_public=None, public_year=None, flags=()):
        flags = list(flags)
        use_ratio = price_public is not None and not pd.isna(price_public) and public_year == 2026
        if use_ratio:
            med, sd, tier, n, area_tier = self._level("lr", pnu, bjd, sgg)
            log_est = np.log(price_public) + med
            ratio = float(np.exp(med))
            basis = (f"공시가격 {price_public / 1e8:.2f}억 × 실거래/공시 비율 {ratio:.2f}"
                     f"({tier}{f' {n}건+' + area_tier if tier == '같은 건물' else f' {n}건'}, 기준일 시점보정)")
            method = "공시비율"
        else:
            med, sd, tier, n, area_tier = self._level("lu", pnu, bjd, sgg)
            log_est = med + np.log(area_m2)
            basis = (f"㎡당 {np.exp(med) / 1e4:,.0f}만원({tier}{f' {n}건+' + area_tier if tier == '같은 건물' else f' {n}건'}"
                     f", 기준일 시점보정) × {area_m2:g}㎡")
            method = "㎡단가"
        base_conf = {("공시비율", "같은 건물"): 0.80, ("공시비율", "법정동"): 0.65, ("공시비율", "구"): 0.50,
                     ("㎡단가", "같은 건물"): 0.60, ("㎡단가", "법정동"): 0.45, ("㎡단가", "구"): 0.30}[(method, tier)]
        penalty = {"면적 추정": 0.15, "공시가격 근사(같은 층 다른 면적)": 0.10, "호 불일치(층·면적으로 대체)": 0.05,
                   "위치 정보 없음": 0.05}
        conf = base_conf - sum(penalty.get(f.split("(")[0] if f.startswith("면적 추정") else f, 0) for f in flags)
        if flags:
            basis += ", " + ", ".join(flags)
        est = float(np.exp(log_est))
        return {"price_est": est, "price_low": float(np.exp(log_est - Z80 * sd)), "price_high": float(np.exp(log_est + Z80 * sd)),
                "confidence": float(np.clip(conf, 0.05, 0.95)), "basis": basis, "method": method, "tier": tier, "n": n}


# ---------------------------------------------------------------- 입력 1건 처리
def lookup_public(refs, pnu, floor, ho, area_m2):
    """공시가격 호 찾기 → (공시가격, 공시 면적, 공시 연도, 플래그)"""
    cand = refs.ap_by_pnu.get(pnu)
    if cand is None or cand.empty:
        return None, None, None, []
    year = int(cand["stdr_year"].iloc[0])
    if ho:
        key = normalize_ho(ho, floor)[0]  # (호 키, 호 앞 동 표시) 중 호 키
        m = cand[cand["ho_key"] == key]
        if len(m) > 1:
            m = m[m["floor"] == floor] if (m["floor"] == floor).any() else m
        # 호가 맞아도 면적이 입력과 1㎡ 넘게 다르면 호 표기를 잘못 맞춘 것으로 보고 층·면적으로 다시 찾는다
        if len(m) and (area_m2 is None or abs(float(m["area_m2"].median()) - area_m2) <= 1.0):
            return float(m["price_public"].median()), float(m["area_m2"].median()), year, []
    flags = ["호 불일치(층·면적으로 대체)"] if ho else []
    same_floor = cand[cand["floor"] == floor]
    if area_m2 is not None:
        m = same_floor[(same_floor["area_m2"] - area_m2).abs() <= 0.5]
        if len(m):
            return float(m["price_public"].median()), float(m["area_m2"].median()), year, flags
        if len(same_floor):  # 같은 층 가장 비슷한 면적 호를 면적 비례로
            r = same_floor.iloc[(same_floor["area_m2"] - area_m2).abs().argsort().iloc[0]]
            return float(r["price_public"] * area_m2 / r["area_m2"]), area_m2, year, flags + ["공시가격 근사(같은 층 다른 면적)"]
        return None, None, None, []
    if len(same_floor):
        return float(same_floor["price_public"].median()), float(same_floor["area_m2"].median()), year, flags
    return None, None, None, []


def estimate(refs, model, row, use_public=True):
    """입력 1행(dict: sigungu, dong, jibun, floor, ho, area_m2) → 출력 dict.
    use_public=False면 공시가격을 쓰지 않는 비교용 기준선(㎡당 단가 × 면적)"""
    pnu, bjd, sgg = parse_address(refs, row.get("sigungu"), row.get("dong"), row.get("jibun"))
    floor = parse_floor(row.get("floor"))
    ho = str(row.get("ho") or "").strip() or None
    area = pd.to_numeric(row.get("area_m2"), errors="coerce")
    area = None if pd.isna(area) or area <= 0 else float(area)
    known = pnu in refs.parcels.index or pnu in refs.ap_by_pnu or pnu in model.n_trades.index
    if not known:  # 필지·공시가격·거래 어디에도 없으면 존재하지 않는 지번으로 본다(필지는 3개 구 전체를 수집)
        raise InputError(f"주소 해석 불가(지번 {row.get('jibun')} 필지 없음)")
    flags = []
    pp, p_area, p_year, pflags = lookup_public(refs, pnu, floor, ho, area)
    flags += pflags
    if not use_public:
        pp, p_year, flags = None, None, []
    if area is None:
        if p_area is not None:
            area, src = p_area, "공시가격 호 면적"
        elif pnu in model.area_by["pnu"].index:
            area, src = float(model.area_by["pnu"].loc[pnu]), "같은 건물 거래 면적 중앙값"
        elif bjd in model.area_by["bjd_cd"].index:
            area, src = float(model.area_by["bjd_cd"].loc[bjd]), "법정동 거래 면적 중앙값"
        else:
            raise InputError("면적 추정 불가")
        flags.append(f"면적 추정({src} {area:g}㎡)")
    if pnu not in refs.parcels.index:
        flags.append("위치 정보 없음")
    out = model.predict(pnu, bjd, sgg, area, pp, p_year, flags)
    out.update({"pnu": pnu, "area_used": area})
    return out


# ---------------------------------------------------------------- 홀드아웃
def holdout_split(trades, frac=0.2, seed=42):
    """최근 12개월 거래가 있는 평가 권역 건물 중 frac을 검증 건물로(1007_07)"""
    recent = trades[(trades["deal_date"] >= BASE_DATE - pd.DateOffset(months=12) + pd.Timedelta(days=1))
                    & ((trades["sgg_cd"] != "11500") | (trades["dong"] == "화곡동"))]
    pnus = np.sort(recent["pnu"].unique())
    rng = np.random.default_rng(seed)
    test = rng.choice(pnus, size=int(round(len(pnus) * frac)), replace=False)
    return pd.Series(np.sort(test), name="pnu")


def holdout_targets(trades, test_pnu):
    recent = trades[trades["pnu"].isin(test_pnu) & (trades["deal_date"] >= BASE_DATE - pd.DateOffset(months=12) + pd.Timedelta(days=1))]
    return recent.sort_values("deal_date").groupby("pnu").tail(1)


def train_set(trades, test_pnu, targets, scenario):
    """A: 검증 건물 거래 모두 제외 / B: 검증 건물은 대상 거래 이전 거래만 남김"""
    if scenario == "A":
        return trades[~trades["pnu"].isin(test_pnu)]
    cutoff = targets.set_index("pnu")["deal_date"]
    t = trades[trades["pnu"].isin(test_pnu)]
    keep = t["deal_date"] < t["pnu"].map(cutoff)
    return pd.concat([trades[~trades["pnu"].isin(test_pnu)], t[keep]])


def evaluate(pred):
    """pred: actual(기준일 보정 실거래가), price_est, price_low, price_high, confidence"""
    ape = (pred["price_est"] - pred["actual"]).abs() / pred["actual"]
    inside = (pred["actual"] >= pred["price_low"]) & (pred["actual"] <= pred["price_high"])
    return pd.Series({"n": len(pred), "MAPE": ape.mean(), "중앙값APE": ape.median(), "±10%": (ape <= 0.1).mean(),
                      "±20%": (ape <= 0.2).mean(), "80%구간포함률": inside.mean()})


def run_holdout(refs, scenario, use_public=True, test_pnu=None):
    """검증 건물의 대상 거래를 입력처럼(호 없음, 면적 있음) 넣어 추정 → 예측표"""
    tr = refs.trades
    test_pnu = holdout_split(tr) if test_pnu is None else test_pnu
    targets = holdout_targets(tr, test_pnu)
    train = train_set(tr, test_pnu, targets, scenario)
    ti = TimeIndex().fit(train)
    model = BaselineModel().fit(train, ti)
    rows = []
    for r in targets.itertuples():
        o = estimate(refs, model, {"sigungu": "서울특별시 " + SGG_NAME[r.sgg_cd], "dong": r.dong, "jibun": r.jibun,
                                   "floor": r.floor, "ho": None, "area_m2": r.area_m2}, use_public=use_public)
        o.update({"pnu": r.pnu, "sgg_cd": r.sgg_cd, "dong": r.dong, "deal_date": r.deal_date, "price": r.price,
                  "actual": r.price * np.exp(ti.adjust(np.array([r.sgg_cd]), pd.Series([r.deal_date]))[0])})
        rows.append(o)
    p = pd.DataFrame(rows)
    p["ape"] = (p["price_est"] - p["actual"]).abs() / p["actual"]
    p["log_err"] = np.log(p["price_est"] / p["actual"])
    return p
