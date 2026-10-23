"""교차집단 64개 그룹별 인원수.

groupbybin.py의 cross 모드와 같은 분할 기준을 사용한다.
  - 6개 체력 백분위 각각을 CROSS_THRESHOLD 이상이면 1(상), 미만이면 0(하)
  - 코드 순서는 FEATURES 순서 (근력, 근지구력, 심폐지구력, 유연성, BMI, 체지방률)
  - 예: "101000" = 근력 상, 심폐지구력 상, 나머지 하

실행:
    python cross_group_counts.py
    python cross_group_counts.py --min_n 30 --out cross_group_counts.csv
"""
import argparse

import pandas as pd

from data.scripts.analysis.data_model.recommend_model.recommend_common import (
    FEATURES, IN_PATH, load_data,
)

KO = dict(zip(FEATURES, ["근력", "근지구력", "심폐지구력", "유연성", "BMI", "체지방률"]))
CROSS_THRESHOLD = 50  # groupbybin.py의 CROSS_THRESHOLD와 반드시 같아야 함


def pretty(code):
    """코드를 사람이 읽을 수 있는 이름으로 바꾼다. 1 = 상위."""
    names = [KO[f] for f, b in zip(FEATURES, code) if b == "1"]
    return ("·".join(names) + " 상") if names else "전 항목 하위"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_path", default=str(IN_PATH))
    ap.add_argument("--out", default="cross_group_counts.csv")
    ap.add_argument("--min_n", type=int, default=30,
                    help="분석 포함 기준 인원 (groupbybin.py의 MIN_GROUP_N과 같게)")
    a = ap.parse_args()

    # groupbybin.py와 같은 전처리: 체력 변수 결측 제거
    df = load_data(a.in_path).dropna(subset=FEATURES).reset_index(drop=True)
    bits = (df[FEATURES].to_numpy(float) >= CROSS_THRESHOLD).astype(int)
    codes = pd.Series(["".join(map(str, r)) for r in bits], name="코드")
    observed = codes.value_counts().rename_axis("코드").reset_index(name="N")

    # 가능한 64개 코드 전부 포함 (인원 0인 그룹도 표시)
    all64 = pd.DataFrame({"코드": [format(i, "06b") for i in range(64)]})
    table = all64.merge(observed, on="코드", how="left")
    table["N"] = table["N"].fillna(0).astype(int)
    table["N 비율(%)"] = (table["N"] / len(df) * 100).round(2)
    table["분석 포함"] = table["N"] >= a.min_n
    table["이름"] = table["코드"].map(pretty)
    table = table[["코드", "이름", "N", "N 비율(%)", "분석 포함"]]
    table = table.sort_values("N", ascending=False).reset_index(drop=True)

    table.to_csv(a.out, index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 120)
    print(table.to_string(index=False))

    n_zero = int((table["N"] == 0).sum())
    n_small = int((table["N"] < a.min_n).sum() - n_zero)
    n_incl = int(table["분석 포함"].sum())
    print(f"\n전체 {len(df):,}명 | 그룹 64개 중 "
          f"0명 {n_zero}개, 1~{a.min_n - 1}명 {n_small}개, "
          f"분석 포함({a.min_n}명 이상) {n_incl}개")
    print(f"[저장] {a.out}")


if __name__ == "__main__":
    main()