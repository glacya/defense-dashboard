"""추천 모델 5종 공통 모듈: 데이터 로드, 분할, 평가, 결과 저장.

평가 방식
  - HIT      : 추천 상위 3개 중 실제 처방이 1개 이상 포함되면 1
  - 정밀도   : 추천 3개 중 실제 처방과 일치하는 종목 수 / 3
  - HOLD-OUT : 80/20 분할, 테스트셋은 최종 1회만 사용
  - K-FOLD   : 학습셋(80%)에서 5-fold, 평균/표준편차/95% 신뢰구간 보고
  - 실험     : 달리기 포함(with_run) / 달리기 계열 제외(without_run)
  - 모든 모델이 같은 SEED로 같은 분할을 사용하므로 결과를 직접 비교할 수 있다.
"""
import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.model_selection import KFold, train_test_split
from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER 
from config import DATA_SCRIPTS_DIR
DATA_DIR = INTERMEDIATE_ENLISTMENT_FILTER
IN_PATH = DATA_DIR / "processed_select_personal.csv"
OUT_DIR = DATA_SCRIPTS_DIR /"analysis/data_model/recommend_results"  # 5개 모델 결과를 한 폴더에 저장

ID_COL = "M_CODE"
TARGET_COL = "PRESCRIPTION"
FEATURES = [
    "REL_GRIP_PCT", "CROSS_UP_PCT", "CARDIO_PCT", "SIT_REACH_PCT",
    "BMI_PCT", "BODY_FAT_PERCENTAGE_PCT",
]

# 달리기 계열 판정 키워드 ("달리기 미포함" 실험에서 제거할 종목)
RUN_KEYWORDS = ("달리기")
EXPERIMENTS = {"with_run": False, "without_run": True}  # 실험명: 달리기 제외 여부

SEED = 42
TEST_SIZE = 0.2
N_FOLDS = 5
TOP_K = 3


