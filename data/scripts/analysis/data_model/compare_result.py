"""5개 추천 모델 결과 비교표 + 차트 + 분석 결과 요약 생성 (마크다운 보고서 포함).
 
입력 : OUT_DIR 안의 모델별 결과 파일
         {모델}_summary.csv                      (CV 평균/표준편차/95% CI, 테스트 적중률·정밀도/95% CI)
         {모델}_test_predictions_{실험}.csv      (테스트 개인별 결과 -> 테스트 표준편차, TOP 3 대비 차이)
출력 : OUT_DIR / model_comparison.md           (분석 결과 요약 + 표 + 차트 보고서)
       OUT_DIR / model_comparison_hit.png      (적중률 차트)
       OUT_DIR / model_comparison_precision.png(정밀도 차트)
       OUT_DIR / model_comparison.csv          (숫자 전체, 실험별 순위 포함)
       OUT_DIR / model_comparison_table.csv    (문자열 표)
 
지표 해석
  - CV  : 학습셋 5-fold, 폴드 간 평균 ± 표준편차, 95% 신뢰구간(t 분포)
  - 테스트 : hold-out 20%, 개인 단위 값의 평균 ± 표준편차, 95% 신뢰구간(정규근사)
  - TOP 3 대비 차이 : 같은 테스트 인원에서 (모델 - TOP 3)의 개인별 차이 평균과 95% 신뢰구간
                      (짝지은 비교. 구간이 0을 포함하지 않으면 차이가 뚜렷하다고 본다)
 
표의 숫자는 소수점 2자리(.2f)까지 표기한다. 차트는 matplotlib가 필요하다 (없으면 표만 생성).
"""
import argparse
from pathlib import Path
 
import numpy as np
import pandas as pd
 
TOP_K = 3  # recommend_common.TOP_K 와 동일
ID_COL = "M_CODE"
BASELINE = "Top_3"
 
# (결과 파일 접두사, 표시 이름) - 슬라이드 순서
MODELS = [
    ("Top_3", "TOP 3 (기준)"),
    ("Cross", "교차분석"),
    ("K_means", "K-MEANS"),
    ("Logistic", "로지스틱"),
    ("KNN", "KNN"),
]
EXP_LABEL = {"with_run": "달리기 포함", "without_run": "달리기 미포함"}
METRIC_LABEL = {"hit": "적중률", "precision": "정밀도"}
KOREAN_FONTS = ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR",
                "Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Sans KR")
PAIRED_KEYS = ("hit_diff", "hit_diff_ci_low", "hit_diff_ci_high",
               "precision_diff", "precision_diff_ci_low", "precision_diff_ci_high")
 
 
def default_out_dir():
    from data.scripts.analysis.data_model.recommend_model.recommend_common import OUT_DIR
    return OUT_DIR
 
 
# ---------- 데이터 ----------
def test_std(out_dir, model, exp):
    """테스트셋 개인별 HIT / 정밀도의 표준편차."""
    path = out_dir / f"{model}_test_predictions_{exp}.csv"
    if not path.exists():
        return np.nan, np.nan
    p = pd.read_csv(path, encoding="utf-8-sig")
    return p["HIT"].std(ddof=1), (p["MATCHES"] / TOP_K).std(ddof=1)
 
 
def _mean_ci(d):
    d = np.asarray(d, dtype=float)
    se = d.std(ddof=1) / np.sqrt(len(d))
    return d.mean(), d.mean() - 1.96 * se, d.mean() + 1.96 * se
 
 
def paired_vs_baseline(out_dir, model, exp):
    """같은 테스트 인원에서 (모델 - TOP 3) 개인별 차이의 평균과 95% 신뢰구간."""
    nan = {k: np.nan for k in PAIRED_KEYS}
    if model == BASELINE:
        return nan
    pa = out_dir / f"{model}_test_predictions_{exp}.csv"
    pb = out_dir / f"{BASELINE}_test_predictions_{exp}.csv"
    if not (pa.exists() and pb.exists()):
        return nan
    a = pd.read_csv(pa, encoding="utf-8-sig")[[ID_COL, "HIT", "MATCHES"]]
    b = pd.read_csv(pb, encoding="utf-8-sig")[[ID_COL, "HIT", "MATCHES"]]
    m = a.merge(b, on=ID_COL, suffixes=("", "_base"))
    hit = _mean_ci(m["HIT"] - m["HIT_base"])
    pre = _mean_ci((m["MATCHES"] - m["MATCHES_base"]) / TOP_K)
    return dict(zip(PAIRED_KEYS, (*hit, *pre)))
 
 
