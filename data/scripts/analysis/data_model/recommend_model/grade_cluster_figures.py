"""등급(1~4)별로 편차 기반 K-means(k=4) 유형을 만들고, 분리도 그림의 (a)(c)(d) 패널을 뽑습니다. 이 파일 하나로 실행됩니다.

- (a) 편차 공간 PCA 산점도와 군집 중심
- (c) 군집별 종목 평균 편차 히트맵 (+강점 / −약점, 색 범위는 등급 간 같게 고정)
- (d) 군집별 체력수준(AVG_PERCENTILE) 분포와 eta²

입력: 등급별 CSV (기본 이름 grade{grade}_4items.csv, percentile_grade 단계의 출력).
      종목별 백분위 4개(*_PERCENTILE)가 있으면 되고, CLUSTER 컬럼은 쓰지 않습니다. 등급마다 k로 새로 군집화합니다.
      AVG_PERCENTILE(없으면 4종목 평균), BMI·체지방률 백분위, AGE, MVM_PRSCRPTN_CN(운동처방)이 있으면 표에 같이 씁니다.
군집: 평균 대비 편차 D(=종목 백분위 − 4종목 평균)로 K-means를 합니다(쌍별 편차와 같은 결과).
      k가 4이면 군집 번호를 강점 종목 순서(근력, 근지구력, 심폐지구력, 유연성)로 다시 붙여, 등급이 달라도 같은 번호가 같은 유형이고 색도 같습니다.

출력(output_dir):
- grade{등급}_k{k}_acd.png: 등급마다 (a)(c)(d) 한 줄 그림
- all_grades_k{k}_acd.png: 모든 등급을 세로로 쌓은 그림
- all_grades_cluster_metrics.csv, all_grades_overall_metrics.csv: 등급별 군집 표와 전체 분리도 지표

사용: 아래 "실행 설정"의 INPUT_DIR, OUTPUT_DIR, FILE_PATTERN, K를 고친 뒤 python grade_cluster_figures.py
"""

import re
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_samples

# ---- 실행 설정: 여기만 고치면 됩니다 ----
INPUT_DIR = Path("data/scripts/analysis/data_model/percentile_grade")  # 등급별 CSV가 있는 폴더
OUTPUT_DIR = Path("data/scripts/analysis/data_model/grade_cluster_figures")  # 그림·표를 저장할 폴더
FILE_PATTERN = "grade{grade}_4items.csv"  # 등급별 파일 이름 형식 ({grade}에 1~4가 들어갑니다)
K = 4  # 군집 수
GRADES = (1, 2, 3, 4)
# ----------------------------------------

CLUSTER = "CLUSTER"
EXERCISES = {"STRENGTH": "근력", "ENDURANCE": "근지구력", "CARDIO": "심폐지구력", "FLEXIBILITY": "유연성"}
BODY = {"BMI_PERCENTILE": "BMI", "BODY_FAT_PERCENTILE": "체지방률"}
PRESCRIPTION = "MVM_PRSCRPTN_CN"
LABEL_THRESHOLD = 5.0  # 유형 이름을 붙일 때 강점·약점으로 보는 평균 편차(백분위 포인트)
MIN_HEATMAP_LIMIT = 10.0  # 히트맵 색 범위의 최소값(±)
SILHOUETTE_SAMPLE = 8000  # 실루엣·산점도에 쓰는 최대 표본 수
KMEANS_N_INIT = 10
RANDOM_STATE = 42
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#eda100", "#e34948"]


def setup_font() -> None:
    """설치된 한글 글꼴을 찾아 씁니다."""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"):
        if name in installed:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def pct_col(exercise: str) -> str:
    """종목의 백분위 컬럼 이름입니다."""
    return f"{exercise}_PERCENTILE"


def dev_col(exercise: str) -> str:
    """종목의 평균 대비 편차 컬럼 이름입니다."""
    return f"{exercise}_DEV"


def load(path: Path) -> pd.DataFrame:
    """등급별 CSV를 읽고 4종목 평균 백분위(AVG4)와 종목별 평균 대비 편차(*_DEV)를 붙입니다.

    Raises:
        ValueError: 종목별 백분위 컬럼이 없을 때
    """
    df = pd.read_csv(path, encoding="utf-8-sig")
    need = [pct_col(e) for e in EXERCISES]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}에 필요한 컬럼이 없습니다: {', '.join(missing)}")
    df = df.dropna(subset=need).reset_index(drop=True)
    df["AVG4"] = df[need].mean(axis=1)
    for e in EXERCISES:
        df[dev_col(e)] = df[pct_col(e)] - df["AVG4"]
    return df


