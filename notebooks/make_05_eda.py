"""notebooks/05_EDA_시세요인.ipynb 생성 스크립트(셀 내용을 코드로 관리해 변경 이력을 남긴다).
사용: python notebooks/make_05_eda.py && jupyter nbconvert --to notebook --execute --inplace notebooks/05_EDA_시세요인.ipynb
읽는 것: data/processed·data/reference(정제 데이터), outputs/calibration_holdout_preds.csv(검증 예측). 재학습하지 않는다
그림: outputs/figures/eda_*.png (PPT용)
"""
from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("""# 05 EDA — 데이터와 시세 요인

목적: PPT의 데이터·시세 요인 장에 쓸 그림을 여러 열·조합으로 그려 보고, 의미 있는 것을 고른다. 판단은 `docs/의사결정/1007_14_변수_정리.md`·`1007_15`.

- 가격 비교는 시점 차이를 빼기 위해 **기준일 환산 가격**(구별 시점 지수, 1007_08)으로 한다. 시세 요인은 모델이 쓰는 **최근 3년** 거래(1007_13), 거래량·시점 지수는 수집 전체 6년
- **실거래/공시 비율**은 "공시가격이 시세를 얼마나 덜 반영했나" — 모델(B1)이 쓰는 값이라, 요인별 비율 차이가 곧 ML 보정이 필요한 이유다
- 색: 권역 3개는 고정 순서(강서 화곡 = 파랑, 관악 = 주황, 강남 = 청록). 값 크기는 파랑 한 가지 색의 진하기
"""),
    code("""import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
from avm import load_refs, add_location, TimeIndex, SGG_NAME, BASE_DATE, PROC
from ml import load_buildings
FIG = ROOT / "outputs" / "figures"; FIG.mkdir(parents=True, exist_ok=True)

# 차트 공통 스타일(dataviz 기준 팔레트: 권역 3색은 모든 쌍 색각 검증 통과, 청록은 대비가 낮아 범례·직접 라벨 필수)
INK, INK2, MUTED, SURF, GRID = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb", "#e6e5e1"
SGG_ORDER = ["강서구", "관악구", "강남구"]
COL = {"강서구": "#2a78d6", "관악구": "#eb6834", "강남구": "#1baf7a"}
LABEL = {"강서구": "강서 화곡동", "관악구": "관악구", "강남구": "강남구"}
SEQ = mpl.colors.LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#104281", "#0d366b"])
DIV = mpl.colors.LinearSegmentedColormap.from_list("div", ["#2a78d6", "#f0efec", "#e34948"])
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "savefig.facecolor": SURF, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 12,
                     "axes.titlelocation": "left", "legend.frameon": False, "figure.dpi": 110, "savefig.dpi": 160})
def save(fig, name):
    fig.savefig(FIG / f"eda_{name}.png", bbox_inches="tight"); plt.show()
def won(x):  # 억 단위 축
    return f"{x / 1e8:.1f}억"

refs = load_refs()                                   # 최근 3년(모델 학습 기간)
t = refs.trades.copy()
t = t[(t.sgg_cd != "11500") | (t.dong == "화곡동")].copy()   # 평가 권역만(강서는 화곡동)
ti = TimeIndex().fit(refs.trades)
t["adj"] = np.exp(ti.adjust(t.sgg_cd.to_numpy(), t.deal_date))
t["price_adj"] = t.price * t.adj                      # 기준일 환산 실거래가
t["m2_adj"] = t.price_adj / t.area_m2 / 1e4           # 기준일 환산 ㎡당 가격(만원)
t["ratio"] = np.where(t.public_year == 2026, t.price_adj / t.price_public, np.nan)  # 기준일 환산 실거래/2026 공시
t["권역"] = t.sgg_cd.map(SGG_NAME)
b = load_buildings(t); t = t.join(b[["elevator", "grnd_flr", "hhld_cnt"]].rename(columns=lambda c: "b_" + c), on="pnu")
t = add_location(t, refs)
t["연식"] = BASE_DATE.year - t.pnu.map(b.build_year)
full = pd.read_csv(PROC / "trades.csv", dtype={"pnu": str, "sgg_cd": str}, parse_dates=["deal_date"], low_memory=False)
full = full[(full.sgg_cd != "11500") | (full.dong == "화곡동")].assign(권역=lambda d: d.sgg_cd.map(SGG_NAME))
print(f"최근 3년 평가 권역 거래 {len(t):,}건(2026 공시 비율 {t.ratio.notna().sum():,}), 6년 {len(full):,}건")
t.groupby("권역")[["m2_adj", "ratio", "area_m2", "연식"]].median().round(2)"""),

    md("## A. 데이터 개요"),
    md("### A1. 월별 거래량 (6년) — 시장 사이클"),
    code("""m = full.groupby([full.deal_date.dt.to_period("M"), "권역"]).size().unstack().loc[:"2026-08"]
fig, ax = plt.subplots(figsize=(10, 3.8))
for g in SGG_ORDER:
    s = m[g]; ax.plot(s.index.to_timestamp(), s.values, color=COL[g], lw=2, label=LABEL[g])
    ax.annotate(LABEL[g], (s.index[-1].to_timestamp(), s.values[-1]), xytext=(6, 0), textcoords="offset points", color=INK2, va="center", fontsize=9)
ax.axvspan(pd.Timestamp("2023-10-06"), pd.Timestamp("2026-08-31"), color="#cde2fb", alpha=0.35, lw=0)
ax.text(pd.Timestamp("2023-11-01"), ax.get_ylim()[1] * 0.92, "모델 학습 기간(최근 3년)", color=INK2, fontsize=9)
ax.set_title("월별 매매 거래량 — 2021년 고점 뒤 2023년까지 급감, 이후 회복"); ax.set_ylabel("건/월"); ax.legend(loc="upper right")
save(fig, "A1_monthly_volume")
print(m.resample("Y").sum() if hasattr(m, "resample") else m.groupby(m.index.year).sum())"""),
    md("### A2. 권역별 ㎡당 가격 분포 (기준일 환산, 최근 3년)"),
    code("""fig, ax = plt.subplots(figsize=(8, 3.8))
data = [t.loc[t.권역 == g, "m2_adj"].clip(upper=4000) for g in SGG_ORDER]
bp = ax.boxplot(data, orientation="horizontal", widths=0.5, patch_artist=True, showfliers=False, medianprops={"color": INK, "lw": 1.5})
for patch, g in zip(bp["boxes"], SGG_ORDER):
    patch.set_facecolor(COL[g]); patch.set_alpha(0.55); patch.set_edgecolor(COL[g])
for i, g in enumerate(SGG_ORDER, 1):
    med = t.loc[t.권역 == g, "m2_adj"].median(); ax.text(med, i + 0.33, f"중앙값 {med:,.0f}만원", ha="center", fontsize=9, color=INK2)
ax.set_yticks([1, 2, 3], [LABEL[g] for g in SGG_ORDER]); ax.set_xlabel("㎡당 가격(만원, 기준일 환산)")
ax.set_title("권역별 ㎡당 가격 — 강남은 화곡의 약 3배, 퍼짐도 가장 큼")
save(fig, "A2_m2_price_by_sgg")
t.groupby("권역").m2_adj.describe(percentiles=[.1, .5, .9]).round(0)"""),
    md("### A3. 전용면적·연식 분포"),
    code("""fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))
for g in SGG_ORDER:
    d = t[t.권역 == g]
    axes[0].hist(d.area_m2.clip(upper=120), bins=np.arange(10, 122, 4), histtype="step", lw=2, color=COL[g], label=LABEL[g], density=True)
    axes[1].hist(d.연식.dropna().clip(upper=50), bins=np.arange(0, 52, 2), histtype="step", lw=2, color=COL[g], label=LABEL[g], density=True)
axes[0].set_title("전용면적(㎡)", fontsize=10, color=INK2); axes[0].legend()
axes[1].set_title("연식(년, 2026 기준)", fontsize=10, color=INK2); axes[1].legend()
fig.suptitle("화곡·관악은 30~60㎡ 중심, 강남은 30㎡ 안팎 소형이 많다 / 관악이 가장 오래됐고(중앙값 24년) 강남이 가장 새것(13년)",
             x=0.01, y=1.03, ha="left", fontweight="bold", fontsize=12)
for a in axes: a.set_yticks([])
save(fig, "A3_area_age_dist")
t.groupby("권역")[["area_m2", "연식"]].describe().round(1)"""),

    md("## B. 공시가격과 시세 — 모델의 뼈대"),
    md("### B1. 실거래가 vs 공시가격 — 한 줄로 늘어선다"),
    code("""d = t[t.ratio.notna()]
fig, ax = plt.subplots(figsize=(6.4, 6))
for g in SGG_ORDER:
    s = d[d.권역 == g]; ax.scatter(s.price_public, s.price_adj, s=5, alpha=0.25, color=COL[g], label=LABEL[g], edgecolors="none")
lim = [3e7, 3e9]; ax.plot(lim, lim, color=MUTED, lw=1, ls="--"); ax.text(4e7, 3.4e7, "실거래 = 공시", color=MUTED, fontsize=8, rotation=38)
med = d.ratio.median(); ax.plot(lim, [x * med for x in lim], color=INK2, lw=1.2)
ax.text(0.97, 0.06, f"실선: 실거래 = 공시 × {med:.2f}(비율 중앙값)", transform=ax.transAxes, color=INK2, fontsize=9, ha="right")
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
fmt = mpl.ticker.FuncFormatter(lambda x, _: won(x)); ax.xaxis.set_major_formatter(fmt); ax.yaxis.set_major_formatter(fmt)
r2 = np.corrcoef(np.log(d.price_public), np.log(d.price_adj))[0, 1] ** 2
ax.set_title(f"실거래가 vs 공시가격(log) — 결정계수 {r2:.2f}"); ax.set_xlabel("호별 공시가격(2026)"); ax.set_ylabel("실거래가(기준일 환산)")
leg = ax.legend(markerscale=4, loc="upper left")
save(fig, "B1_price_vs_public")
print(f"log 상관 결정계수 {r2:.3f}, 비율 중앙값 {med:.3f}")"""),
    md("### B2. 무엇이 가격을 설명하나 — 변수 하나씩의 설명력(결정계수)\n\nlog 실거래가를 변수 하나(또는 구)로만 회귀했을 때 설명되는 비율. 공시가격 하나가 면적·위치·연식을 합친 것보다 많이 설명한다"),
    code("""d = t[t.ratio.notna()].dropna(subset=["land_price_m2", "station_dist_m", "연식"]).copy()
y = np.log(d.price_adj)
def r2(cols):
    X = np.column_stack([np.ones(len(d))] + [c for c in cols]); beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return 1 - ((y - X @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()
dummies = [ (d.권역 == g).astype(float) for g in SGG_ORDER[1:] ]
cands = {"공시가격": [np.log(d.price_public)], "전용면적": [np.log(d.area_m2)], "권역": dummies, "땅값(공시지가)": [np.log(d.land_price_m2)],
         "연식": [d.연식], "역 거리": [np.log(d.station_dist_m + 50)], "층": [d.floor],
         "면적+권역+땅값+연식+역+층": [np.log(d.area_m2), *dummies, np.log(d.land_price_m2), d.연식, np.log(d.station_dist_m + 50), d.floor]}
res = pd.Series({k: r2(v) for k, v in cands.items()}).sort_values()
fig, ax = plt.subplots(figsize=(8, 3.8))
colors = ["#2a78d6" if k == "공시가격" else ("#86b6ef" if "+" in k else "#b7b6b1") for k in res.index]
ax.barh(res.index, res.values, color=colors, height=0.6, edgecolor=SURF, lw=2)
for i, v in enumerate(res.values): ax.text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=9, color=INK2)
ax.set_xlim(0, 1); ax.set_xlabel("결정계수(log 실거래가)"); ax.set_title("공시가격 하나가 다른 요인을 모두 합친 것보다 가격을 더 설명")
save(fig, "B2_r2_single_features")
res.round(3)"""),
    md("### B3. 실거래/공시 비율 분포 — 공시가격은 시세의 약 60%"),
    code("""fig, ax = plt.subplots(figsize=(8, 3.6))
for g in SGG_ORDER:
    s = t.loc[(t.권역 == g), "ratio"].dropna()
    ax.hist(s[s.between(0.8, 3.2)], bins=np.arange(0.8, 3.25, 0.05), histtype="step", lw=2, color=COL[g], label=f"{LABEL[g]} (중앙값 {s.median():.2f})", density=True)
ax.text(0.99, 0.5, f"3.2 초과 {(t.ratio > 3.2).mean():.1%}는 생략", transform=ax.transAxes, ha="right", fontsize=8, color=MUTED)
ax.axvline(1, color=MUTED, lw=1, ls="--"); ax.text(1.02, ax.get_ylim()[1] * 0.9, "실거래 = 공시", color=MUTED, fontsize=8)
ax.set_yticks([]); ax.set_xlabel("실거래가 ÷ 공시가격(기준일 환산)"); ax.set_title("실거래/공시 비율 — 권역마다 다르고, 같은 권역 안에서도 퍼져 있다"); ax.legend()
save(fig, "B3_ratio_dist")
t.groupby("권역").ratio.describe(percentiles=[.1, .5, .9]).round(3)"""),
    md("### B4. 시점 지수 — 6년 동안의 시장 변화(구별, 2026-08 = 1.0)"),
    code("""ti6 = TimeIndex().fit(full)
rel = np.exp(ti6.index - ti6.index.iloc[-1]); rel.columns = [SGG_NAME[c] for c in rel.columns]
fig, ax = plt.subplots(figsize=(10, 3.8))
for g in SGG_ORDER:
    s = rel[g]; ax.plot(s.index.to_timestamp(), s.values, color=COL[g], lw=2, label=LABEL[g])
ax.axhline(1, color=MUTED, lw=0.8); ax.set_ylabel("기준월(2026-08) 대비 배율")
ax.set_title("시점 지수 — 강서·관악은 2022년 고점 뒤 조정, 강남은 2024년부터 상승"); ax.legend(loc="lower right", ncol=3)
save(fig, "B4_time_index")
rel.iloc[::6].round(3)"""),

    md("## C. 시세 요인 — 요인 × 권역\n\n각 요인을 **㎡당 가격**(시세 수준)과 **실거래/공시 비율**(공시가격이 덜 반영한 정도) 두 가지로 본다. 비율이 요인에 따라 달라지면 공시가격만으로는 부족하다는 뜻이다"),
    code("""def factor_plot(col, bins, labels, name, title, min_n=30):
    d = t.assign(구간=pd.cut(t[col], bins, labels=labels))
    agg = d.groupby(["권역", "구간"], observed=True).agg(m2=("m2_adj", "median"), ratio=("ratio", "median"), n=("m2_adj", "size")).reset_index()
    agg = agg[agg.n >= min_n]
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    x = {l: i for i, l in enumerate(labels)}
    for g in SGG_ORDER:
        s = agg[agg.권역 == g]
        for ax, v in zip(axes, ["m2", "ratio"]):
            ax.plot([x[c] for c in s.구간], s[v], color=COL[g], lw=2, marker="o", ms=6, mec=SURF, mew=2, label=LABEL[g])
    for ax, ttl in zip(axes, ["㎡당 가격 중앙값(만원)", "실거래/공시 비율 중앙값"]):
        ax.set_xticks(range(len(labels)), labels); ax.set_title(ttl, fontsize=10, color=INK2, loc="left"); ax.legend(fontsize=8)
    fig.suptitle(title, x=0.01, y=1.03, ha="left", fontweight="bold", fontsize=12)
    save(fig, name)
    return agg.pivot(index="구간", columns="권역", values=["m2", "ratio", "n"]).round(2)"""),
    md("### C1. 연식"),
    code("""factor_plot("연식", [-1, 5, 10, 15, 20, 25, 30, 35, 60], ["~5", "6~10", "11~15", "16~20", "21~25", "26~30", "31~35", "36~"], "C1_age",
            "연식 — 새 건물이 ㎡당 비싸지만, 공시 대비 비율은 오래된 건물이 더 높다(공시가격이 노후 건물 시세를 덜 반영)")"""),
    md("### C2. 층"),
    code("""factor_plot("floor", [-5, 0, 1, 2, 3, 4, 5, 30], ["지하", "1층", "2층", "3층", "4층", "5층", "6층~"], "C2_floor",
            "층 — 지하는 지상의 절반 수준, 5층 이상은 신축 고층이 많아 비싸다. 공시 대비 비율은 지하·1층이 높다")"""),
    md("### C3. 전용면적"),
    code("""factor_plot("area_m2", [0, 20, 30, 40, 50, 60, 85, 300], ["~20", "20~30", "30~40", "40~50", "50~60", "60~85", "85~"], "C3_area",
            "전용면적 — 작을수록 ㎡당 가격이 높다(원룸형 프리미엄)")"""),
    md("### C4. 지하철역 거리"),
    code("""factor_plot("station_dist_m", [0, 250, 500, 750, 1000, 1500, 5000], ["~250m", "250~500", "500~750", "750~1km", "1~1.5km", "1.5km~"], "C4_station",
            "지하철역 거리 — 효과는 약하다(화곡만 멀수록 뚜렷하게 쌈)")"""),
    md("### C5. 승강기 × 권역"),
    code("""d = t.dropna(subset=["b_elevator"]).assign(승강기=lambda x: np.where(x.b_elevator.astype(bool), "있음", "없음"))
agg = d.groupby(["권역", "승강기"]).agg(m2=("m2_adj", "median"), ratio=("ratio", "median"), n=("m2_adj", "size"), 연식=("연식", "median")).reset_index()
fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))
w = 0.38
for j, (v, ttl) in enumerate([("m2", "㎡당 가격 중앙값(만원)"), ("ratio", "실거래/공시 비율 중앙값")]):
    for k, e in enumerate(["없음", "있음"]):
        s = agg[agg.승강기 == e].set_index("권역").loc[SGG_ORDER]
        bars = axes[j].bar(np.arange(3) + (k - 0.5) * w, s[v], width=w, color=["#b7b6b1", "#2a78d6"][k], edgecolor=SURF, lw=2, label=f"승강기 {e}")
        for x0, val in zip(np.arange(3) + (k - 0.5) * w, s[v]): axes[j].text(x0, val, f"{val:,.0f}" if v == "m2" else f"{val:.2f}", ha="center", va="bottom", fontsize=8, color=INK2)
    axes[j].set_xticks(range(3), [LABEL[g] for g in SGG_ORDER]); axes[j].set_title(ttl, fontsize=10, color=INK2)
    axes[j].set_ylim(0, agg[v].max() * 1.25); axes[j].legend(fontsize=8, ncol=2, loc="upper left")
fig.suptitle("승강기 — 있는 건물이 비싸다(대부분 신축·중대형이라 연식과 함께 봐야 함)", x=0.01, y=1.03, ha="left", fontweight="bold", fontsize=12)
save(fig, "C5_elevator")
agg.round(2)"""),
    md("### C6. 땅값(㎡당 개별공시지가) vs ㎡당 가격"),
    code("""d = t.dropna(subset=["land_price_m2"])
fig, ax = plt.subplots(figsize=(7, 5))
for g in SGG_ORDER:
    s = d[d.권역 == g]; ax.scatter(s.land_price_m2 / 1e4, s.m2_adj, s=5, alpha=0.25, color=COL[g], label=LABEL[g], edgecolors="none")
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("㎡당 개별공시지가(만원, log)"); ax.set_ylabel("㎡당 가격(만원, log)")
rho = np.corrcoef(np.log(d.land_price_m2), np.log(d.m2_adj))[0, 1]
ax.set_title(f"땅값이 비싼 곳의 빌라가 비싸다 — log 상관 {rho:.2f}"); ax.legend(markerscale=4)
save(fig, "C6_land_vs_m2")
print(f"log 상관 {rho:.3f}")"""),
    md("### C7. 건물 규모(세대수)"),
    code("""factor_plot("b_hhld_cnt", [0, 4, 8, 12, 19, 30, 400], ["~4", "5~8", "9~12", "13~19", "20~30", "31~"], "C7_households",
            "건물 규모(세대수) — 세대수가 많을수록 대체로 ㎡당 가격이 높다(신축 대형 다세대)")"""),
    md("### C8. 연식 × 면적 — ㎡당 가격 히트맵(권역별)"),
    code("""ab = pd.cut(t.연식, [-1, 10, 20, 30, 60], labels=["~10년", "11~20년", "21~30년", "31년~"])
arb = pd.cut(t.area_m2, [0, 30, 45, 60, 85, 300], labels=["~30㎡", "30~45", "45~60", "60~85", "85~"])
fig, axes = plt.subplots(1, 3, figsize=(16, 3.8), gridspec_kw={"wspace": 0.12})
for k, (ax, g) in enumerate(zip(axes, SGG_ORDER)):
    m = t[t.권역 == g].assign(a=ab, r=arb).pivot_table(index="a", columns="r", values="m2_adj", aggfunc="median", observed=True)
    n = t[t.권역 == g].assign(a=ab, r=arb).pivot_table(index="a", columns="r", values="m2_adj", aggfunc="size", observed=True)
    m = m.where(n >= 15)
    im = ax.imshow(m.values, cmap=SEQ, aspect="auto", vmin=400, vmax=2500)
    ax.set_xticks(range(m.shape[1]), m.columns); ax.set_yticks(range(m.shape[0]), m.index if k == 0 else [""] * m.shape[0]); ax.grid(False)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            if pd.notna(m.values[i, j]): ax.text(j, i, f"{m.values[i, j]:,.0f}", ha="center", va="center", fontsize=8,
                                                 color="white" if m.values[i, j] > 1500 else INK)
    ax.set_title(LABEL[g], fontsize=11)
fig.colorbar(im, ax=axes, shrink=0.8, label="㎡당 가격(만원)")
fig.suptitle("연식 × 면적별 ㎡당 가격(거래 15건 미만 칸은 비움) — 같은 권역 안에서도 2~3배 차이", x=0.01, y=1.06, ha="left", fontweight="bold", fontsize=12)
save(fig, "C8_heat_age_area")"""),
    md("### C9. 지도 — 필지 좌표별 ㎡당 가격"),
    code("""fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
for ax, g in zip(axes, SGG_ORDER):
    s = t[(t.권역 == g)].dropna(subset=["lon"]).groupby("pnu").agg(lon=("lon", "first"), lat=("lat", "first"), m2=("m2_adj", "median"))
    sc = ax.scatter(s.lon, s.lat, c=s.m2.clip(300, 3000), cmap=SEQ, s=6, vmin=300, vmax=3000, edgecolors="none")
    ax.set_title(f"{LABEL[g]} ({len(s):,}개 건물)", fontsize=11); ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect(1 / np.cos(np.radians(37.5))); ax.grid(False); [sp.set_visible(False) for sp in ax.spines.values()]
fig.colorbar(sc, ax=axes, shrink=0.8, label="㎡당 가격 중앙값(만원)")
fig.suptitle("위치별 ㎡당 가격 — 같은 구 안에서도 위치에 따라 크게 다르다", x=0.01, y=1.02, ha="left", fontweight="bold", fontsize=12)
save(fig, "C9_map")"""),
    md("### C10. 변수 사이 상관 — 무엇이 서로 겹치나"),
    code("""cols = {"log ㎡당 가격": np.log(t.m2_adj), "실거래/공시 비율": t.ratio, "log 공시 ㎡단가": np.log(t.price_public / t.area_m2), "연식": t.연식,
        "log 면적": np.log(t.area_m2), "층": t.floor, "승강기": t.b_elevator.astype(float), "지상층수": t.b_grnd_flr, "log 세대수": np.log1p(t.b_hhld_cnt),
        "log 역 거리": np.log(t.station_dist_m + 50), "log 땅값": np.log(t.land_price_m2)}
c = pd.DataFrame(cols).corr()
fig, ax = plt.subplots(figsize=(8.5, 7))
im = ax.imshow(c.values, cmap=DIV, vmin=-1, vmax=1); ax.grid(False)
ax.set_xticks(range(len(c)), c.columns, rotation=45, ha="right"); ax.set_yticks(range(len(c)), c.columns)
for i in range(len(c)):
    for j in range(len(c)): ax.text(j, i, f"{c.values[i, j]:.2f}", ha="center", va="center", fontsize=7, color="white" if abs(c.values[i, j]) > 0.6 else INK)
fig.colorbar(im, ax=ax, shrink=0.8, label="상관계수")
ax.set_title("변수 상관 — 연식·승강기·층수가 서로 얽혀 있다(트리 모델은 영향이 작음)")
save(fig, "C10_corr")
c.round(2)"""),
    md("### C11. 거래유형 — 직거래는 공시가격 근처에서 거래된다"),
    code("""fig, ax = plt.subplots(figsize=(8, 3.6))
for name, col in [("중개거래", "#2a78d6"), ("직거래", "#e34948")]:
    s = t.loc[t.dealing_type == name, "ratio"].dropna()
    ax.hist(s[s.between(0.8, 3.2)], bins=np.arange(0.8, 3.25, 0.05), histtype="step", lw=2, color=col, density=True, label=f"{name} (중앙값 {s.median():.2f}, {len(s):,}건)")
ax.set_yticks([]); ax.set_xlabel("실거래가 ÷ 공시가격"); ax.legend()
ax.set_title("직거래는 공시 대비 비율이 낮은 쪽으로 치우친다 — 예측이 높게 빗나가는 이유(1007_13)")
save(fig, "C11_dealing_type")
t.groupby("dealing_type").ratio.describe(percentiles=[.1, .5, .9]).round(3)"""),

    md("## D. 검증 요약 그림 (최종 모델, 저장된 검증 예측)"),
    code("""p = pd.read_csv(ROOT / "outputs" / "calibration_holdout_preds.csv", dtype={"pnu": str, "sgg_cd": str})
p = p[(p.구분 == "보정") & (~p.area_blank)].assign(권역=lambda d: d.sgg_cd.map(SGG_NAME))
q = p[p.상황 == "B"]
fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4))
ax = axes[0]
for g in SGG_ORDER:
    s = q[q.권역 == g]; ax.scatter(s.actual, s.price_est, s=12, alpha=0.6, color=COL[g], label=LABEL[g], edgecolors=SURF, linewidths=0.5)
lim = [5e7, 4e9]; xs = np.array(lim)
ax.plot(xs, xs, color=INK2, lw=1); ax.fill_between(xs, xs * 0.8, xs * 1.2, color="#cde2fb", alpha=0.5, lw=0, label="±20%")
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
fmt = mpl.ticker.FuncFormatter(lambda x, _: won(x)); ax.xaxis.set_major_formatter(fmt); ax.yaxis.set_major_formatter(fmt)
ax.set_xlabel("실거래가(기준일 환산)"); ax.set_ylabel("추정가"); ax.legend(loc="upper left", markerscale=1.5)
ax.set_title(f"추정 vs 실제 — 검증 632건 중 {(q.ape <= .2).mean():.0%}가 ±20% 안")
ax = axes[1]
for sc, col, mk in [("A", "#eb6834", "s"), ("B", "#2a78d6", "o")]:
    g = p[p.상황 == sc]
    r = g.groupby(pd.qcut(g.confidence.rank(method="first"), 5), observed=True).agg(conf=("confidence", "mean"), hit=("ape", lambda v: (v <= .2).mean()))
    ax.plot(r.conf, r.hit, color=col, lw=2, marker=mk, ms=8, mec=SURF, mew=2, label={"A": "처음 보는 건물", "B": "같은 건물 과거 거래 있음"}[sc])
ax.plot([0.45, 0.95], [0.45, 0.95], color=MUTED, lw=1, ls="--"); ax.text(0.86, 0.89, "신뢰도 = 실제", color=MUTED, fontsize=8, rotation=38)
ax.set_xlim(0.45, 0.95); ax.set_ylim(0.45, 0.95); ax.set_xlabel("평균 신뢰도(5분위)"); ax.set_ylabel("실제 ±20% 적중률"); ax.legend(loc="upper left")
ax.set_title("신뢰도와 실제 적중률이 거의 같다(대부분 약간 보수적)")
save(fig, "D1_pred_vs_actual_reliability")"""),
    md("""## 관찰

PPT에 쓸 그림 선택과 해석은 `docs/의사결정/1007_15_EDA.md`에 정리한다."""),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
path = Path(__file__).with_name("05_EDA_시세요인.ipynb")
nbf.write(nb, path)
print("작성:", path)