def build_comparison(out_dir):
    rows = []
    for key, label in MODELS:
        path = out_dir / f"{key}_summary.csv"
        if not path.exists():
            print(f"[경고] 결과 없음, 건너뜀: {path.name}")
            continue
        summary = pd.read_csv(path, encoding="utf-8-sig")
        for _, r in summary.iterrows():
            hit_sd, pre_sd = test_std(out_dir, key, r["experiment"])
            rows.append({
                "experiment": r["experiment"], "model": key, "model_label": label,
                "best_params": r["best_params"], "n_test": r["n_test"],
                "cv_hit_mean": r["cv_hit_mean"], "cv_hit_std": r["cv_hit_std"],
                "cv_hit_ci_low": r["cv_hit_ci_low"], "cv_hit_ci_high": r["cv_hit_ci_high"],
                "cv_precision_mean": r["cv_precision_mean"],
                "cv_precision_std": r["cv_precision_std"],
                "cv_precision_ci_low": r["cv_precision_ci_low"],
                "cv_precision_ci_high": r["cv_precision_ci_high"],
                "test_hit": r["test_hit"], "test_hit_std": hit_sd,
                "test_hit_ci_low": r["test_hit_ci_low"], "test_hit_ci_high": r["test_hit_ci_high"],
                "test_precision": r["test_precision"], "test_precision_std": pre_sd,
                "test_precision_ci_low": r["test_precision_ci_low"],
                "test_precision_ci_high": r["test_precision_ci_high"],
                "silhouette_test": r.get("test_silhouette", np.nan),
                **paired_vs_baseline(out_dir, key, r["experiment"]),
            })
    if not rows:
        raise SystemExit(f"비교할 결과 파일이 없습니다: {out_dir}")
 
    df = pd.DataFrame(rows)
    # 실험별 테스트 순위 (1 = 가장 높음)
    df["test_hit_rank"] = df.groupby("experiment")["test_hit"].rank(ascending=False, method="min")
    df["test_precision_rank"] = df.groupby("experiment")["test_precision"].rank(
        ascending=False, method="min")
    return df
 
 
def _pm(mean, std):
    return f"{mean:.2f} ± {std:.2f}"
 
 
def _ci(lo, hi):
    return f"[{lo:.2f}, {hi:.2f}]"
 
 
def format_table(df):
    return pd.DataFrame({
        "실험": df["experiment"].map(EXP_LABEL).fillna(df["experiment"]),
        "모델": df["model_label"],
        "최적 파라미터": df["best_params"],
        "CV 적중률 (평균±폴드SD)": [_pm(m, s) for m, s in zip(df["cv_hit_mean"], df["cv_hit_std"])],
        "CV 적중률 95%CI": [_ci(a, b) for a, b in zip(df["cv_hit_ci_low"], df["cv_hit_ci_high"])],
        "CV 정밀도 (평균±폴드SD)": [_pm(m, s) for m, s in zip(df["cv_precision_mean"], df["cv_precision_std"])],
        "CV 정밀도 95%CI": [_ci(a, b) for a, b in zip(df["cv_precision_ci_low"], df["cv_precision_ci_high"])],
        "테스트 적중률 (평균±SD)": [_pm(m, s) for m, s in zip(df["test_hit"], df["test_hit_std"])],
        "테스트 적중률 95%CI": [_ci(a, b) for a, b in zip(df["test_hit_ci_low"], df["test_hit_ci_high"])],
        "테스트 정밀도 (평균±SD)": [_pm(m, s) for m, s in zip(df["test_precision"], df["test_precision_std"])],
        "테스트 정밀도 95%CI": [_ci(a, b) for a, b in zip(df["test_precision_ci_low"], df["test_precision_ci_high"])],
        "테스트 적중률 순위": df["test_hit_rank"].astype(int),
    })
 
 