def fit_clusters(df: pd.DataFrame, k: int) -> pd.DataFrame:
    """평균 대비 편차 D로 K-means(k)를 하고, 강점 종목 순서에 맞게 군집 번호를 다시 붙입니다.

    k가 종목 수(4)와 같으면 군집과 종목을 1:1로 짝지어(헝가리안 배정) 번호를 정합니다.
    다르면 군집의 최대 편차 종목 순서, 같은 종목이면 편차가 큰 순서로 번호를 붙입니다.
    """
    dev_cols = [dev_col(e) for e in EXERCISES]
    raw = KMeans(k, n_init=KMEANS_N_INIT, random_state=RANDOM_STATE).fit_predict(df[dev_cols])
    means = df[dev_cols].groupby(raw).mean().to_numpy()  # k x 종목 수
    if k == len(EXERCISES):
        rows, cols = linear_sum_assignment(-means)
        mapping = {int(r): int(c) for r, c in zip(rows, cols)}
    else:
        order = sorted(range(k), key=lambda c: (means[c].argmax(), -means[c].max()))
        mapping = {c: i for i, c in enumerate(order)}
    return df.assign(**{CLUSTER: pd.Series(raw, index=df.index).map(mapping).astype(int)})


def eta_squared(values: pd.Series, labels: pd.Series) -> float:
    """군집 간 분산이 전체 분산에서 차지하는 비율입니다(0~1, 클수록 군집이 값을 잘 구분)."""
    grand = values.mean()
    total = ((values - grand) ** 2).sum()
    between = sum(len(v) * (v.mean() - grand) ** 2 for _, v in values.groupby(labels))
    return float(between / total) if total > 0 else float("nan")


def cluster_names(df: pd.DataFrame) -> dict[int, str]:
    """군집별 평균 편차가 가장 큰 강점 종목과 가장 작은 약점 종목으로 '유형 0: 근력↑ 유연성↓' 이름을 붙입니다."""
    names = {}
    for c, g in df.groupby(CLUSTER):
        mean_dev = {EXERCISES[e]: g[dev_col(e)].mean() for e in EXERCISES}
        best, worst = max(mean_dev, key=mean_dev.get), min(mean_dev, key=mean_dev.get)
        parts = []
        if mean_dev[best] >= LABEL_THRESHOLD:
            parts.append(f"{best}↑")
        if mean_dev[worst] <= -LABEL_THRESHOLD:
            parts.append(f"{worst}↓")
        names[c] = f"유형 {c}: " + (" ".join(parts) if parts else "균형형")
    return names


def cluster_colors(clusters) -> dict:
    """군집 번호마다 고정 색을 줍니다."""
    return {c: COLORS[i % len(COLORS)] for i, c in enumerate(sorted(clusters))}


def top_prescriptions(series: pd.Series, n: int = 3) -> tuple[list[str], float]:
    """사람 비율이 높은 처방 종목 상위 n개와 달리기류 보유 비율(%)을 돌려줍니다."""
    sets = [{re.sub(r"\s+", "", t) for t in str(x).split(",") if t.strip()} for x in series.dropna()]
    sets = [s for s in sets if s]
    if not sets:
        return [], float("nan")
    counts = Counter(t for s in sets for t in s)
    top = [f"{t}({c / len(sets) * 100:.0f}%)" for t, c in counts.most_common(n)]
    running = np.mean([any("달리기" in t for t in s) for s in sets]) * 100
    return top, float(running)