# ---------- 데이터 ----------
def load_data(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["ITEMS"] = df[TARGET_COL].fillna("").map(
        lambda s: [i for i in str(s).split(",") if i]
    )
    return df


def drop_running(df):
    """처방에서 달리기 계열 종목을 제거하고, 처방이 비는 행은 제외."""
    df = df.copy()
    df["ITEMS"] = df["ITEMS"].map(
        lambda lst: [i for i in lst if not any(k in i for k in RUN_KEYWORDS)]
    )
    return df[df["ITEMS"].map(len) > 0].reset_index(drop=True)


# ---------- 추천 보조 ----------
def count_items(items_list):
    c = Counter()
    for lst in items_list:
        c.update(lst)
    return c


def top_k(counter, k=TOP_K, fallback=None):
    """빈도 상위 k개. 부족하면 fallback(전체 빈도)으로 채운다."""
    rec = [i for i, _ in counter.most_common(k)]
    if fallback is not None and len(rec) < k:
        for i, _ in fallback.most_common():
            if i not in rec:
                rec.append(i)
            if len(rec) == k:
                break
    return rec


# ---------- 평가 ----------
def evaluate(model, X, items):
    recs = model.recommend(X)
    matches = np.array([len(set(r) & set(a)) for r, a in zip(recs, items)])
    out = {
        "recs": recs,
        "matches": matches,
        "hit": (matches >= 1).astype(float),
        "precision": matches / TOP_K,
        "extra": {},
    }
    if hasattr(model, "extra_metrics"):
        out["extra"] = model.extra_metrics(X)
    return out


def normal_ci(arr):
    se = arr.std(ddof=1) / np.sqrt(len(arr))
    return arr.mean() - 1.96 * se, arr.mean() + 1.96 * se


def t_ci(vals):
    vals = np.asarray(vals, dtype=float)
    half = stats.t.ppf(0.975, len(vals) - 1) * vals.std(ddof=1) / np.sqrt(len(vals))
    return vals.mean() - half, vals.mean() + half


# ---------- 실험 실행 ----------
def run_experiment(name, factory, grid, df, exp_name, out_dir):
    X = df[FEATURES].to_numpy(float)
    items = df["ITEMS"].tolist()
    train_idx, test_idx = train_test_split(
        np.arange(len(df)), test_size=TEST_SIZE, random_state=SEED
    )

    # 1) K-FOLD CV (학습셋 내부): 하이퍼파라미터별 성능
    kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    rows = []
    for params in grid:
        for fold, (tr, va) in enumerate(kf.split(train_idx), 1):
            a, b = train_idx[tr], train_idx[va]
            model = factory(**params).fit(X[a], [items[i] for i in a])
            r = evaluate(model, X[b], [items[i] for i in b])
            rows.append({
                "experiment": exp_name, "params": str(params), "fold": fold,
                "hit": r["hit"].mean(), "precision": r["precision"].mean(),
                "silhouette": r["extra"].get("silhouette", np.nan),
            })
    cv = pd.DataFrame(rows)
    by_param = cv.groupby("params", sort=False)["hit"].mean()
    best_key = by_param.idxmax()
    best_params = grid[list(by_param.index).index(best_key)]
    cvb = cv[cv["params"] == best_key]

    # 2) HOLD-OUT: 선택된 파라미터로 학습셋 전체 학습 -> 테스트셋 1회 평가
    model = factory(**best_params).fit(X[train_idx], [items[i] for i in train_idx])
    r = evaluate(model, X[test_idx], [items[i] for i in test_idx])
    hit_lo, hit_hi = normal_ci(r["hit"])
    pre_lo, pre_hi = normal_ci(r["precision"])
    cv_hit_lo, cv_hit_hi = t_ci(cvb["hit"])
    cv_pre_lo, cv_pre_hi = t_ci(cvb["precision"])

    summary = {
        "model": name, "experiment": exp_name, "best_params": str(best_params),
        "n_train": len(train_idx), "n_test": len(test_idx),
        "cv_hit_mean": cvb["hit"].mean(), "cv_hit_std": cvb["hit"].std(ddof=1),
        "cv_hit_ci_low": cv_hit_lo, "cv_hit_ci_high": cv_hit_hi,
        "cv_precision_mean": cvb["precision"].mean(),
        "cv_precision_std": cvb["precision"].std(ddof=1),
        "cv_precision_ci_low": cv_pre_lo, "cv_precision_ci_high": cv_pre_hi,
        "test_hit": r["hit"].mean(), "test_hit_ci_low": hit_lo, "test_hit_ci_high": hit_hi,
        "test_precision": r["precision"].mean(),
        "test_precision_ci_low": pre_lo, "test_precision_ci_high": pre_hi,
        "cv_silhouette_mean": cvb["silhouette"].mean(),
        "test_silhouette": r["extra"].get("silhouette", np.nan),
    }

    # 3) 결과 저장 (한 폴더, 파일명에 모델명 접두)
    pred = pd.DataFrame({
        ID_COL: df[ID_COL].to_numpy()[test_idx],
        "ACTUAL": [",".join(items[i]) for i in test_idx],
        "RECOMMEND": [",".join(x) for x in r["recs"]],
        "MATCHES": r["matches"],
        "HIT": r["hit"].astype(int),
    })
    pred.to_csv(out_dir / f"{name}_test_predictions_{exp_name}.csv",
                index=False, encoding="utf-8-sig")
    if hasattr(model, "describe"):
        for key, table in model.describe().items():
            table.to_csv(out_dir / f"{name}_{key}_{exp_name}.csv",
                         index=False, encoding="utf-8-sig")
    return summary, cv


def main(name, factory, grid):
    ap = argparse.ArgumentParser()
    ap.add_argument("in_path", nargs="?", default=IN_PATH)
    ap.add_argument("out_dir", nargs="?", default=OUT_DIR)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = load_data(args.in_path)

    summaries, cvs = [], []
    for exp_name, no_run in EXPERIMENTS.items():
        df = drop_running(base) if no_run else base
        s, cv = run_experiment(name, factory, grid, df, exp_name, out_dir)
        summaries.append(s)
        cvs.append(cv)

    pd.concat(cvs).to_csv(out_dir / f"{name}_cv_results.csv",
                          index=False, encoding="utf-8-sig")
    summary = pd.DataFrame(summaries)
    summary.to_csv(out_dir / f"{name}_summary.csv", index=False, encoding="utf-8-sig")

    show = ["experiment", "best_params", "cv_hit_mean", "cv_hit_std",
            "test_hit", "test_precision"]
    print(f"[{name}] 결과 저장: {out_dir}")
    print(summary[show].round(4).to_string(index=False))