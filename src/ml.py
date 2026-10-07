"""ML 비교(1007_10): B1(공시비율) 대 ML 4계열(Ridge·KNN·랜덤포레스트·XGBoost) × 2방식(직접 / B1 잔차 보정)
최종 모델(MLModel): XGB-평균 = √(XGBoost 직접 추정 × B1 × exp(XGBoost 잔차))

누수 방지 원칙
- 학습 행의 B1 근거는 예측 때와 같은 조건으로 만든다
  - 같은 건물 근거: 그 거래보다 **앞선** 같은 건물 거래만(만료 시점 기준 expanding)
  - 동네(법정동·구) 근거: 건물 단위 GroupKFold로 **자기 건물을 뺀** 거래만
- 교차검증·그리드서치는 학습 세트 안에서 건물 단위 GroupKFold로만 한다. 최종 홀드아웃(632개 건물)은 마지막 비교에만 쓴다
- 시점 지수는 학습 세트로 맞춘다(한 거래가 구·월 중앙값에 미치는 영향은 무시할 만함 — 한계로 기록)
"""
import math

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from avm import BASE_DATE, MIN_BJD, PROC, SHRINK_K, BaselineModel, add_location

HEDONIC = ["log_public_m2", "log_area", "floor", "is_basement", "rel_floor", "is_top_floor", "age", "elevator",
           "grnd_flr", "log_hhld", "parking_per_hhld", "log_station", "log_land", "lon", "lat", "gangnam", "hwagok"]
B1_FEATS = ["b1_ratio", "area_ratio", "area_sd", "b_n", "b_gap", "b_sd"]
FEATURES = {"직접": HEDONIC, "잔차": HEDONIC + B1_FEATS}  # 직접: log ㎡당 가격 / 잔차: log(실거래 ÷ B1)
FAMILIES = ["Ridge", "KNN", "RF", "XGB"]
# XGB: 1차 그리드(깊이 3·5·7, 학습률 0.03·0.1, 트리 300·800)에서 4번 모두 학습률 0.03, 깊이·트리 수가 끝값 → 학습률 고정, 범위 확장
GRIDS = {
    "Ridge": {"ridge__alpha": [0.1, 1, 10, 100]},
    "KNN": {"knn__n_neighbors": [5, 10, 20, 40], "knn__weights": ["uniform", "distance"]},
    "RF": {"rf__min_samples_leaf": [2, 5, 20], "rf__max_features": [0.33, 0.6]},
    "XGB": {"xgb__max_depth": [3, 5, 7, 9], "xgb__n_estimators": [300, 800, 1500], "xgb__min_child_weight": [5, 20]},
}