# ---------- 분석 결과로 알 수 있는 사실 ----------
def _verdict(lo, hi):
    if lo > 0:
        return "기준보다 높고 차이의 95% 신뢰구간이 0을 포함하지 않아 뚜렷한 차이"
    if hi < 0:
        return "기준보다 낮고 차이의 95% 신뢰구간이 0을 포함하지 않아 뚜렷한 차이"
    return "차이의 95% 신뢰구간이 0을 포함해 뚜렷한 차이는 확인되지 않음"
 
 
def build_findings(df):
    facts = []
    exps = list(dict.fromkeys(df["experiment"]))
 
    # 1) 달리기 계열 제외 효과
    if {"with_run", "without_run"} <= set(exps):
        w = df[df["experiment"] == "with_run"].set_index("model")
        wo = df[df["experiment"] == "without_run"].set_index("model")
        common = [m for m in w.index if m in wo.index]
        drop = (w.loc[common, "test_hit"] - wo.loc[common, "test_hit"]) * 100
        worst = drop.idxmax()
        facts.append(
            f"달리기 계열을 제외하면 모든 모델의 테스트 적중률이 {drop.min():.1f}~{drop.max():.1f}%p 낮아진다 "
            f"(하락폭 최대: {w.loc[worst, 'model_label'].replace(' (기준)', '')} {drop.max():.1f}%p). "
            "달리기 처방이 적중률에 크게 기여하고 있다는 뜻이다."
            if (drop > 0).all() else
            f"달리기 계열 제외 시 테스트 적중률 변화는 {drop.min():.1f}~{drop.max():.1f}%p이다."
        )
 
    # 2) 실험별 · 지표별: 개인화 모델 vs TOP 3
    for exp in exps:
        g = df[df["experiment"] == exp].set_index("model")
        if BASELINE not in g.index or len(g) < 2:
            continue
        label = EXP_LABEL.get(exp, exp)
        base = g.loc[BASELINE]
        pers = g.drop(index=BASELINE)
        for metric in ("hit", "precision"):
            col = f"test_{metric}"
            best = pers[col].idxmax()
            row = pers.loc[best]
            lo, hi = row[f"{metric}_diff_ci_low"], row[f"{metric}_diff_ci_high"]
            text = (
                f"[{label}] {METRIC_LABEL[metric]}: 개인화 모델 중 테스트 최고는 {row['model_label']}"
                f"({row[col]:.2f})이며, TOP 3 기준({base[col]:.2f}) 대비 "
                f"{row[f'{metric}_diff'] * 100:+.1f}%p, {_verdict(lo, hi)}."
            )
            higher = [pers.loc[m, "model_label"] for m in pers.index
                      if pers.loc[m, f"{metric}_diff_ci_low"] > 0]
            lower = [pers.loc[m, "model_label"] for m in pers.index
                     if pers.loc[m, f"{metric}_diff_ci_high"] < 0]
            text += (f" TOP 3보다 뚜렷하게 높은 모델: {', '.join(higher) if higher else '없음'}"
                     f" / 뚜렷하게 낮은 모델: {', '.join(lower) if lower else '없음'}.")
            if g[col].idxmax() == BASELINE:
                text += " 전체 1위는 기준 모델(TOP 3)이다."
            facts.append(text)
 
        spread = (g["test_hit"].max() - g["test_hit"].min()) * 100
        facts.append(f"[{label}] 모델 간 테스트 적중률 격차(최고-최저)는 {spread:.1f}%p이다.")
 
    # 3) 해석 시 주의
    half = ((df["test_hit_ci_high"] - df["test_hit_ci_low"]) / 2 * 100).mean()
    n_test = int(df["n_test"].median())
    facts.append(
        f"테스트 인원은 약 {n_test:,}명이고 적중률 95% 신뢰구간 반폭은 평균 ±{half:.1f}%p이므로, "
        "이보다 작은 모델 간 차이는 개별 신뢰구간만으로는 구분하기 어렵다(위 TOP 3 대비 차이는 같은 인원끼리 짝지어 비교한 값)."
    )
    return facts
 
 
