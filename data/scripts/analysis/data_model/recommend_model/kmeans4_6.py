"""K-MEANS 체력유형 분석 보고서 (논문 방식 출력 및 K=4, 6 개별 비교 산출).

참고 논문: 이상진·지현욱·김진세, 「K-means 군집분석을 활용한 국민체력100 성인 참여자의
           체력유형 분류 및 특성 분석」, 한국체육학회지 65(4), 2026.

수정 사항:
  1. 등급별(3등급/참가등급) 분리 로직을 제거하고, 이미 필터링된 전체 입력 데이터를 대상으로 일괄 수행
  2. 군집 개수 비교 범위를 K=3, 4, 5, 6, 7로 확장하여 실루엣 계수 및 최소 군집 비율 산출
  3. K-means 전 상관관계(Correlation) 및 VIF 검증 결과 산출
  4. 핵심 비교 대상인 K=4와 K=6에 대해서 각각 개별 PCA 산점도와 군집별 체력 프로필(Bar Plot) 산출
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

TARGET_KS = (4, 6)                  # 개별 산출 및 프로필을 그릴 핵심 군집 수 K (4와 6)
K_COMPARE = (3, 4, 5, 6, 7)         # 군집 개수 비교 전체 범위 (K=3~7)
HIER_SAMPLE = 5000                  # 계층적 군집/표본 실루엣용 표본 크기
STRONG_Z = 0.5                      # 군집 중심 Z값이 +0.5 이상 강점, -0.5 이하 약점
SCATTER_N = 3000
TOP_N_PRESC = 5

KO = dict(zip(FEATURES, ["근력", "근지구력", "심폐지구력", "유연성", "BMI", "체지방률"]))
RAW_COL = {"STRENGTH": "REL_GRIP", "ENDURANCE": "CROSS_UP",
           "CARDIO": "CARDIO", "FLEXIBILITY": "SIT_REACH"}
KOREAN_FONTS = ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR",
                "Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Sans KR")
COLORS = ["#1f4e8c", "#d9822b", "#3a9d6f", "#9b59b6", "#c0392b", "#7f8c8d", "#d35400"]


def default_paths():
    from data.scripts.paths import INTERMEDIATE_ENLISTMENT_FILTER
    from data.scripts.analysis.data_model.recommend_model.recommend_common import (
        IN_PATH, OUT_DIR,
    )
    return IN_PATH, INTERMEDIATE_ENLISTMENT_FILTER / "personal_selected.csv", OUT_DIR


# ---------- 계산 ----------
def _kmeans(k):
    return KMeans(n_clusters=k, init="k-means++", n_init=10, max_iter=300, random_state=SEED)


def compare_k(Z):
    """K=3, 4, 5, 6, 7에 대한 실루엣 계수 및 최소 군집 비율 비교."""
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
    """VIF(분산팽창지수) 계산."""
    n = Z.shape[0]
    rows = []
    for j, f in enumerate(FEATURES):
        A = np.column_stack([np.ones(n), np.delete(Z, j, axis=1)])
        coef, *_ = np.linalg.lstsq(A, Z[:, j], rcond=None)
        r2 = 1 - (Z[:, j] - A @ coef).var() / Z[:, j].var()
        rows.append({"변수": KO[f], "VIF": round(float(1 / (1 - r2)), 2)})
    return pd.DataFrame(rows)


# ---------- 시각화 ----------
def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("[경고] matplotlib가 없어 그림 생성을 건너뜁니다.")
        return None
    avail = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in avail:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
    return plt


def plot_pca(plt, pc, labels, centers_pc, expl, k_val, out_dir):
    rng = np.random.RandomState(SEED)
    idx = rng.choice(len(pc), min(len(pc), SCATTER_N), replace=False)
    fig, ax = plt.subplots(figsize=(7, 5.6))
    for c in range(k_val):
        m = idx[labels[idx] == c]
        ax.scatter(pc[m, 0], pc[m, 1], s=7, alpha=0.35, color=COLORS[c % len(COLORS)],
                   label=f"군집 {c + 1}")
        ax.scatter(*centers_pc[c], marker="X", s=200, color=COLORS[c % len(COLORS)],
                   edgecolor="white", linewidth=1.5, zorder=5)
        ax.text(centers_pc[c][0], centers_pc[c][1], f" {c + 1}", fontsize=11,
                fontweight="bold", va="center", zorder=6)
    ax.set_xlabel(f"PC1 ({expl[0]:.1f}%)")
    ax.set_ylabel(f"PC2 ({expl[1]:.1f}%)")
    ax.set_title(f"[K={k_val}] PCA 2차원 군집 분포 (X = 군집 중심)")
    ax.legend(frameon=False, markerscale=2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_dir / f"kmeans_pca_scatter_K{k_val}.png", dpi=150)
    plt.close(fig)


def plot_profile(plt, prof, k_val, out_dir):
    names = [KO[f] for f in FEATURES]
    w = 0.8 / k_val
    x = np.arange(len(FEATURES))
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, (_, r) in enumerate(prof.iterrows()):
        vals = [r[n] for n in names]
        ax.bar(x + (i - (k_val - 1) / 2) * w, vals, w, color=COLORS[i % len(COLORS)],
               label=f"군집 {int(r['군집'])} (n={int(r['인원'])})")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 100)
    ax.set_ylabel("평균 백분위 점수 (높을수록 양호)")
    ax.set_title(f"[K={k_val}] 군집별 체력 프로필")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / f"kmeans_profile_K{k_val}.png", dpi=150)
    plt.close(fig)


# ---------- 메인 실행 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("processed", nargs="?", default=None, help="processed_select_personal.csv")
    ap.add_argument("raw", nargs="?", default=None, help="personal_selected.csv")
    ap.add_argument("out_dir", nargs="?", default=None)
    a = ap.parse_args()
    if None in (a.processed, a.raw, a.out_dir):
        d = default_paths()
    processed = Path(a.processed or d[0])
    out_dir = Path(a.out_dir or d[2]) / "kmeans_paper"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 이미 3등급 이하 등으로 필터링된 전체 데이터 로드
    df_all = load_data(processed)
    
    # 2. 사전 변수 분석: 상관관계 및 VIF
    X_all = df_all[FEATURES].to_numpy(float)
    corr = pd.DataFrame(X_all, columns=[KO[f] for f in FEATURES]).corr().round(2)
    corr = corr.rename_axis("변수").reset_index()
    Z_all = StandardScaler().fit_transform(X_all)
    vif = vif_table(Z_all)

    # 사전 검증 콘솔 출력
    print("=" * 65)
    print(" [1] 분석 변수 간 상관관계 행렬 (Correlation Matrix)")
    print("=" * 65)
    print(corr.to_string(index=False))
    print("\n" + "=" * 65)
    print(" [2] 다중공선성 검증 (VIF: Variance Inflation Factor)")
    print("=" * 65)
    print(vif.to_string(index=False))
    print("=" * 65 + "\n")

    corr.to_csv(out_dir / "kmeans_correlation.csv", index=False, encoding="utf-8-sig")
    vif.to_csv(out_dir / "kmeans_vif.csv", index=False, encoding="utf-8-sig")

    # 3. K=3~7 실루엣 계수 및 군집 비교 수행
    comp = compare_k(Z_all)
    comp.to_csv(out_dir / "kmeans_k_comparison.csv", index=False, encoding="utf-8-sig")

    print("=" * 65)
    print(" [3] 군집 개수(K=3~7) 실루엣 계수 및 비율 비교")
    print("=" * 65)
    print(comp.to_string(index=False))
    print("=" * 65 + "\n")

    plt = _plt()
    n_all = len(Z_all)

    # 4. 핵심 비교 대상인 K=4와 K=6에 대해 각각 모델 학습, 프로필, PCA, 처방 종목 산출
    all_assignments = []
    for k_val in TARGET_KS:
        km = _kmeans(k_val).fit(Z_all)
        labels = km.labels_

        # 군집 프로필
        prof_rows = []
        for c in range(k_val):
            zc = km.cluster_centers_[c]
            row = {"군집": c + 1, "인원": int((labels == c).sum()),
                   "비율(%)": round((labels == c).sum() / n_all * 100, 1)}
            row.update({KO[f]: round(float(X_all[labels == c, j].mean()), 2) for j, f in enumerate(FEATURES)})
            row["강점"] = ",".join(KO[f] for f, z in zip(FEATURES, zc) if z >= STRONG_Z)
            row["약점"] = ",".join(KO[f] for f, z in zip(FEATURES, zc) if z <= -STRONG_Z)
            prof_rows.append(row)
        prof = pd.DataFrame(prof_rows)
        prof.to_csv(out_dir / f"kmeans_clusters_K{k_val}.csv", index=False, encoding="utf-8-sig")

        # PCA (2차원 투영)
        pca = PCA(n_components=len(FEATURES), random_state=SEED).fit(Z_all)
        pc = pca.transform(Z_all)[:, :2]
        centers_pc = pca.transform(km.cluster_centers_)[:, :2]
        expl = pca.explained_variance_ratio_[:2] * 100
        
        pca_rows = []
        for i in range(2):
            r = {"PC": f"PC{i + 1}", "설명력(%)": round(float(expl[i]), 2),
                 "누적(%)": round(float(expl[: i + 1].sum()), 2)}
            r.update({KO[f]: round(float(v), 3) for f, v in zip(FEATURES, pca.components_[i])})
            pca_rows.append(r)
        pca_df = pd.DataFrame(pca_rows)
        pca_df.to_csv(out_dir / f"kmeans_pca_K{k_val}.csv", index=False, encoding="utf-8-sig")

        # 상위 처방 종목 분석
        items_list = df_all["ITEMS"].tolist() if "ITEMS" in df_all.columns else []
        overall = count_items(items_list) if items_list else {}
        presc_rows = []
        if items_list:
            for c in range(k_val):
                members = [items_list[i] for i in np.where(labels == c)[0]]
                cnt = count_items(members)
                for rank, (item, v) in enumerate(cnt.most_common(TOP_N_PRESC), 1):
                    presc_rows.append({"군집": c + 1, "순위": rank, "종목": item,
                                       "군집 내 비율(%)": round(v / len(members) * 100, 1),
                                       "전체 비율(%)": round(overall[item] / n_all * 100, 1)})
        presc = pd.DataFrame(presc_rows)
        presc.to_csv(out_dir / f"kmeans_cluster_prescription_K{k_val}.csv", index=False, encoding="utf-8-sig")

        # 개인별 할당 결과 저장용 수집 (K=4 기준 혹은 지정 키)
        sub_assign = pd.DataFrame({ID_COL: df_all[ID_COL], f"CLUSTER_K{k_val}": labels + 1})
        all_assignments.append(sub_assign)

        # 시각화 산출물 생성
        if plt is not None:
            plot_pca(plt, pc, labels, centers_pc, expl, k_val, out_dir)
            plot_profile(plt, prof, k_val, out_dir)

    # 개별 할당 결과 통합 저장
    if all_assignments:
        merged_assign = all_assignments[0]
        for sub in all_assignments[1:]:
            merged_assign = pd.merge(merged_assign, sub, on=ID_COL)
        merged_assign.to_csv(out_dir / "kmeans_assignments_K4_K6.csv", index=False, encoding="utf-8-sig")

    print(f"[저장 완료] K=3~7 실루엣 계수 및 K=4, K=6에 대한 분석 결과가 [{out_dir}] 폴더에 성공적으로 저장되었습니다.")


if __name__ == "__main__":
    main()