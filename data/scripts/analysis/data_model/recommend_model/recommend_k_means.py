"""K-MEANS 체력유형 분석 보고서 (등급별 분리 분석, K 지정 가능).

참고 논문: 이상진·지현욱·김진세, 「K-means 군집분석을 활용한 국민체력100 성인 참여자의
          체력유형 분류 및 특성 분석」, 한국체육학회지 65(4), 2026.

수정 사항 (이전 버전 대비)
  1. 등급별 최종 K를 명령행 옵션(--k_3, --k_part)으로 지정 가능 (기본값: 3등급 3, 참가등급 4)
  2. --assign_ks 로 추가 K(예: 4 6)의 할당 결과를 한 파일에 함께 저장
  3. 할당 파일에 GROUP(예: "참가등급-C2")과 GROUP_K{k} 열을 추가하여 freq_analysis 스크립트에서
     등급이 섞이지 않도록 바로 사용 가능 (--kmeans_col GROUP 또는 GROUP_K4)
  4. 등급 필터를 정확한 문자열 일치로 변경 (기존 정규식 대체 로직 제거)
  5. 입력·출력 경로를 옵션으로 받도록 변경, 사용하지 않던 경로 인자 및 import 제거
  6. --no_plot 옵션으로 그림 생성 생략 가능
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
    FEATURES, ID_COL, IN_PATH, OUT_DIR, SEED, count_items, load_data,
)

TARGET_GRADES = ("3등급", "참가등급")
DEFAULT_K = {"3등급": 3, "참가등급": 4}   # 등급별 기본 최종 K
K_COMPARE = (3, 4, 5, 6, 7)               # 실루엣 비교 범위
HIER_SAMPLE = 5000                        # 계층적 군집/실루엣 표본 크기
STRONG_Z = 0.5                            # 군집 중심 Z값 +0.5 이상 강점, -0.5 이하 약점
SCATTER_N = 3000
TOP_N_PRESC = 5
MIN_GRADE_N = 10                          # 이보다 작은 등급 집단은 분석에서 제외

KO = dict(zip(FEATURES, ["근력", "근지구력", "심폐지구력", "유연성", "BMI", "체지방률"]))
KOREAN_FONTS = ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR",
                "Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Sans KR")
COLORS = ["#1f4e8c", "#d9822b", "#3a9d6f", "#9b59b6", "#c0392b", "#7f8c8d", "#d35400"]


# ---------- 계산 ----------
def _kmeans(k):
    return KMeans(n_clusters=k, init="k-means++", n_init=10, max_iter=300, random_state=SEED)


def filter_target_grades(df):
    """3등급과 참가등급만 남긴다. 해당 등급이 없으면 전체 데이터를 사용한다."""
    if "GRADE" not in df.columns:
        return df
    grade = df["GRADE"].astype(str).str.strip()
    filtered = df[grade.isin(TARGET_GRADES)].copy()
    if filtered.empty:
        print("[경고] 3등급/참가등급 행이 없어 전체 데이터를 사용합니다.")
        return df.copy()
    return filtered


def compare_k(Z):
    """K=3~7에 대한 실루엣 계수 및 최소 군집 비율 비교."""
    n = len(Z)
    rng = np.random.RandomState(SEED)
    idx = rng.choice(n, min(n, HIER_SAMPLE), replace=False)
    rows = []
    for k in K_COMPARE:
        lab = _kmeans(k).fit(Z).labels_
        hier = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(Z[idx])
        rows.append({
            "군집 수 K": k,
            "K-means 실루엣(전체)": silhouette_score(
                Z, lab, sample_size=min(n, 20000), random_state=SEED),
            "K-means 실루엣(표본)": silhouette_score(Z[idx], lab[idx]),
            "계층적(Ward) 실루엣(표본)": silhouette_score(Z[idx], hier),
            "최소 군집 비율(%)": np.bincount(lab).min() / n * 100,
        })
    return pd.DataFrame(rows).round(4)


def vif_table(Z):
    """VIF(분산팽창지수)."""
    n = Z.shape[0]
    rows = []
    for j, f in enumerate(FEATURES):
        A = np.column_stack([np.ones(n), np.delete(Z, j, axis=1)])
        coef, *_ = np.linalg.lstsq(A, Z[:, j], rcond=None)
        r2 = 1 - (Z[:, j] - A @ coef).var() / Z[:, j].var()
        rows.append({"변수": KO[f], "VIF": round(float(1 / (1 - r2)), 2)})
    return pd.DataFrame(rows)


def build_profile(sub_X, labels, centers):
    """군집별 인원, 원점수 평균, 강점·약점(Z 중심 기준)."""
    n = len(sub_X)
    rows = []
    for c in range(len(centers)):
        m = labels == c
        zc = centers[c]
        row = {"군집": c + 1, "인원": int(m.sum()), "비율(%)": round(m.sum() / n * 100, 1)}
        row.update({KO[f]: round(float(sub_X[m, j].mean()), 2) for j, f in enumerate(FEATURES)})
        row["강점"] = ",".join(KO[f] for f, z in zip(FEATURES, zc) if z >= STRONG_Z)
        row["약점"] = ",".join(KO[f] for f, z in zip(FEATURES, zc) if z <= -STRONG_Z)
        rows.append(row)
    return pd.DataFrame(rows)


def final_k_for(grade_name, n_groups, args):
    """등급별 최종 K. 3등급은 k_3, 참가등급(또는 단일 집단)은 k_part."""
    if "참가" in grade_name or n_groups == 1:
        return args.k_part
    if grade_name == "3등급":
        return args.k_3
    return args.k_3


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


def plot_pca(plt, pc, labels, centers_pc, expl, grade_name, out_dir):
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
    ax.set_title(f"[{grade_name}] PCA 2차원 군집 분포 (X = 군집 중심)")
    ax.legend(frameon=False, markerscale=2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_dir / f"kmeans_pca_scatter_{grade_name}.png", dpi=150)
    plt.close(fig)


def plot_profile(plt, prof, grade_name, out_dir):
    names = [KO[f] for f in FEATURES]
    k = len(prof)
    w = 0.8 / k
    x = np.arange(len(FEATURES))
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, (_, r) in enumerate(prof.iterrows()):
        vals = [r[n] for n in names]
        ax.bar(x + (i - (k - 1) / 2) * w, vals, w, color=COLORS[i % len(COLORS)],
               label=f"군집 {int(r['군집'])} (n={int(r['인원'])})")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 100)
    ax.set_ylabel("평균 백분위 점수 (높을수록 양호)")
    ax.set_title(f"[{grade_name}] 군집별 체력 프로필")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / f"kmeans_profile_{grade_name}.png", dpi=150)
    plt.close(fig)


# ---------- 등급별 분석 ----------
def analyze_grade(g_name, g_df, k_main, assign_ks, out_dir, plt):
    """한 등급 집단에 대해 실루엣 비교, 군집화, 프로필, PCA, 처방 종목을 산출하고
    할당 결과 DataFrame을 반환한다."""
    sub_X = g_df[FEATURES].to_numpy(float)
    n_sub = len(sub_X)
    sub_Z = StandardScaler().fit_transform(sub_X)

    # K=3~7 비교
    comp = compare_k(sub_Z)
    comp.to_csv(out_dir / f"kmeans_k_comparison_{g_name}.csv", index=False, encoding="utf-8-sig")
    print("=" * 65)
    print(f" [3] [{g_name}] 군집 개수(K=3~7) 실루엣 계수 및 비율 비교")
    print("=" * 65)
    print(comp.to_string(index=False))
    print("=" * 65 + "\n")

    # 최종 K 군집화
    km = _kmeans(k_main).fit(sub_Z)
    labels = km.labels_
    print(f"[{g_name}] 최종 K={k_main}, 군집 인원: "
          + ", ".join(f"{c + 1}군집={int((labels == c).sum())}명" for c in range(k_main)) + "\n")

    prof = build_profile(sub_X, labels, km.cluster_centers_)
    prof.to_csv(out_dir / f"kmeans_clusters_{g_name}.csv", index=False, encoding="utf-8-sig")

    # PCA
    pca = PCA(n_components=len(FEATURES), random_state=SEED).fit(sub_Z)
    pc = pca.transform(sub_Z)[:, :2]
    centers_pc = pca.transform(km.cluster_centers_)[:, :2]
    expl = pca.explained_variance_ratio_[:2] * 100
    pca_rows = []
    for i in range(2):
        r = {"PC": f"PC{i + 1}", "설명력(%)": round(float(expl[i]), 2),
             "누적(%)": round(float(expl[: i + 1].sum()), 2)}
        r.update({KO[f]: round(float(v), 3) for f, v in zip(FEATURES, pca.components_[i])})
        pca_rows.append(r)
    pd.DataFrame(pca_rows).to_csv(out_dir / f"kmeans_pca_{g_name}.csv",
                                  index=False, encoding="utf-8-sig")

    # 군집별 상위 처방 종목
    items_list = g_df["ITEMS"].tolist()
    overall = count_items(items_list)
    presc_rows = []
    for c in range(k_main):
        members = [items_list[i] for i in np.where(labels == c)[0]]
        cnt = count_items(members)
        for rank, (item, v) in enumerate(cnt.most_common(TOP_N_PRESC), 1):
            presc_rows.append({"군집": c + 1, "순위": rank, "종목": item,
                               "군집 내 비율(%)": round(v / len(members) * 100, 1),
                               "전체 비율(%)": round(overall[item] / n_sub * 100, 1)})
    pd.DataFrame(presc_rows).to_csv(out_dir / f"kmeans_cluster_prescription_{g_name}.csv",
                                    index=False, encoding="utf-8-sig")

    if plt is not None:
        plot_pca(plt, pc, labels, centers_pc, expl, g_name, out_dir)
        plot_profile(plt, prof, g_name, out_dir)

    # 개인별 할당 결과 (주 K + 추가 K)
    assign = pd.DataFrame({
        ID_COL: g_df[ID_COL].to_numpy(),
        "GRADE": g_name,
        "CLUSTER": labels + 1,
        "GROUP": [f"{g_name}-C{x}" for x in labels + 1],
    })
    for k in assign_ks:
        if k == k_main:
            lab = labels
        else:
            lab = _kmeans(k).fit(sub_Z).labels_
        assign[f"GROUP_K{k}"] = [f"{g_name}-C{x}" for x in lab + 1]
        assign[f"CLUSTER_K{k}"] = lab + 1
    return assign


# ---------- 메인 ----------
def parse_args():
    ap = argparse.ArgumentParser(description="K-means 체력유형 분석 (등급별 분리)")
    ap.add_argument("--in_path", default=str(IN_PATH), help="processed_select_personal.csv")
    ap.add_argument("--out_dir", default=str(OUT_DIR), help="결과 상위 폴더 (하위에 kmeans_paper 생성)")
    ap.add_argument("--k_3", type=int, default=DEFAULT_K["3등급"], help="3등급 최종 K (기본 3)")
    ap.add_argument("--k_part", type=int, default=DEFAULT_K["참가등급"],
                    help="참가등급 최종 K (기본 4)")
    ap.add_argument("--assign_ks", type=int, nargs="*", default=[],
                    help="할당 파일에 추가로 저장할 K 목록 (예: --assign_ks 4 6)")
    ap.add_argument("--no_plot", action="store_true", help="그림 생성 생략")
    return ap.parse_args()


def main():
    args = parse_args()
    out_dir = Path(args.out_dir) / "kmeans_paper"
    out_dir.mkdir(parents=True, exist_ok=True)

    df_all = load_data(args.in_path)
    df_target = filter_target_grades(df_all)

    # 1. 사전 변수 분석: 상관관계, VIF
    X = df_target[FEATURES].to_numpy(float)
    corr = pd.DataFrame(X, columns=[KO[f] for f in FEATURES]).corr().round(2)
    corr = corr.rename_axis("변수").reset_index()
    vif = vif_table(StandardScaler().fit_transform(X))

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

    # 2. 등급별 집단 구성
    grade_groups = {}
    if "GRADE" in df_target.columns:
        grades = df_target["GRADE"].astype(str).str.strip()
        for g in grades.unique():
            sub = df_target[grades == g].copy()
            if len(sub) >= MIN_GRADE_N:
                grade_groups[g] = sub
            else:
                print(f"[건너뜀] {g}: {len(sub)}명으로 최소 인원({MIN_GRADE_N}명) 미만")
    if not grade_groups:
        grade_groups["참가등급"] = df_target

    plt = None if args.no_plot else _plt()
    assignments = []
    for g_name, g_df in grade_groups.items():
        if len(g_df) < max(K_COMPARE):
            print(f"[건너뜀] {g_name}: 인원이 K 비교 범위({max(K_COMPARE)})보다 적습니다.")
            continue
        k_main = final_k_for(g_name, len(grade_groups), args)
        assign_ks = sorted(set(args.assign_ks))
        assignments.append(analyze_grade(g_name, g_df, k_main, assign_ks, out_dir, plt))

    # 3. 할당 결과 저장
    if assignments:
        pd.concat(assignments, ignore_index=True).to_csv(
            out_dir / "kmeans_assignments.csv", index=False, encoding="utf-8-sig")
        print("[할당 열] GROUP: 주 K 집단(등급-C번호), CLUSTER: 주 K 번호"
              + ("".join(f", GROUP_K{k}/CLUSTER_K{k}" for k in sorted(set(args.assign_ks)))
                 if args.assign_ks else ""))
    print(f"\n[저장 완료] 분석 결과가 [{out_dir}] 폴더에 저장되었습니다.")


if __name__ == "__main__":
    main()