# ---------- 차트 ----------
def make_chart(df, out_dir, metric):
    """모델별 CV/테스트 평균과 95% 신뢰구간 막대 차트 (실험별 패널). 파일명 반환."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("[경고] matplotlib가 없어 차트를 건너뜁니다 (pip install matplotlib)")
        return None
 
    avail = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in avail:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
 
    series = [  # (표시명, 평균 컬럼, CI 하한, CI 상한, 색)
        ("CV (5-fold)", f"cv_{metric}_mean", f"cv_{metric}_ci_low", f"cv_{metric}_ci_high", "#a9bfd9"),
        ("테스트 (hold-out)", f"test_{metric}", f"test_{metric}_ci_low", f"test_{metric}_ci_high", "#1f4e8c"),
    ]
    exps = list(dict.fromkeys(df["experiment"]))
    fig, axes = plt.subplots(1, len(exps), figsize=(6.2 * len(exps), 4.8), sharey=True)
    axes = np.atleast_1d(axes)
    ymax = max(df[s[3]].max() for s in series) * 1.18
    w = 0.38
 
    for ax, exp in zip(axes, exps):
        g = df[df["experiment"] == exp].reset_index(drop=True)
        x = np.arange(len(g))
        for off, (label, mcol, lo, hi, color) in zip((-w / 2, w / 2), series):
            mean = g[mcol].to_numpy()
            err = np.vstack([mean - g[lo].to_numpy(), g[hi].to_numpy() - mean])
            ax.bar(x + off, mean, w, yerr=err, capsize=3, color=color, label=label,
                   error_kw={"elinewidth": 1, "ecolor": "#333333"})
            for xi, m, h in zip(x + off, mean, g[hi].to_numpy()):
                ax.text(xi, h + ymax * 0.01, f"{m:.2f}", ha="center", va="bottom", fontsize=8)
        base = g.loc[g["model"] == BASELINE, f"test_{metric}"]
        if len(base):
            ax.axhline(base.iloc[0], color="#888888", linestyle="--", linewidth=1)
        ax.set_xticks(x)
        ax.set_xticklabels(g["model_label"], fontsize=9)
        ax.set_title(EXP_LABEL.get(exp, exp))
        ax.set_ylim(0, ymax)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel(METRIC_LABEL[metric])
    axes[0].legend(loc="upper right", fontsize=8, frameon=False)
    fig.suptitle(f"모델별 {METRIC_LABEL[metric]} (95% 신뢰구간, 점선 = TOP 3 테스트 기준)")
    fig.tight_layout()
    fname = f"model_comparison_{metric}.png"
    fig.savefig(out_dir / fname, dpi=150)
    plt.close(fig)
    return fname
 
 
# ---------- 마크다운 ----------
def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)
 
 
def metric_table(g, metric):
    headers = ["모델", "최적 파라미터", "CV 평균±폴드SD", "CV 95%CI",
               "테스트 평균±SD", "테스트 95%CI", "테스트 순위"]
    rows = []
    for _, r in g.iterrows():
        test_cell = _pm(r[f"test_{metric}"], r[f"test_{metric}_std"])
        rank = int(r[f"test_{metric}_rank"])
        if rank == 1:
            test_cell = f"**{test_cell}**"
        rows.append([
            r["model_label"], f"`{r['best_params']}`",
            _pm(r[f"cv_{metric}_mean"], r[f"cv_{metric}_std"]),
            _ci(r[f"cv_{metric}_ci_low"], r[f"cv_{metric}_ci_high"]),
            test_cell,
            _ci(r[f"test_{metric}_ci_low"], r[f"test_{metric}_ci_high"]),
            rank,
        ])
    return md_table(headers, rows)
 
 
def diff_table(g):
    """TOP 3 대비 차이(%p) 표."""
    rows = []
    for _, r in g.iterrows():
        if r["model"] == BASELINE or pd.isna(r["hit_diff"]):
            continue
        rows.append([
            r["model_label"],
            f"{r['hit_diff'] * 100:+.1f}",
            f"[{r['hit_diff_ci_low'] * 100:.1f}, {r['hit_diff_ci_high'] * 100:.1f}]",
            f"{r['precision_diff'] * 100:+.1f}",
            f"[{r['precision_diff_ci_low'] * 100:.1f}, {r['precision_diff_ci_high'] * 100:.1f}]",
        ])
    if not rows:
        return None
    return md_table(["모델", "적중률 차이(%p)", "95%CI(%p)", "정밀도 차이(%p)", "95%CI(%p)"], rows)
 
 
def write_markdown(df, out_dir, charts):
    n_test = ", ".join(f"{EXP_LABEL.get(e, e)} {int(n):,}명"
                       for e, n in df.groupby("experiment", sort=False)["n_test"].first().items())
    parts = [
        "# 추천 모델 결과 비교",
        "",
        "## 평가 기준",
        "",
        "- **적중률**: 추천 상위 3개 중 실제 처방 종목이 1개 이상 포함된 비율",
        "- **정밀도**: 추천 3개 중 실제 처방과 일치한 종목 수 / 3 의 평균",
        "- **CV**: 학습셋(80%) 5-fold 교차검증. 평균 ± 폴드 간 표준편차(폴드SD), 95% 신뢰구간(t 분포)",
        "- **테스트**: 20% hold-out을 최종 1회 평가. 평균 ± 개인 단위 표준편차(SD), 95% 신뢰구간(정규근사)",
        "- **TOP 3 대비 차이**: 같은 테스트 인원에서 (모델 - TOP 3) 개인별 차이의 평균과 95% 신뢰구간. 구간이 0을 포함하지 않으면 뚜렷한 차이",
        "- **달리기 미포함**: 달리기·조깅이 들어간 종목을 처방에서 제외하고 평가",
        f"- 테스트 인원: {n_test}",
        "",
        "## 분석 결과로 알 수 있는 사실",
        "",
    ]
    parts += [f"{i}. {t}" for i, t in enumerate(build_findings(df), 1)]
    parts.append("")
 
    for exp, g in df.groupby("experiment", sort=False):
        g = g.reset_index(drop=True)
        parts += [f"## {EXP_LABEL.get(exp, exp)}", "",
                  "### 적중률", "", metric_table(g, "hit"), "",
                  "### 정밀도", "", metric_table(g, "precision"), ""]
        dt = diff_table(g)
        if dt:
            parts += ["### TOP 3 대비 차이 (테스트, 짝지은 비교)", "", dt, ""]
 
    if any(charts.values()):
        parts += ["## 차트", ""]
        for metric, fname in charts.items():
            if fname:
                parts += [f"![{METRIC_LABEL[metric]} 비교]({fname})", ""]
 
    sil = df[df["model"] == "K_means"][["experiment", "silhouette_test"]].dropna()
    if len(sil):
        parts += ["## K-MEANS 실루엣 계수 (테스트)", ""]
        parts += [md_table(["실험", "실루엣 계수"],
                           [[EXP_LABEL.get(e, e), f"{v:.2f}"] for e, v in sil.itertuples(index=False)]), ""]
 
    path = out_dir / "model_comparison.md"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", nargs="?", default=None, help="모델 결과가 있는 폴더")
    args = ap.parse_args()
    out_dir = Path(args.out_dir) if args.out_dir else Path(default_out_dir())
 
    df = build_comparison(out_dir)
    df.to_csv(out_dir / "model_comparison.csv", index=False, encoding="utf-8-sig")
    format_table(df).to_csv(out_dir / "model_comparison_table.csv",
                            index=False, encoding="utf-8-sig")
 
    charts = {m: make_chart(df, out_dir, m) for m in ("hit", "precision")}
    md_path = write_markdown(df, out_dir, charts)
    print(f"저장 완료: {md_path}")
 
 
if __name__ == "__main__":
    main()
