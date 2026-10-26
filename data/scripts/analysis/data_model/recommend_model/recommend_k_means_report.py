"""K-MEANS 체력유형 분석 보고서 (논문 방식 출력).

참고 논문: 이상진·지현욱·김진세, 「K-means 군집분석을 활용한 국민체력100 성인 참여자의
          체력유형 분류 및 특성 분석」, 한국체육학회지 65(4), 2026.

recommend_K_means.py 가 "추천 성능 평가"(학습/테스트 분할)용이라면,
이 파일은 논문처럼 전체 데이터를 대상으로 한 "체력유형 분석"(기술 통계) 결과를 만든다.

출력 폴더: OUT_DIR / kmeans_paper /
  kmeans_report.md                 보고서 (아래 표·그림·해석 포함)
  kmeans_correlation.csv           변수 간 상관계수            (논문 §25-26)
  kmeans_vif.csv                   VIF                         (논문 §27)
  kmeans_k_comparison.csv          K=3,4,5 실루엣, K-means vs 계층적  (논문 §31)
  kmeans_clusters.csv              군집별 인원/비율/평균 백분위 + 강점·약점 (논문 §38)
  kmeans_pca.csv                   PCA 설명력/적재값           (논문 §34-35)
  kmeans_distance.csv              3등급 기준군과의 유클리드 거리  (논문 §36, 근사)
  kmeans_cluster_prescription.csv  군집별 상위 처방 종목
  kmeans_assignments.csv           개인별 군집 번호
  kmeans_pca_scatter.png           PCA 2차원 군집 그림          (논문 §33)
  kmeans_profile.png               군집별 체력 프로필 그림

논문과 다른 점
  - 3등급/참가등급을 나눠 각각 군집화하지 않고 전체를 한 번에 군집화 (등급 정보 없음)
  - "3등급 기준군"은 4개 건강체력이 모두 3등급컷 이상인 사람으로 근사 (BMI·체지방률 조건, 성별·연령별 기준 미적용)
  - 계층적 군집은 계산량 때문에 표본(HIER_SAMPLE명)으로 실루엣을 비교
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from data.scripts.analysis.data_model.recommend_model.recommend_common import (
    FEATURES, ID_COL, SEED, count_items, load_data, top_k,
)
from data.scripts.fitness_standards import grade_cut_table

FINAL_K = 4              # 논문: K=3,4,5 비교 후 K=4 선정
K_COMPARE = (3, 4, 5)
HIER_SAMPLE = 5000       # 계층적 군집/표본 실루엣에 쓰는 표본 수
STRONG_Z = 0.5           # 군집 중심 Z값이 +0.5 이상 강점, -0.5 이하 약점
MIN_REF = 30             # 3등급 기준군이 이보다 적으면 거리 비교 생략
SCATTER_N = 3000
TOP_N_PRESC = 5

KO = dict(zip(FEATURES, ["근력", "근지구력", "심폐지구력", "유연성", "BMI", "체지방률"]))
# 등급 하한 표(fitness_standards.grade_cut_table)의 영문속성명 -> 원자료 컬럼
RAW_COL = {"STRENGTH": "REL_GRIP", "ENDURANCE": "CROSS_UP",
           "CARDIO": "CARDIO", "FLEXIBILITY": "SIT_REACH"}
KOREAN_FONTS = ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR",
                "Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Sans KR")
COLORS = ["#1f4e8c", "#d9822b", "#3a9d6f", "#9b59b6", "#c0392b", "#7f8c8d"]


def default_paths():
    from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER
    from data.scripts.analysis.data_model.recommend_model.recommend_common import (
        IN_PATH, OUT_DIR,
    )
    return IN_PATH, INTERMEDIATE_ENLISTMENT_FILTER / "personal_selected.csv", OUT_DIR


# ---------- 계산 ----------
def _kmeans(k):
    return KMeans(n_clusters=k, init="k-means++", n_init=10, max_iter=300, random_state=SEED)


def reference_mask(df, raw, grade):
    """3등급 기준군(근사): 4개 건강체력이 모두 3등급컷 이상인 사람."""
    m = df[[ID_COL]].merge(raw, on=ID_COL, how="left")
    ok = np.ones(len(m), dtype=bool)
    for _, r in grade.iterrows():
        ok &= (m[RAW_COL[r["영문속성명"]]] >= r["3등급컷"]).to_numpy()
    return ok


def compare_k(Z):
    n = len(Z)
    rng = np.random.RandomState(SEED)
    idx = rng.choice(n, min(n, HIER_SAMPLE), replace=False)
    rows = []
    for k in K_COMPARE:
        lab = _kmeans(k).fit(Z).labels_
        hier = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Z[idx])
        rows.append({
            "군집 수 K": k,
            "K-means 실루엣(전체)": silhouette_score(Z, lab, sample_size=min(n, 20000), random_state=SEED),
            "K-means 실루엣(표본)": silhouette_score(Z[idx], lab[idx]),
            "계층적(Ward) 실루엣(표본)": silhouette_score(Z[idx], hier),
            "최소 군집 비율(%)": np.bincount(lab).min() / n * 100,
        })
    return pd.DataFrame(rows).round(4)


def vif_table(Z):
    n = Z.shape[0]
    rows = []
    for j, f in enumerate(FEATURES):
        A = np.column_stack([np.ones(n), np.delete(Z, j, axis=1)])
        coef, *_ = np.linalg.lstsq(A, Z[:, j], rcond=None)
        r2 = 1 - (Z[:, j] - A @ coef).var() / Z[:, j].var()
        rows.append({"변수": KO[f], "VIF": round(float(1 / (1 - r2)), 2)})
    return pd.DataFrame(rows)


# ---------- 그림 ----------
def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("[경고] matplotlib가 없어 그림을 건너뜁니다 (pip install matplotlib)")
        return None
    avail = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in avail:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
    return plt


def plot_pca(plt, pc, labels, centers_pc, expl, out_dir):
    rng = np.random.RandomState(SEED)
    idx = rng.choice(len(pc), min(len(pc), SCATTER_N), replace=False)
    fig, ax = plt.subplots(figsize=(7, 5.6))
    for c in range(len(centers_pc)):
        m = idx[labels[idx] == c]
        ax.scatter(pc[m, 0], pc[m, 1], s=7, alpha=0.35, color=COLORS[c % len(COLORS)],
                   label=f"군집 {c + 1}")
        ax.scatter(*centers_pc[c], marker="X", s=200, color=COLORS[c % len(COLORS)],
                   edgecolor="white", linewidth=1.5, zorder=5)
        ax.text(centers_pc[c][0], centers_pc[c][1], f" {c + 1}", fontsize=11,
                fontweight="bold", va="center", zorder=6)
    ax.set_xlabel(f"PC1 ({expl[0]:.1f}%)")
    ax.set_ylabel(f"PC2 ({expl[1]:.1f}%)")
    ax.set_title("PCA 2차원 군집 분포 (X = 군집 중심)")
    ax.legend(frameon=False, markerscale=2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_dir / "kmeans_pca_scatter.png", dpi=150)
    plt.close(fig)


def plot_profile(plt, prof, ref_profile, out_dir):
    names = [KO[f] for f in FEATURES]
    k = len(prof)
    w = 0.8 / k
    x = np.arange(len(FEATURES))
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, (_, r) in enumerate(prof.iterrows()):
        vals = [r[n] for n in names]
        ax.bar(x + (i - (k - 1) / 2) * w, vals, w, color=COLORS[i % len(COLORS)],
               label=f"군집 {int(r['군집'])} (n={int(r['인원'])})")
    if ref_profile is not None:
        ax.plot(x, ref_profile, color="#222222", marker="o", linestyle="--", linewidth=1.2,
                label="3등급 기준군(근사)")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 100)
    ax.set_ylabel("평균 백분위 점수 (높을수록 양호)")
    ax.set_title("군집별 체력 프로필")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "kmeans_profile.png", dpi=150)
    plt.close(fig)


# ---------- 보고서 ----------
def md_table(df, floatfmt=2):
    def cell(v):
        return f"{v:.{floatfmt}f}" if isinstance(v, (float, np.floating)) else str(v)
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "|".join("---" for _ in df.columns) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def build_findings(comp, prof, corr, vif, pca_df, dist, presc_same, k_total, n_ref):
    f = []
    best = comp.loc[comp["K-means 실루엣(전체)"].idxmax()]
    sel = comp[comp["군집 수 K"] == FINAL_K].iloc[0]
    f.append(
        f"K-means 실루엣 계수는 K={int(best['군집 수 K'])}에서 가장 높고({best['K-means 실루엣(전체)']:.2f}), "
        f"선택한 K={FINAL_K}는 {sel['K-means 실루엣(전체)']:.2f}로 {best['K-means 실루엣(전체)'] - sel['K-means 실루엣(전체)']:.2f} 낮다. "
        "논문과 같이 통계적 군집 품질뿐 아니라 군집 해석 가능성을 함께 고려해 K=4를 사용했다."
    )
    wins = (comp["K-means 실루엣(표본)"] > comp["계층적(Ward) 실루엣(표본)"]).all()
    f.append("같은 표본에서 K-means 실루엣이 모든 K에서 계층적 군집보다 " +
             ("높아 K-means 사용이 타당하다." if wins else "항상 높지는 않다. 계층적 군집과의 비교 결과를 확인할 필요가 있다."))
    share = prof["비율(%)"]
    f.append(f"군집 비율은 {share.min():.1f}%~{share.max():.1f}%로 " +
             ("지나치게 작은 군집 없이 고르게 분포한다." if share.min() >= 10 else "작은 군집이 있어 해석 시 주의가 필요하다."))
    c = corr.set_index("변수").copy()
    vals = c.where(np.triu(np.ones(c.shape, dtype=bool), 1)).stack()
    pair = vals.abs().idxmax()
    flex = c.loc["유연성"].drop("유연성").abs().max()
    f.append(f"변수 간 상관이 가장 큰 쌍은 {pair[0]}-{pair[1]}(r={vals[pair]:.2f})이다. "
             f"유연성은 다른 변수와의 상관이 |r| ≤ {flex:.2f}로 낮아 비교적 독립적인 특성이다.")
    f.append(f"VIF 최댓값은 {vif['VIF'].max():.2f}로 " +
             ("모두 5 미만이어서 다중공선성 문제가 없다." if vif["VIF"].max() < 5 else "5 이상인 변수가 있어 주의가 필요하다."))
    p = pca_df.set_index("PC")
    top1 = p.loc["PC1"].drop(["설명력(%)", "누적(%)"]).abs().sort_values(ascending=False).index[:3]
    top2 = p.loc["PC2"].drop(["설명력(%)", "누적(%)"]).abs().sort_values(ascending=False).index[:2]
    f.append(f"PCA 2개 축이 전체 정보의 {p.loc['PC2', '누적(%)']:.1f}%를 설명한다 "
             f"(PC1 {p.loc['PC1', '설명력(%)']:.1f}%, PC2 {p.loc['PC2', '설명력(%)']:.1f}%). "
             f"PC1은 {', '.join(top1)}, PC2는 {', '.join(top2)} 변수의 영향이 크다.")
    for _, r in prof.iterrows():
        f.append(f"군집 {int(r['군집'])}: {int(r['인원']):,}명({r['비율(%)']:.1f}%), "
                 f"강점 {r['강점'] or '없음'} / 약점 {r['약점'] or '없음'}.")
    if dist is not None:
        near = dist.loc[dist["유클리드 거리"].idxmin()]
        far = dist.loc[dist["유클리드 거리"].idxmax()]
        f.append(f"3등급 기준군({n_ref:,}명)과 프로필이 가장 가까운 군집은 {int(near['군집'])}번({near['유클리드 거리']:.1f}), "
                 f"가장 먼 군집은 {int(far['군집'])}번({far['유클리드 거리']:.1f})이다. "
                 "논문의 해석 방식대로면 각각 개선가능군, 고위험군 후보이다(유형 이름은 군집 프로필을 보고 연구자가 확정).")
    f.append(f"{k_total}개 군집 중 {presc_same}개 군집의 처방 빈도 상위 3개가 전체 상위 3개와 같은 구성이다. " +
             ("체력유형이 달라도 빈도 기준 추천 종목은 크게 다르지 않다." if presc_same >= k_total / 2
              else "군집에 따라 추천 종목이 달라진다."))
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("processed", nargs="?", default=None, help="processed_select_personal.csv")
    ap.add_argument("raw", nargs="?", default=None, help="personal_selected.csv (원자료, 3등급 기준군 계산용)")
    ap.add_argument("out_dir", nargs="?", default=None)
    a = ap.parse_args()
    if None in (a.processed, a.raw, a.out_dir):
        d = default_paths()
    processed = Path(a.processed or d[0])
    raw_path = Path(a.raw or d[1])
    out_dir = Path(a.out_dir or d[2]) / "kmeans_paper"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_data(processed)
    X = df[FEATURES].to_numpy(float)
    n = len(X)
    Z = StandardScaler().fit_transform(X)                       # 백분위 -> Z-score (논문 §22)

    # 상관 / VIF
    corr = pd.DataFrame(X, columns=[KO[f] for f in FEATURES]).corr().round(2)
    corr = corr.rename_axis("변수").reset_index()
    vif = vif_table(Z)

    # K 비교, 최종 K-means
    comp = compare_k(Z)
    km = _kmeans(FINAL_K).fit(Z)
    labels = km.labels_

    # 군집 프로필 (원래 백분위 단위)
    prof_rows = []
    for c in range(FINAL_K):
        zc = km.cluster_centers_[c]
        row = {"군집": c + 1, "인원": int((labels == c).sum()),
               "비율(%)": round((labels == c).sum() / n * 100, 1)}
        row.update({KO[f]: round(float(X[labels == c, j].mean()), 2) for j, f in enumerate(FEATURES)})
        row["강점"] = ",".join(KO[f] for f, z in zip(FEATURES, zc) if z >= STRONG_Z)
        row["약점"] = ",".join(KO[f] for f, z in zip(FEATURES, zc) if z <= -STRONG_Z)
        prof_rows.append(row)
    prof = pd.DataFrame(prof_rows)

    # PCA
    pca = PCA(n_components=len(FEATURES), random_state=SEED).fit(Z)
    pc = pca.transform(Z)[:, :2]
    centers_pc = pca.transform(km.cluster_centers_)[:, :2]
    expl = pca.explained_variance_ratio_[:2] * 100
    pca_rows = []
    for i in range(2):
        r = {"PC": f"PC{i + 1}", "설명력(%)": round(float(expl[i]), 2),
             "누적(%)": round(float(expl[: i + 1].sum()), 2)}
        r.update({KO[f]: round(float(v), 3) for f, v in zip(FEATURES, pca.components_[i])})
        pca_rows.append(r)
    pca_df = pd.DataFrame(pca_rows)

    # 3등급 기준군과의 거리 (근사)
    dist, ref_profile, n_ref = None, None, 0
    if raw_path.exists():
        raw = pd.read_csv(raw_path, encoding="utf-8-sig",
                          usecols=lambda c: c in {ID_COL, *RAW_COL.values()})
        # 3등급 기준군 판정에는 3등급 하한만 쓴다(data/scripts/fitness_standards.py).
        grade = grade_cut_table(grades=(3,))
        ref = reference_mask(df, raw, grade)
        n_ref = int(ref.sum())
        if n_ref >= MIN_REF:
            ref_profile = X[ref].mean(axis=0)
            dist = pd.DataFrame({
                "군집": np.arange(1, FINAL_K + 1),
                "유클리드 거리": [round(float(np.linalg.norm(X[labels == c].mean(axis=0) - ref_profile)), 3)
                              for c in range(FINAL_K)],
            })
            dist["가까운 순위"] = dist["유클리드 거리"].rank(method="min").astype(int)
        else:
            print(f"[경고] 3등급 기준군이 {n_ref}명으로 적어 거리 비교를 생략합니다")
    else:
        print("[경고] 원자료/등급 정의 파일이 없어 3등급 기준군 거리 비교를 생략합니다")

    # 군집별 상위 처방 종목
    items = df["ITEMS"].tolist()
    overall = count_items(items)
    overall_top = set(top_k(overall))
    presc_rows, same = [], 0
    for c in range(FINAL_K):
        members = [items[i] for i in np.where(labels == c)[0]]
        cnt = count_items(members)
        if set(top_k(cnt)) == overall_top:
            same += 1
        for rank, (item, v) in enumerate(cnt.most_common(TOP_N_PRESC), 1):
            presc_rows.append({"군집": c + 1, "순위": rank, "종목": item,
                               "군집 내 비율(%)": round(v / len(members) * 100, 1),
                               "전체 비율(%)": round(overall[item] / n * 100, 1)})
    presc = pd.DataFrame(presc_rows)

    # 저장
    corr.to_csv(out_dir / "kmeans_correlation.csv", index=False, encoding="utf-8-sig")
    vif.to_csv(out_dir / "kmeans_vif.csv", index=False, encoding="utf-8-sig")
    comp.to_csv(out_dir / "kmeans_k_comparison.csv", index=False, encoding="utf-8-sig")
    prof.to_csv(out_dir / "kmeans_clusters.csv", index=False, encoding="utf-8-sig")
    pca_df.to_csv(out_dir / "kmeans_pca.csv", index=False, encoding="utf-8-sig")
    if dist is not None:
        dist.to_csv(out_dir / "kmeans_distance.csv", index=False, encoding="utf-8-sig")
    presc.to_csv(out_dir / "kmeans_cluster_prescription.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({ID_COL: df[ID_COL], "CLUSTER": labels + 1}).to_csv(
        out_dir / "kmeans_assignments.csv", index=False, encoding="utf-8-sig")

    plt = _plt()
    figs = []
    if plt is not None:
        plot_pca(plt, pc, labels, centers_pc, expl, out_dir)
        plot_profile(plt, prof, ref_profile, out_dir)
        figs = ["kmeans_pca_scatter.png", "kmeans_profile.png"]

    # 마크다운 보고서
    facts = build_findings(comp, prof, corr, vif, pca_df, dist, same, FINAL_K, n_ref)
    parts = [
        "# K-means 체력유형 분석 보고서", "",
        "참고 논문: 이상진·지현욱·김진세, 「K-means 군집분석을 활용한 국민체력100 성인 참여자의 체력유형 분류 및 특성 분석」, 한국체육학회지 65(4), 2026", "",
        "## 1. 분석 개요", "",
        f"- 분석 대상: {n:,}명 (개인별 첫 행, 1·2등급 제외, 운동처방 있음)",
        "- 분석 변수 6개: 근력(상대악력), 근지구력(교차윗몸일으키기), 심폐지구력, 유연성, BMI, 체지방률",
        "- 전처리: 0~100 백분위 점수(BMI·체지방률은 방향을 뒤집어 높을수록 양호) → Z-score 표준화 → K-means",
        f"- K-means 설정: k-means++, max_iter=300, random_state={SEED}, K={FINAL_K}",
        "- 논문과 다른 점: 3등급/참가등급 분리 없이 전체를 한 번에 군집화, 3등급 기준군은 4개 건강체력이 모두 3등급컷 이상인 사람으로 근사",
        "", "## 2. 분석 결과로 알 수 있는 사실", "",
    ]
    parts += [f"{i}. {t}" for i, t in enumerate(facts, 1)]
    parts += ["", "## 3. 변수 간 상관관계", "", md_table(corr), "",
              "BMI·체지방률은 방향을 뒤집었으므로 양의 상관은 체력이 좋은 사람이 신체조성도 양호한 경향이 있다는 뜻이다.", "",
              "## 4. 다중공선성 (VIF)", "", md_table(vif), "",
              "## 5. 군집 수 K 비교 (실루엣 계수)", "", md_table(comp), "",
              f"계층적 군집은 계산량 때문에 표본 {min(n, HIER_SAMPLE):,}명으로 비교했다.", "",
              "## 6. 군집별 체력 프로필 (평균 백분위 점수)", "", md_table(prof), "",
              "점수는 전체 대상 분포 기준 백분위이며 BMI·체지방률도 높을수록 양호하다. 강점/약점은 군집 중심의 Z값이 ±0.5 이상인 항목이다.", ""]
    if "kmeans_profile.png" in figs:
        parts += ["![군집별 체력 프로필](kmeans_profile.png)", ""]
    parts += ["## 7. PCA", "", md_table(pca_df, 3), ""]
    if "kmeans_pca_scatter.png" in figs:
        parts += ["![PCA 군집 분포](kmeans_pca_scatter.png)", ""]
    if dist is not None:
        parts += [f"## 8. 3등급 기준군과의 유클리드 거리 (근사, 기준군 {n_ref:,}명)", "",
                  md_table(dist, 3), "",
                  "거리가 작을수록 3등급 기준군과 체력 구조가 비슷하다. 기준군은 BMI·체지방률 조건과 성별·연령별 기준을 적용하지 않은 근사치이다.", ""]
    parts += ["## 9. 군집별 상위 처방 종목", "", md_table(presc, 1), "",
              "## 10. 해석 시 유의점", "",
              "- 유형 이름(개선가능군 등)은 K-means가 붙이는 것이 아니라 군집 프로필을 보고 연구자가 해석해 부여한다.",
              "- 군집은 등급 정보 없이 전체 데이터에서 만들었으므로 논문의 참가등급 내부 군집과 직접 비교하기 어렵다.",
              "- 백분위는 이 데이터 안에서 계산한 값이라 전체 국민 기준 백분위와 다르다."]
    (out_dir / "kmeans_report.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"저장 완료: {out_dir / 'kmeans_report.md'}")


if __name__ == "__main__":
    main()