# ---------------------------------------------------------------- 건물·위치 변수
def load_buildings(trades):
    """지번별 건물 정보. 연식 기준 연도는 표제부 대표 동 사용승인 연도, 없으면 그 지번 거래의 건축년도 중앙값"""
    b = pd.read_csv(PROC / "bld_title.csv", dtype={"pnu": str}).set_index("pnu")
    year = (b["use_apr_date"] // 10000).where(b["use_apr_date"].notna(), b["use_apr_year_max"])
    year = year.fillna(trades.groupby("pnu")["build_year"].median())
    return pd.DataFrame({"build_year": year, "elevator": b["elevator"], "grnd_flr": b["grnd_flr"],
                         "hhld_cnt": b["hhld_cnt"], "parking_cnt": b["parking_cnt"]})


def hedonic_features(rows, refs, bld):
    """rows: pnu, sgg_cd, floor, area_m2, price_public(2026 아니면 NaN) → 헤도닉 변수"""
    r = add_location(rows[["pnu"]].reset_index(drop=True), refs)
    b = bld.reindex(rows["pnu"]).reset_index(drop=True)
    floor = rows["floor"].astype(float).to_numpy()
    area = rows["area_m2"].astype(float).to_numpy()
    return pd.DataFrame({
        "log_public_m2": np.log(rows["price_public"].astype(float).to_numpy() / area),
        "log_area": np.log(area),
        "floor": floor,
        "is_basement": (floor < 0).astype(float),
        "rel_floor": floor / b["grnd_flr"].clip(lower=1).to_numpy(),
        "is_top_floor": (floor == b["grnd_flr"].to_numpy()).astype(float),
        "age": BASE_DATE.year - b["build_year"].to_numpy(),
        "elevator": b["elevator"].to_numpy(),
        "grnd_flr": b["grnd_flr"].to_numpy(),
        "log_hhld": np.log1p(b["hhld_cnt"].to_numpy()),
        "parking_per_hhld": (b["parking_cnt"] / b["hhld_cnt"].clip(lower=1)).to_numpy(),
        "log_station": np.log(r["station_dist_m"].to_numpy() + 50),
        "log_land": np.log(r["land_price_m2"].to_numpy()),
        "lon": r["lon"].to_numpy(), "lat": r["lat"].to_numpy(),
        "gangnam": (rows["sgg_cd"].to_numpy() == "11680").astype(float),
        "hwagok": (rows["sgg_cd"].to_numpy() == "11500").astype(float),
    })


# ---------------------------------------------------------------- B1 근거 변수
def _area_level(model, bjd, sgg):
    """동네 근거(법정동 거래 MIN_BJD건 이상이면 법정동, 아니면 구)의 (중앙값, 흩어짐)"""
    s = model.stats["lr"]
    bj, sg = s["bjd_cd"], s["sgg_cd"]
    med = np.where(bj["n"].reindex(bjd).fillna(0).to_numpy() >= MIN_BJD, bj["med"].reindex(bjd).to_numpy(),
                   sg["med"].reindex(sgg).to_numpy())
    sd = np.where(bj["n"].reindex(bjd).fillna(0).to_numpy() >= MIN_BJD, bj["sd"].reindex(bjd).to_numpy(),
                  sg["sd"].reindex(sgg).to_numpy())
    return med, sd


def _combine(out, area_med, area_sd, b_med, b_sd, b_n):
    out["area_ratio"], out["area_sd"] = area_med, area_sd
    out["b_n"] = b_n
    out["b_gap"] = np.where(b_n > 0, b_med - area_med, np.nan)
    out["b_sd"] = np.where(b_n > 0, b_sd, np.nan)
    out["b1_ratio"] = np.where(b_n > 0, (b_n * np.nan_to_num(b_med) + SHRINK_K * area_med) / (b_n + SHRINK_K), area_med)
    return out


def train_b1_features(train, ti, n_folds=5):
    """학습 거래마다 예측 때와 같은 조건의 B1 근거: 동네는 자기 건물을 뺀 폴드, 같은 건물은 앞선 거래만"""
    t = train.reset_index(drop=True).copy()
    t["adj"] = ti.adjust(t["sgg_cd"].to_numpy(), t["deal_date"])
    ok = (t["public_year"] == 2026) & t["price_public"].notna()
    t["lr"] = np.where(ok, np.log(t["price"] / t["price_public"]) + t["adj"], np.nan)
    area_med, area_sd = np.full(len(t), np.nan), np.full(len(t), np.nan)
    for tr_idx, te_idx in GroupKFold(n_folds).split(t, groups=t["pnu"]):
        m = BaselineModel().fit(t.iloc[tr_idx], ti)
        area_med[te_idx], area_sd[te_idx] = _area_level(m, t["bjd_cd"].iloc[te_idx].to_numpy(), t["sgg_cd"].iloc[te_idx].to_numpy())
    # 같은 건물의 앞선 거래(거래일이 엄격히 이전)만 — 홀드아웃 상황 B와 같은 조건
    b_med, b_sd, b_n = np.full(len(t), np.nan), np.full(len(t), np.nan), np.zeros(len(t))
    v = t[t["lr"].notna()].sort_values("deal_date")
    for _, g in v.groupby("pnu"):
        dates, lr = g["deal_date"].to_numpy(), g["lr"].to_numpy()
        for i, idx in enumerate(g.index):
            prior = lr[:i][dates[:i] < dates[i]]
            if len(prior):
                med = np.median(prior)
                b_med[idx], b_sd[idx], b_n[idx] = med, 1.4826 * np.median(np.abs(prior - med)), len(prior)
    # 공시가 없는 행도 같은 건물 앞선 거래 수는 0으로 둔다(B1 비율 변수는 NaN → 모델에서 제외되는 행)
    return _combine(pd.DataFrame(index=t.index), area_med, area_sd, b_med, b_sd, b_n), t


def query_b1_features(rows, model):
    """예측 대상(rows: pnu, bjd_cd, sgg_cd)의 B1 근거 — model은 학습 세트로 맞춘 BaselineModel"""
    area_med, area_sd = _area_level(model, rows["bjd_cd"].to_numpy(), rows["sgg_cd"].to_numpy())
    s = model.stats["lr"]["pnu"]
    b = s.reindex(rows["pnu"])
    b_n = b["n"].fillna(0).to_numpy()
    return _combine(pd.DataFrame(index=rows.index), area_med, area_sd, b["med"].to_numpy(), b["sd"].to_numpy(), b_n)


# ---------------------------------------------------------------- 모델
def make_pipeline(family, features, **params):
    """변수 선택·순서 고정 → (선형·이웃은 결측 채움·표준화) → 모델.
    트리 계열은 결측을 그대로 받아 분기 방향을 학습하고 척도에 영향받지 않아 표준화하지 않는다"""
    prep = [("prep", ColumnTransformer([("num", "passthrough", features)]))]
    if family == "Ridge":
        est = [("impute", SimpleImputer(strategy="median", add_indicator=True)), ("scale", StandardScaler()), ("ridge", Ridge(**params))]
    elif family == "KNN":
        est = [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("knn", KNeighborsRegressor(**params))]
    elif family == "RF":
        est = [("rf", RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1, **params))]
    else:
        est = [("xgb", XGBRegressor(tree_method="hist", learning_rate=0.03, subsample=0.8, colsample_bytree=0.8,
                                    random_state=42, n_jobs=-1, **params))]
    return Pipeline(prep + est)


