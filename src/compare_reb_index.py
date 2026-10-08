"""직접 만든 구별 시점 지수와 한국부동산원 연립/다세대 매매 지수 비교(1008_03) — 재학습 없음

사용: python src/compare_reb_index.py
입력: data/processed/trades.csv(시점 지수를 6년 전체로 다시 계산 — 모델과 같은 TimeIndex), data/reference/reb_villa_index.csv
출력: outputs/reb_index_compare.csv(월별 값), outputs/reb_index_metrics.csv(상관·차이), outputs/figures/reb_index_compare.png

- 기준을 맞춘다: 부동산원 지수의 기준(2026-06 = 100)에 맞춰 우리 지수도 2026-06 = 100으로 바꾼다
- 짝: 강서구·관악구 ↔ 서남권, 강남구 ↔ 동남권(주택가격동향조사), 세 구 모두 ↔ 서울 실거래가격지수
- 기간: 모델이 쓰는 최근 3년(2023-10～) / 수집 전체 6년(2020-10～), 둘 다 우리 지수의 기준월(2026-08)까지
"""
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avm import LAST_FULL_MONTH, PROC, REF, ROOT, SGG_NAME, TimeIndex  # noqa: E402

OUT = ROOT / "outputs"
BASE = "2026-06"
PAIRS = {"강서구": "서남권(동향조사)", "관악구": "서남권(동향조사)", "강남구": "동남권(동향조사)"}
COL = {"강서구": "#2a78d6", "관악구": "#eb6834", "강남구": "#1baf7a"}
INK2, MUTED, SURF, GRID = "#52514e", "#8a8984", "#fcfcfb", "#e6e5e1"
WINDOWS = {"최근 3년": "2023-10", "6년": "2020-10"}


def ours():
    t = pd.read_csv(PROC / "trades.csv", dtype={"pnu": str, "sgg_cd": str}, parse_dates=["deal_date"], low_memory=False)
    idx = TimeIndex().fit(t).index  # 구 × 월, log(실거래/2026 공시) 중앙값의 3개월 이동평균
    idx.index = idx.index.astype(str)
    lvl = np.exp(idx - idx.loc[BASE]) * 100
    return lvl.rename(columns=SGG_NAME)


def metrics(a, b):
    d = pd.concat([a, b], axis=1).dropna()
    ch = d.pct_change(3).dropna()  # 3개월 변화율
    return {"개월": len(d), "수준 상관": d.iloc[:, 0].corr(d.iloc[:, 1]), "3개월 변화율 상관": ch.iloc[:, 0].corr(ch.iloc[:, 1]),
            "같은 방향 비율(3개월)": (np.sign(ch.iloc[:, 0]) == np.sign(ch.iloc[:, 1])).mean(),
            "차이 절댓값 평균(pt)": (d.iloc[:, 0] - d.iloc[:, 1]).abs().mean(),
            "기간 변화(우리 %)": d.iloc[-1, 0] / d.iloc[0, 0] - 1, "기간 변화(부동산원 %)": d.iloc[-1, 1] / d.iloc[0, 1] - 1}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    our = ours()
    reb = pd.read_csv(REF / "reb_villa_index.csv", encoding="utf-8-sig").pivot(index="month", columns="series", values="index")
    end = str(LAST_FULL_MONTH)
    both = our.join(reb, how="left").loc[:end]
    both.round(2).to_csv(OUT / "reb_index_compare.csv", encoding="utf-8-sig")

    rows = []
    for w, start in WINDOWS.items():
        sub = both.loc[start:]
        for g, r in PAIRS.items():
            for ref in [r, "서울(실거래)"]:
                rows.append({"기간": w, "우리 지수": g, "부동산원": ref, **metrics(sub[g], sub[ref])})
    m = pd.DataFrame(rows)
    m.round(3).to_csv(OUT / "reb_index_metrics.csv", index=False, encoding="utf-8-sig")
    print(m.round(3).to_string(index=False))

    plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "axes.facecolor": SURF, "figure.facecolor": SURF})
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), sharey=True)
    x = pd.PeriodIndex(both.index, freq="M").to_timestamp()
    for ax, (g, r) in zip(axes, PAIRS.items()):
        ax.axvspan(pd.Timestamp("2023-10-01"), x[-1], color="#cde2fb", alpha=0.35, lw=0)
        ax.plot(x, both[r], color=MUTED, lw=2, ls="--", label=f"부동산원 {r.split('(')[0]}(동향조사)")
        ax.plot(x, both["서울(실거래)"], color="#b7b6b1", lw=1.5, ls=":", label="부동산원 서울(실거래)")
        ax.plot(x, both[g], color=COL[g], lw=2.2, label=f"우리 지수 {'강서(화곡 포함)' if g == '강서구' else g}")
        ax.axhline(100, color=GRID, lw=1)
        ax.set_title(g, loc="left", fontsize=12, color=INK2)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=9, loc="lower right")
    axes[0].set_ylabel(f"{BASE} = 100")
    axes[0].text(pd.Timestamp("2023-11-01"), axes[0].get_ylim()[1] * 0.995, "모델 학습 기간(최근 3년)", fontsize=9, color=INK2, va="top")
    fig.suptitle("직접 만든 시점 지수와 부동산원 연립/다세대 지수 — 큰 흐름은 같고(관악·강남 3년 상관 0.9), 강서는 2024～25년 회복을 덜 잡는다", x=0.01, ha="left", fontweight="bold", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "figures" / "reb_index_compare.png", dpi=150, bbox_inches="tight")
    print("→ outputs/reb_index_compare.csv, outputs/reb_index_metrics.csv, outputs/figures/reb_index_compare.png")


if __name__ == "__main__":
    main()