def compute_metrics(df: pd.DataFrame, names: dict[int, str], level_col: str):
    """군집별 표, 전체 분리도 지표, 산점도·실루엣에 쓰는 표본 위치를 계산합니다."""
    dev_cols = [dev_col(e) for e in EXERCISES]
    x, labels = df[dev_cols].to_numpy(), df[CLUSTER].to_numpy()

    rng = np.random.default_rng(RANDOM_STATE)
    sample = np.sort(rng.choice(len(df), size=min(SILHOUETTE_SAMPLE, len(df)), replace=False))
    sil = silhouette_samples(x[sample], labels[sample])

    overall = {
        "인원": len(df),
        "군집 수": df[CLUSTER].nunique(),
        f"실루엣(표본 {len(sample):,}명)": sil.mean(),
        "Calinski-Harabasz": calinski_harabasz_score(x, labels),
        "Davies-Bouldin(낮을수록 좋음)": davies_bouldin_score(x, labels),
        f"eta² 체력수준({level_col})": eta_squared(df[level_col], df[CLUSTER]),
    }
    for e, label in EXERCISES.items():
        overall[f"eta² {label} 편차"] = eta_squared(df[dev_col(e)], df[CLUSTER])
    for e, label in EXERCISES.items():
        overall[f"eta² {label} 백분위"] = eta_squared(df[pct_col(e)], df[CLUSTER])

    rows = []
    for c, g in df.groupby(CLUSTER):
        row = {"군집": c, "이름": names[c], "인원": len(g), "비율(%)": round(len(g) / len(df) * 100, 1),
               "평균 실루엣": round(float(sil[labels[sample] == c].mean()), 3),
               f"{level_col} 평균": round(g[level_col].mean(), 1), f"{level_col} 표준편차": round(g[level_col].std(), 1)}
        for e, label in EXERCISES.items():
            row[f"{label} 편차"] = round(g[dev_col(e)].mean(), 1)
        for e, label in EXERCISES.items():
            row[f"{label} 백분위"] = round(g[pct_col(e)].mean(), 1)
        for col, label in BODY.items():
            if col in g:
                row[f"{label} 백분위"] = round(g[col].mean(), 1)
        if "AGE" in g:
            row["평균 나이"] = round(g["AGE"].mean(), 1)
        if PRESCRIPTION in g:
            top, running = top_prescriptions(g[PRESCRIPTION])
            row["처방 상위3"] = ", ".join(top)
            row["달리기류 처방(%)"] = round(running, 1)
        rows.append(row)
    return pd.DataFrame(rows), pd.Series(overall), sample


def plot_scatter(ax, df, names, color, sample, prefix: str = "") -> None:
    """(a) 편차 공간 PCA 산점도와 군집 중심."""
    dev_cols = [dev_col(e) for e in EXERCISES]
    labels = df[CLUSTER].to_numpy()
    pca = PCA(n_components=2, random_state=RANDOM_STATE).fit(df[dev_cols])
    xy = pca.transform(df[dev_cols])
    for c in sorted(df[CLUSTER].unique()):
        m = labels[sample] == c
        ax.scatter(xy[sample][m, 0], xy[sample][m, 1], s=6, alpha=0.35, color=color[c], label=names[c])
        ax.scatter(*xy[labels == c].mean(axis=0), s=140, color=color[c], edgecolor="black", linewidth=1.5, zorder=3)
    ratio = pca.explained_variance_ratio_ * 100
    ax.set(xlabel=f"PC1 ({ratio[0]:.0f}%)", ylabel=f"PC2 ({ratio[1]:.0f}%)",
           title=f"{prefix}(a) 편차 공간의 군집 분포 (PCA, 두 축 합 {ratio.sum():.0f}%)")
    ax.legend(markerscale=3, fontsize=9, loc="best")


def plot_deviation_heatmap(ax, df, names, limit: float, prefix: str = "") -> None:
    """(c) 군집별 종목 평균 편차 히트맵. 색 범위는 ±limit로 고정합니다(등급 간 비교용)."""
    clusters = sorted(df[CLUSTER].unique())
    matrix = np.array([[df.loc[df[CLUSTER] == c, dev_col(e)].mean() for e in EXERCISES] for c in clusters])
    im = ax.imshow(matrix, cmap="coolwarm", vmin=-limit, vmax=limit, aspect="auto")
    ax.set_xticks(range(len(EXERCISES)), list(EXERCISES.values()))
    ax.set_yticks(range(len(clusters)), [names[c] for c in clusters])
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, f"{matrix[i, j]:+.1f}", ha="center", va="center", fontsize=12,
                    color="white" if abs(matrix[i, j]) > limit * 0.6 else "black")
    ax.figure.colorbar(im, ax=ax, shrink=0.8, label="평균 백분위 대비 편차(포인트)")
    ax.set_title(f"{prefix}(c) 군집별 종목 편차 (+강점 / −약점)")


