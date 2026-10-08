"""행정동 → 법정동 연계표(3개 구) → data/reference/행정동_법정동_행정안전부_20260930.csv

사용: python src/build_admin_dong.py
입력: data/raw/jscode/jscode20260930.zip
      행정안전부 누리집 > 주민등록 주소코드 게시판의 "행정기관(행정동) 및 관할구역(법정동) 변경내역(2026.9.30. 시행)"
      첨부 jscode20260930.zip(키 없이 내려받음). 안의 KIKmix.20260930(고정 폭, cp949)을 읽는다
판단 근거는 docs/의사결정/1008_01_행정동_입력.md

- 행정동 하나가 법정동 여러 개에 걸치면 여러 행이 된다(예: 우장산동 → 화곡동·내발산동)
- 말소일자가 있는 행(없어진 연계)은 뺀다
"""
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avm import SGG  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "jscode" / "jscode20260930.zip"
OUT = ROOT / "data" / "reference" / "행정동_법정동_행정안전부_20260930.csv"
MEMBER = "jscode20260930/KIKmix.20260930"


def read_kikmix(path):
    lines = zipfile.ZipFile(path).read(MEMBER).split(b"\n")
    head = lines[0]
    starts = [m.start() for m in re.finditer(rb"\S+", head)]  # 고정 폭: 머리글 글자 시작 위치가 열 경계
    cuts = list(zip(starts, starts[1:] + [None]))
    cols = [head[a:b].decode("cp949").strip() for a, b in cuts]
    rows = [[l[a:b].decode("cp949").strip() for a, b in cuts] for l in lines[1:] if l.strip()]
    return pd.DataFrame(rows, columns=cols)


def main():
    d = read_kikmix(RAW)
    print(f"KIKmix {len(d):,}행")
    d = d[(d["시도명"] == "서울특별시") & d["시군구명"].isin(SGG) & (d["읍면동명"] != "") & (d["말소일자"] == "")]
    out = pd.DataFrame({
        "sgg_cd": d["행정동코드"].str[:5],
        "admin_cd": d["행정동코드"],
        "admin_dong": d["읍면동명"],
        "bjd_cd": d["법정동코드"],
        "dong": d["동리명"],
    }).sort_values(["admin_cd", "bjd_cd"])
    assert (out["bjd_cd"].str[:5] == out["sgg_cd"]).all(), "행정동과 법정동의 구가 다른 행 있음"
    print(f"3개 구: 행정동 {out['admin_cd'].nunique()}개, 연계 {len(out)}행, "
          f"법정동 여러 개에 걸친 행정동 {int((out.groupby('admin_cd').size() > 1).sum())}개")
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