def training_table(train, ti, refs, bld):
    """학습 거래 → (변수표, 목표값들). 직접 = log 기준일 ㎡당 가격, 잔차 = log(기준일 실거래가 / B1 추정)"""
    feats, t = train_b1_features(train, ti)
    X = pd.concat([hedonic_features(t, refs, bld), feats], axis=1)
    X["log_public_m2"] = np.where(t["lr"].notna(), X["log_public_m2"], np.nan)  # 2026 공시가만 변수로
    ly = np.log(t["price"].to_numpy()) + t["adj"].to_numpy()
    y_m1 = ly - np.log(t["area_m2"].to_numpy())
    b1_log = np.log(t["price_public"].to_numpy()) + X["b1_ratio"].to_numpy()
    y_m2 = np.where(t["lr"].notna(), ly - b1_log, np.nan)
    return X, {"직접": y_m1, "잔차": y_m2}, t["pnu"].to_numpy()


def grid_search(family, X, y, groups, features, n_folds=5):
    """학습 세트 안 건물 단위 GroupKFold 그리드서치. 최적값으로 학습 세트 전체에 다시 맞춘 모델은 gs.best_estimator_"""
    m = ~np.isnan(y)
    gs = GridSearchCV(make_pipeline(family, features), GRIDS[family], cv=GroupKFold(n_folds),
                      scoring="neg_mean_absolute_error", n_jobs=1)
    gs.fit(X[m], y[m], groups=groups[m])
    return gs


# ---------------------------------------------------------------- 최종 모델(1007_10 결정)
# 하이퍼파라미터: 상황 B(실제 입력에 가장 가까움) 그리드서치 최적값. 학습률 0.03은 make_pipeline에서 고정
FINAL_PARAMS = {"직접": {"max_depth": 5, "n_estimators": 800, "min_child_weight": 20},
                "잔차": {"max_depth": 9, "n_estimators": 300, "min_child_weight": 20}}


class MLModel:
    """B1 추정을 XGBoost 두 모델로 보정한다. 학습 거래·시점 지수·B1 모델(BaselineModel)은 B1과 같은 것을 쓴다
    - 직접: 건물·입지 변수로 log 기준일 ㎡당 가격
    - 잔차: 같은 변수 + B1 근거로 log(실거래 ÷ B1) → B1 × exp(예측). 공시가격이 없으면(㎡단가 추정) B1 그대로
    - 최종 = 두 값의 기하평균"""

    def fit(self, trades, time_index, refs, base):
        self.refs, self.base = refs, base
        self.bld = load_buildings(refs.trades)
        X, ys, _ = training_table(trades, time_index, refs, self.bld)
        self.models = {}
        for way, y in ys.items():
            ok = ~np.isnan(y)
            self.models[way] = make_pipeline("XGB", FEATURES[way], **FINAL_PARAMS[way]).fit(X[ok], y[ok])
        return self

    def apply(self, out, bjd, floor):
        """estimate()의 B1 결과 1건 → 추정값을 보정하고 근거를 덧붙인다(구간은 같은 배율로 옮긴 뒤 보정표가 다시 정함)"""
        q = pd.DataFrame({"pnu": [out["pnu"]], "bjd_cd": [bjd], "sgg_cd": [out["sgg_cd"]], "floor": [floor],
                          "area_m2": [out["area_used"]], "price_public": [out["price_public"]]})
        X = pd.concat([hedonic_features(q, self.refs, self.bld), query_b1_features(q, self.base)], axis=1)
        b1 = out["price_est"]
        direct = float(np.exp(self.models["직접"].predict(X)[0])) * out["area_used"]
        resid = b1 * float(np.exp(self.models["잔차"].predict(X)[0])) if out["method"] == "공시비율" else b1
        est = math.sqrt(direct * resid)
        f = est / b1
        out.update(price_b1=b1, price_ml_direct=direct, price_ml_resid=resid, ml_factor=f, price_est=est,
                   price_low=out["price_low"] * f, price_high=out["price_high"] * f)
        src = f"XGBoost 잔차 {resid / 1e8:.2f}억" if out["method"] == "공시비율" else "㎡단가 추정"
        out["basis"] = (f"{out['basis_core']} = {b1 / 1e8:.2f}억, 건물·입지 보정 ×{f:.2f}"
                        f"({src}·XGBoost 직접 {direct / 1e8:.2f}억 평균)")
        if out["flags"]:
            out["basis"] += ", " + ", ".join(out["flags"])
        return out
