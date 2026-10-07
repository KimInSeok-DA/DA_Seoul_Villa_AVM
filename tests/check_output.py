"""predict.py 출력 규격 검사

사용: uv run python tests/check_output.py --input tests/sample_input.csv --output output.csv
검사: 컬럼 7개·순서, id가 입력과 같은 순서로 모두 있음, status 값, ok 행의 금액이 원 단위 양의 정수이고
price_low ≤ price_est ≤ price_high, confidence 0~1, basis가 비어 있지 않음. fail 행은 사유가 있음
"""
import argparse
import sys

import pandas as pd

COLS = ["id", "price_est", "price_low", "price_high", "confidence", "basis", "status"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--expect-ok", action="store_true", help="권역 안 정상 입력이라 전부 ok여야 할 때")
    a = ap.parse_args()
    inp = pd.read_csv(a.input, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    out = pd.read_csv(a.output, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    errors = []
    if list(out.columns) != COLS:
        errors.append(f"컬럼 불일치: {list(out.columns)}")
    if list(out["id"]) != list(inp["id"]):
        errors.append("id가 입력과 다름(개수·순서)")
    ok = out[out["status"] == "ok"]
    bad_status = out[~out["status"].str.match(r"^(ok|fail: .+)$")]
    if len(bad_status):
        errors.append(f"status 형식 오류 id={list(bad_status['id'])}")
    for c in ["price_est", "price_low", "price_high"]:
        v = pd.to_numeric(ok[c], errors="coerce")
        if v.isna().any() or (v <= 0).any() or (v % 1 != 0).any():
            errors.append(f"{c}: ok 행에 양의 정수가 아닌 값")
    est, lo, hi = (pd.to_numeric(ok[c]) for c in ["price_est", "price_low", "price_high"])
    if ((lo > est) | (est > hi)).any():
        errors.append("price_low ≤ price_est ≤ price_high 위반")
    conf = pd.to_numeric(out["confidence"], errors="coerce")
    if conf.isna().any() or ((conf < 0) | (conf > 1)).any():
        errors.append("confidence 0~1 위반")
    if (ok["basis"].str.strip() == "").any():
        errors.append("ok 행에 basis 없음")
    crash = out[out["status"].str.contains("처리 오류")]
    if len(crash):  # 권역 밖·주소 해석 불가가 아닌, 예상 못 한 코드 오류
        errors.append(f"처리 오류(코드 결함) id={list(crash['id'])}: {crash['status'].iloc[0]}")
    if a.expect_ok and len(ok) < len(out):
        errors.append(f"모두 ok여야 하는 입력에서 fail id={list(out.loc[out['status'] != 'ok', 'id'])}")
    print(f"{len(out)}행: ok {len(ok)}, fail {len(out) - len(ok)}")
    for e in errors:
        print("  [오류]", e)
    print("규격 통과" if not errors else "규격 위반")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