def plot_level_box(ax, df, names, color, level_col, overall, prefix: str = "") -> None:
    """(d) 군집별 체력수준 분포 박스플롯."""
    clusters = sorted(df[CLUSTER].unique())
    box = ax.boxplot([df.loc[df[CLUSTER] == c, level_col] for c in clusters], patch_artist=True,
                     showfliers=False, medianprops={"color": "black"})
    for patch, c in zip(box["boxes"], clusters):
        patch.set(facecolor=color[c], alpha=0.8)
    ax.set_xticks(range(1, len(clusters) + 1), [f"유형 {c}" for c in clusters])
    eta_level = overall[f"eta² 체력수준({level_col})"]
    eta_dev = np.nanmean([overall[f"eta² {label} 편차"] for label in EXERCISES.values()])
    ax.set(ylabel=level_col, title=f"{prefix}(d) 군집별 체력수준 분포 (수준 eta² {eta_level:.3f} vs 편차 eta² 평균 {eta_dev:.3f})")


def draw_acd(axes, df, names, level_col, overall, sample, limit: float, prefix: str = "") -> None:
    """한 등급의 (a)(c)(d) 패널을 axes 세 칸에 그립니다."""
    color = cluster_colors(df[CLUSTER].unique())
    plot_scatter(axes[0], df, names, color, sample, prefix)
    plot_deviation_heatmap(axes[1], df, names, limit, prefix)
    plot_level_box(axes[2], df, names, color, level_col, overall, prefix)


def run(input_dir: Path, output_dir: Path, k: int, pattern: str) -> None:
    """등급별 파일을 찾아 k개 유형으로 나누고, 등급별 그림·전체 그림·지표 표를 output_dir에 저장합니다.

    Raises:
        FileNotFoundError: 어떤 등급 파일도 찾지 못했을 때
    """
    setup_font()
    output_dir.mkdir(parents=True, exist_ok=True)

    fitted = {}
    for grade in GRADES:
        path = input_dir / pattern.format(grade=grade)
        if not path.exists():
            print(f"{grade}등급: {path.name} 없음, 건너뜀")
            continue
        fitted[grade] = fit_clusters(load(path), k)
    if not fitted:
        raise FileNotFoundError(f"{input_dir}에서 {pattern} 형식의 파일을 찾지 못했습니다.")

    dev_cols = [dev_col(e) for e in EXERCISES]
    limit = max(MIN_HEATMAP_LIMIT, *(df.groupby(CLUSTER)[dev_cols].mean().abs().to_numpy().max() for df in fitted.values()))

    results, tables, overalls = {}, [], {}
    for grade, df in fitted.items():
        level_col = "AVG_PERCENTILE" if "AVG_PERCENTILE" in df else "AVG4"
        names = cluster_names(df)
        table, overall, sample = compute_metrics(df, names, level_col)
        results[grade] = (df, names, level_col, overall, sample)
        tables.append(table.assign(등급=f"{grade}등급"))
        overalls[f"{grade}등급"] = overall

        fig, axes = plt.subplots(1, 3, figsize=(21, 6.5))
        draw_acd(axes, df, names, level_col, overall, sample, limit)
        fig.suptitle(f"{grade}등급 (n={len(df):,}) 편차 기반 K-means k={k}", fontsize=16)
        fig.tight_layout()
        fig.savefig(output_dir / f"grade{grade}_k{k}_acd.png", dpi=200, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(len(results), 3, figsize=(21, 6.5 * len(results)), squeeze=False)
    for row, (grade, (df, names, level_col, overall, sample)) in zip(axes, results.items()):
        draw_acd(row, df, names, level_col, overall, sample, limit, prefix=f"[{grade}등급] ")
    fig.suptitle(f"등급별 편차 기반 K-means k={k} 유형", fontsize=18)
    fig.tight_layout()
    fig.savefig(output_dir / f"all_grades_k{k}_acd.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    metrics = pd.concat(tables, ignore_index=True)
    metrics = metrics[["등급", *[c for c in metrics.columns if c != "등급"]]]
    metrics.to_csv(output_dir / "all_grades_cluster_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(overalls).T.round(4).rename_axis("등급").to_csv(
        output_dir / "all_grades_overall_metrics.csv", encoding="utf-8-sig")

    pd.set_option("display.width", 200, "display.max_columns", 20)
    print(pd.DataFrame(overalls).T.round(3).iloc[:, :5].to_string())
    print(f"저장: {output_dir}")


def main() -> None:
    """코드 위쪽의 실행 설정(INPUT_DIR, OUTPUT_DIR, FILE_PATTERN, K)으로 실행합니다."""
    run(INPUT_DIR, OUTPUT_DIR, K, FILE_PATTERN)


if __name__ == "__main__":
    main()