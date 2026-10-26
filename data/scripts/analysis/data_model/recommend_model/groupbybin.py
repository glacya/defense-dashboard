"""운동처방 빈도·처방률 분석 및 집단 간 연관성 검정 (3개 집단 모드, 집단별 결론 및 최종 보고서 포함).

집단 모드
  cross    : 6항목 상/하 교차 그룹 (recommend_cross.py 방식, 최대 64개)
  kmeans   : K-means 군집 할당 파일 (kmeans4_6.py 또는 recommend_k_means.py 출력)
  overall  : 전체 집단 1개 (분할 없음, 처방률 기준선만 산출, 연관성 검정 미수행)

산출물
  freq_analysis/final_report.md        : 최종 보고서 (모드별 결론, 집단별 결론, 강한 후보, 종합 결론)
  freq_analysis/<모드>/report.md       : 모드별 상세 보고서 (집단별 결론 표 포함)
  freq_analysis/<모드>/candidates.csv  : 후보 칸 표
  freq_analysis/comparison/            : 세 모드 비교 표·그래프, candidates_all.csv
  freq_analysis/graphs/                : 전체 공통 그래프

판정 기준
  - 통계적 유의: Holm 보정 p < ALPHA
  - 효과 있음: 통계적 유의 + Cramér's V >= EFFECT_MIN   → "연관 확인"
  - 효과 미약: 통계적 유의 + Cramér's V < EFFECT_MIN    → "통계적으로만 유의"
  - 과/과소처방: 조정잔차 >= RES_CUT 또는 <= -RES_CUT
  - 배수: 집단 처방률 / 전체 처방률 (예: 2.0 = 전체의 2배)
  - 신뢰구간: 집단 처방률의 Wilson 95% 구간을 전체 처방률로 나눈 배수 구간

후보 칸 스크리닝 (배수 기준)
  1) 집단 인원 >= SCREEN_MIN_N
  2) 전체 처방률 >= SCREEN_MIN_BASE (%)
  3) 배수 >= SCREEN_MIN_RATIO 또는 배수 <= 1 / SCREEN_MIN_RATIO
  4) 같은 종목에서 같은 방향 기준을 넘는 집단이 SCREEN_MIN_CONSIST개 이상
  5) 배수의 95% 신뢰구간이 1을 포함하지 않음
  결합 등급: 강한 후보 = 종목 검정 "효과 있음" + 칸 잔차 과처방/과소처방, 그 외는 참고 후보

주의
  후보 칸은 가설을 고르기 위한 스크리닝입니다. 최종 결론은 종목 단위 Holm 보정 결과(group_item_test.csv)를
  우선하세요. 배수의 기준값(전체 처방률)에는 해당 집단도 포함되어 있습니다.

사용 방법
  1. 아래 "직접 설정" 블록의 KMEANS_FILE, KMEANS_COL을 확인합니다.
  2. python groupbybin.py 로 실행합니다.
  K=4와 K=6을 모두 보려면 KMEANS_COL을 바꿔 두 번 실행하세요.
  그래프를 건너뛰려면 python groupbybin.py --no_plot
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from data.scripts.analysis.data_model.recommend_model.recommend_common import (
    FEATURES, ID_COL, IN_PATH, OUT_DIR, count_items, load_data,
)

KO = dict(zip(FEATURES, ["근력", "근지구력", "심폐지구력", "유연성", "BMI", "체지방률"]))
MODES = ("cross", "kmeans", "overall")
MODE_LABEL = {"cross": "교차집단", "kmeans": "K-means 집단", "overall": "전체 집단"}
OVERALL_LABEL = MODE_LABEL["overall"]
CROSS_THRESHOLD = 50
BIN_EDGES = [-0.01, 20, 40, 60, 80, 100]
BIN_LABELS = ["0~20", "20~40", "40~60", "60~80", "80~100"]
ALPHA = 0.05
MIN_EXPECTED = 5
MIN_ITEM_COUNT = 30
MIN_GROUP_N = 30
EFFECT_MIN = 0.1
RES_CUT = 1.96
TOP_REPORT = 10
TOP_GROUP_ITEMS = 3
UNMATCHED = "미분류"

# 후보 칸 스크리닝 기준
SCREEN_MIN_N = 30
SCREEN_MIN_BASE = 5.0
SCREEN_MIN_RATIO = 1.5
SCREEN_MIN_CONSIST = 2
SCREEN_TOP_REPORT = 15

# 그래프·비교 설정
PLOT_TOP_ITEMS = 20
PLOT_MAX_GROUPS = 8
KOREAN_FONTS = (
    "Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR",
    "Noto Sans CJK JP", "Noto Sans CJK SC", "Noto Sans KR"
)
COLORS = [
    "#1f4e8c", "#d9822b", "#3a9d6f", "#9b59b6",
    "#c0392b", "#7f8c8d", "#d35400", "#16a085"
]

# ---------- 직접 설정 ----------
KMEANS_FILE = Path(OUT_DIR) / "kmeans_paper" / "kmeans_assignments_K4_K6.csv"
KMEANS_COL = "CLUSTER_K4"
# ------------------------------

OVERALL_COLS = ["순위", "종목", "처방 빈도", "처방률(%)", "처방 건수 비율(%)"]
GROUP_LONG_COLS = [
    "집단", "집단 N", "종목", "처방 빈도", "처방률(%)",
    "전체 처방률(%)", "차이(%p)", "배수"
]
G_TEST_COLS = [
    "종목", "처방 빈도", "chi2", "p", "Cramér V", "희소셀 비율(%)",
    "과처방 집단", "과소처방 집단"
]
G_RESID_COLS = ["집단", "종목", "처방률(%)", "전체 처방률(%)", "조정잔차", "방향"]
B_TEST_COLS = [
    "구간 변수", "종목", "처방 빈도", "chi2", "p", "Cramér V", "희소셀 비율(%)",
    "최고 처방률 구간", "최고 처방률(%)", "최저 처방률 구간", "최저 처방률(%)"
]
COMPARE_COLS = [
    "모드", "집단", "집단 N", "종목", "처방률(%)",
    "전체 처방률(%)", "차이(%p)", "배수", "라벨"
]
CAND_COLS = [
    "모드", "후보 등급", "집단", "집단 N", "종목", "처방률(%)",
    "전체 처방률(%)", "배수", "배수_low", "배수_high",
    "같은방향집단수", "조정잔차", "방향", "p_holm", "Cramér V", "판정"
]
GROUP_SUM_COLS = [
    "집단", "N", "과처방 종목(배수)", "과소처방 종목(배수)",
    "과처방 칸", "과소처방 칸", "후보(강한/참고)", "결론"
]


# ---------- 그래프 ----------
def _plt():
    """matplotlib 준비 (한글 폰트 자동 선택). 없으면 None 반환."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except ImportError:
        print("[경고] matplotlib가 없어 그래프를 건너뜁니다. (pip install matplotlib)")
        return None

    avail = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in avail:
            matplotlib.rcParams["font.family"] = name
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
    return plt


def heatmap(
    plt, data, title, path, cbar_label="처방률(%)", cmap="YlGnBu",
    symmetric=False, fmt="{:.1f}", center=None
):
    """행=종목, 열=집단/구간 히트맵. center가 있으면 해당 값을 중심으로 색상을 정규화."""
    if data.empty or data.shape[1] == 0:
        return

    vals = data.to_numpy(float)
    finite = vals[np.isfinite(vals)]
    if finite.size == 0:
        return

    nrow, ncol = vals.shape
    fig_w = min(max(8, 0.6 * ncol + 3), 30)
    fig_h = min(max(5, 0.35 * nrow + 2), 30)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    if center is not None:
        from matplotlib.colors import TwoSlopeNorm

        vmin = min(float(np.min(finite)), float(center))
        vmax = max(float(np.max(finite)), float(center))
        if vmin == vmax:
            vmin, vmax = float(center) - 0.01, float(center) + 0.01
        norm = TwoSlopeNorm(vmin=vmin, vcenter=float(center), vmax=vmax)
        im = ax.imshow(vals, aspect="auto", cmap=cmap, norm=norm)
    elif symmetric:
        m = float(np.max(np.abs(finite)))
        if m == 0:
            m = 1.0
        im = ax.imshow(vals, aspect="auto", cmap=cmap, vmin=-m, vmax=m)
    else:
        im = ax.imshow(vals, aspect="auto", cmap=cmap)

    ax.set_xticks(range(ncol))
    ax.set_xticklabels(
        [str(c) for c in data.columns], rotation=45, ha="right", fontsize=8
    )
    ax.set_yticks(range(nrow))
    ax.set_yticklabels([str(i) for i in data.index], fontsize=8)

    if nrow * ncol <= 300:
        for i in range(nrow):
            for j in range(ncol):
                v = vals[i, j]
                if not np.isfinite(v):
                    continue

                if center is not None:
                    span = max(
                        abs(float(np.max(finite)) - center),
                        abs(float(np.min(finite)) - center),
                        1e-9
                    )
                    dark = abs(v - center) > 0.55 * span
                elif symmetric:
                    vmax_abs = max(float(np.max(np.abs(finite))), 1e-9)
                    dark = abs(v) > 0.6 * vmax_abs
                else:
                    vmax_val = max(float(np.max(finite)), 1e-9)
                    dark = v > 0.6 * vmax_val

                ax.text(
                    j, i, fmt.format(v), ha="center", va="center",
                    fontsize=7, color="white" if dark else "black"
                )

    fig.colorbar(im, ax=ax, label=cbar_label, fraction=0.03, pad=0.02)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def bar_overall(plt, overall, path, top=PLOT_TOP_ITEMS):
    """전체 처방률 상위 종목 가로 막대."""
    t = overall.head(top).iloc[::-1]
    if t.empty:
        return

    fig, ax = plt.subplots(figsize=(8, max(4, 0.35 * len(t) + 1.5)))
    ax.barh(t["종목"].astype(str), t["처방률(%)"], color=COLORS[0])
    for y, v in enumerate(t["처방률(%)"]):
        ax.text(v, y, f" {v:.1f}%", va="center", fontsize=8)

    ax.set_xlabel("처방률(%) (전체 인원 대비)")
    ax.set_title(f"전체 처방률 상위 {len(t)}개 종목")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def bar_group_top_items(plt, res, overall, path, top_items=8, max_groups=PLOT_MAX_GROUPS):
    """상위 종목별 집단 처방률 막대. 전체 처방률은 검은 선으로 표시."""
    gl = res["group_long"]
    if gl.empty:
        return

    items = overall["종목"].head(top_items).tolist()
    sizes = gl.drop_duplicates("집단").set_index("집단")["집단 N"].sort_values(ascending=False)
    groups = sizes.index[:max_groups].tolist()
    if not groups:
        return

    w = 0.8 / len(groups)
    x = np.arange(len(items))
    fig, ax = plt.subplots(figsize=(max(8, 1.3 * len(items) + 3), 5.5))

    for i, g in enumerate(groups):
        sub = gl[gl["집단"] == g].set_index("종목").reindex(items)
        ax.bar(
            x + (i - (len(groups) - 1) / 2) * w,
            sub["처방률(%)"].fillna(0), w,
            color=COLORS[i % len(COLORS)],
            label=f"{g} (n={int(sizes[g]):,})"
        )

    base = overall.set_index("종목").reindex(items)["처방률(%)"]
    ax.scatter(x, base, marker="_", s=600, color="black",
               linewidths=2, label="전체", zorder=5)
    ax.set_xticks(x)
    ax.set_xticklabels(items, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("처방률(%)")
    note = "" if len(sizes) <= max_groups else f" (인원 많은 {max_groups}개 집단만 표시)"
    ax.set_title(f"상위 종목의 집단별 처방률{note}")
    ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_group_heatmaps(plt, res, order, out_graph):
    """집단 x 종목 처방률 히트맵과 전체 대비 차이 히트맵."""
    gl = res["group_long"]
    if gl.empty:
        return

    top = order[:PLOT_TOP_ITEMS]
    rate = res["wide"].reindex(top)
    diff = gl.pivot(index="종목", columns="집단", values="차이(%p)").reindex(top)

    heatmap(
        plt, rate, "집단별 처방률 히트맵 (상위 종목)",
        out_graph / "group_rate_heatmap.png",
        cbar_label="처방률(%)", cmap="YlGnBu"
    )
    heatmap(
        plt, diff, "전체 처방률 대비 차이 (%p, 빨강=높음 / 파랑=낮음)",
        out_graph / "group_diff_heatmap.png",
        cbar_label="차이(%p)", cmap="RdBu_r", symmetric=True, fmt="{:+.1f}"
    )


def plot_bin_heatmaps(plt, bin_tables, out_graph):
    """체력 변수별 구간 처방률 히트맵."""
    for name, t in bin_tables.items():
        if t.empty:
            continue
        data = t.head(PLOT_TOP_ITEMS).set_index("종목")[BIN_LABELS]
        heatmap(
            plt, data, f"[{name}] 구간별 처방률 (구간 간 차이 상위 종목)",
            out_graph / f"bin_rate_{name}.png",
            cbar_label="처방률(%)", cmap="YlOrRd"
        )


# ---------- 집단 이름 ----------
def pretty_group(mode, g):
    """집단 라벨을 사람이 읽을 수 있는 이름으로 바꾼다."""
    g = str(g)
    if mode == "cross":
        names = [KO[f] for f, b in zip(FEATURES, g) if b == "1"]
        return ("·".join(names) + " 상") if names else "전 항목 하위"
    if mode == "kmeans":
        return f"군집 {g}" if g.isdigit() else g
    return g


# ---------- 후보 칸 스크리닝 ----------
def wilson_ci(k, n, z=1.96):
    """Wilson 신뢰구간 (처방 빈도 k, 인원 n 입력; 반환은 %)."""
    k = np.asarray(k, float)
    n = np.asarray(n, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = k / n
        d = 1 + z * z / n
        c = p + z * z / (2 * n)
        h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        lo = (c - h) / d * 100
        hi = (c + h) / d * 100
    return lo, hi


def screen_candidates(mode, res):
    """집단-종목 칸을 배수 기준으로 스크리닝한다."""
    gl = res["group_long"]
    if gl.empty or len(res["levels"]) < 2:
        return pd.DataFrame(columns=CAND_COLS)

    df = gl.copy()
    base = df["전체 처방률(%)"].to_numpy(float)
    rate_lo, rate_hi = wilson_ci(df["처방 빈도"], df["집단 N"])

    with np.errstate(divide="ignore", invalid="ignore"):
        df["배수_low"] = rate_lo / base
        df["배수_high"] = rate_hi / base

    up = (df["배수"] >= SCREEN_MIN_RATIO).to_numpy()
    down = (df["배수"] <= 1 / SCREEN_MIN_RATIO).to_numpy()
    sgn = np.where(up, 1, np.where(down, -1, 0))
    df["_s"] = sgn
    cnt_up = df[df["_s"] == 1].groupby("종목").size()
    cnt_dn = df[df["_s"] == -1].groupby("종목").size()

    df["같은방향집단수"] = np.where(
        sgn == 1, df["종목"].map(cnt_up).fillna(0),
        np.where(sgn == -1, df["종목"].map(cnt_dn).fillna(0), 0)
    ).astype(int)

    df = df.merge(
        res["g_resid"][["집단", "종목", "조정잔차", "방향"]],
        on=["집단", "종목"], how="left"
    )

    if len(res["g_test"]):
        df = df.merge(
            res["g_test"][["종목", "p_holm", "Cramér V", "판정"]],
            on="종목", how="left"
        )
    else:
        df["p_holm"], df["Cramér V"], df["판정"] = np.nan, np.nan, "검정 불가"

    ci_excl_1 = (df["배수_low"] > 1) | (df["배수_high"] < 1)
    cond = (
        (df["집단 N"] >= SCREEN_MIN_N)
        & (df["전체 처방률(%)"] >= SCREEN_MIN_BASE)
        & (df["_s"] != 0)
        & (df["같은방향집단수"] >= SCREEN_MIN_CONSIST)
        & ci_excl_1
    )
    cand = df[cond].copy()
    if cand.empty:
        return pd.DataFrame(columns=CAND_COLS)

    strong = (
        (cand["판정"] == "유의·효과 있음")
        & cand["방향"].isin(["과처방", "과소처방"])
    )
    cand["후보 등급"] = np.where(strong, "강한 후보", "참고 후보")
    cand.insert(0, "모드", MODE_LABEL[mode])
    cand = cand.assign(_dev=np.abs(np.log(cand["배수"].astype(float))))
    cand = cand.sort_values(["후보 등급", "_dev"], ascending=[True, False])
    return cand[CAND_COLS].reset_index(drop=True)


# ---------- 결론 생성 ----------
def mode_conclusion(res, g_test):
    if len(res["levels"]) < 2:
        return "기준선 (집단 연관성 판정 불가)"
    n_eff = int((g_test["판정"] == "유의·효과 있음").sum()) if len(g_test) else 0
    n_weak = int((g_test["판정"] == "유의·효과 미약").sum()) if len(g_test) else 0
    if n_eff:
        return f"연관 확인: 효과 있음 {n_eff}개 종목"
    if n_weak:
        return f"통계적으로만 유의 (효과 작음): {n_weak}개 종목"
    return "연관 없음"


def top_bottom_ratio(sub, base_min=SCREEN_MIN_BASE, k=TOP_GROUP_ITEMS):
    s = sub[sub["전체 처방률(%)"] >= base_min].dropna(subset=["배수"])
    up = s[s["배수"] >= 1].sort_values("배수", ascending=False).head(k)
    dn = s[s["배수"] < 1].sort_values("배수", ascending=True).head(k)

    def fmt(d):
        return ", ".join(
            f"{r['종목']}({r['배수']:.2f}배)" for _, r in d.iterrows()
        ) or "-"

    return fmt(up), fmt(dn)


def group_summary(res, cand):
    rows = []
    gl = res["group_long"]
    if gl.empty:
        return pd.DataFrame(columns=GROUP_SUM_COLS)

    for lvl, sub in gl.groupby("집단", sort=False):
        up, dn = top_bottom_ratio(sub)
        r = res["g_resid"][res["g_resid"]["집단"] == lvl] if len(res["g_resid"]) else res["g_resid"]
        n_over = int((r["방향"] == "과처방").sum()) if len(r) else 0
        n_under = int((r["방향"] == "과소처방").sum()) if len(r) else 0
        c = cand[cand["집단"] == lvl] if len(cand) else cand
        n_s = int((c["후보 등급"] == "강한 후보").sum()) if len(c) else 0
        n_w = (len(c) - n_s) if len(c) else 0

        if n_s:
            concl = f"차이 확인: 강한 후보 {n_s}개 (검정 유의 + 칸 잔차 기준 충족)"
        elif n_w:
            concl = f"차이 가능성: 참고 후보 {n_w}개 (검정 기준 미달)"
        else:
            concl = "뚜렷한 차이 없음"

        rows.append({
            "집단": lvl, "N": int(sub["집단 N"].iloc[0]),
            "과처방 종목(배수)": up, "과소처방 종목(배수)": dn,
            "과처방 칸": n_over, "과소처방 칸": n_under,
            "후보(강한/참고)": f"{n_s}/{n_w}", "결론": concl,
        })

    return pd.DataFrame(rows, columns=GROUP_SUM_COLS)
# ---------- 모드 비교 ----------
def build_comparison(results, overall, n_all, max_groups=PLOT_MAX_GROUPS):
    """모드별 비교 표. 집단 배수의 분모는 전체 분석 대상의 처방률이다."""
    ov_rate = overall["처방률(%)"].to_numpy(dtype=float)
    ov = pd.DataFrame({
        "모드": OVERALL_LABEL,
        "집단": "전체",
        "집단 N": n_all,
        "종목": overall["종목"].to_numpy(),
        "처방률(%)": ov_rate,
        "전체 처방률(%)": ov_rate,
        "차이(%p)": 0.0,
        "배수": np.where(ov_rate > 0, 1.0, np.nan),
    })
    parts = [ov]

    overall_rate_map = overall.set_index("종목")["처방률(%)"]

    for mode in ("cross", "kmeans"):
        res = results.get(mode)
        if res is None or res["group_long"].empty:
            continue

        gl = res["group_long"].copy()
        sizes = (
            gl.drop_duplicates("집단")
            .set_index("집단")["집단 N"]
            .sort_values(ascending=False)
        )
        keep = sizes.index[:max_groups]
        sub = gl[gl["집단"].isin(keep)].copy()

        # 전체 데이터의 처방률을 기준으로 배수와 차이를 다시 계산한다.
        sub["전체 처방률(%)"] = sub["종목"].map(overall_rate_map)
        sub["차이(%p)"] = sub["처방률(%)"] - sub["전체 처방률(%)"]

        with np.errstate(divide="ignore", invalid="ignore"):
            sub["배수"] = np.where(
                sub["전체 처방률(%)"] > 0,
                sub["처방률(%)"] / sub["전체 처방률(%)"],
                np.nan,
            )

        sub.insert(0, "모드", MODE_LABEL[mode])
        parts.append(sub)

    comb = pd.concat(parts, ignore_index=True)
    comb["라벨"] = comb["모드"] + " | " + comb["집단"].astype(str)
    return comb[COMPARE_COLS]


def dot_compare(plt, comb, overall, path, top=PLOT_TOP_ITEMS):
    """전체 처방률 대비 배수 점그래프. 1.0배가 기준선이다."""
    items = overall["종목"].head(top).tolist()
    sub = comb[
        comb["종목"].isin(items) & (comb["모드"] != OVERALL_LABEL)
    ].copy()

    sub = sub[np.isfinite(pd.to_numeric(sub["배수"], errors="coerce"))]
    if sub.empty:
        return

    mode_key = {v: k for k, v in MODE_LABEL.items()}
    sub["표시"] = [
        f"[{m}] {pretty_group(mode_key.get(m, m), g)} (n={int(n):,})"
        for m, g, n in zip(sub["모드"], sub["집단"], sub["집단 N"])
    ]

    ypos = {it: i for i, it in enumerate(items[::-1])}
    labels = list(dict.fromkeys(sub["표시"]))
    n_g = len(labels)
    cmap = plt.get_cmap("tab20")
    spread = min(0.7, 0.07 * n_g)

    fig, ax = plt.subplots(figsize=(11, max(6, 0.45 * len(items) + 2.5)))

    for k, lab in enumerate(labels):
        d = sub[sub["표시"] == lab]
        off = (k - (n_g - 1) / 2) * (spread / max(n_g, 1))
        ax.scatter(
            d["배수"],
            d["종목"].map(ypos) + off,
            s=32,
            alpha=0.85,
            color=cmap(k % 20),
            label=lab,
            zorder=3,
        )

    ov = overall[overall["종목"].isin(items)].copy()
    ax.scatter(
        np.ones(len(ov)),
        ov["종목"].map(ypos),
        marker="D",
        s=60,
        color="black",
        label=f"{OVERALL_LABEL} (1.0배)",
        zorder=5,
    )
    ax.axvline(
        1.0, color="black", linestyle="--", linewidth=1.2, alpha=0.7, zorder=2
    )

    ax.set_yticks(list(ypos.values()))
    ax.set_yticklabels(list(ypos.keys()), fontsize=9)

    max_ratio = float(sub["배수"].max()) if len(sub) else 1.0
    ax.set_xlim(left=0, right=max(1.2, max_ratio * 1.1))
    ax.set_xlabel("전체 처방률 대비 배수 (집단 처방률 ÷ 전체 처방률)")
    ax.set_title("상위 종목별 집단 처방률 배수 (◆ 및 점선 = 1.0배)")
    ax.grid(axis="x", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1))
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def save_comparison(base, plt, comb, overall, order, cand_all):
    """비교 CSV와 그래프를 저장한다."""
    cdir = base / "comparison"
    cdir.mkdir(parents=True, exist_ok=True)

    comb.to_csv(cdir / "compare_long.csv", index=False, encoding="utf-8-sig")
    cand_all.to_csv(cdir / "candidates_all.csv", index=False, encoding="utf-8-sig")

    col_order = list(dict.fromkeys(comb["라벨"]))
    rate_w = comb.pivot(index="종목", columns="라벨", values="처방률(%)")
    diff_w = comb.pivot(index="종목", columns="라벨", values="차이(%p)")
    ratio_w = comb.pivot(index="종목", columns="라벨", values="배수")

    rate_w = rate_w.reindex(index=order, columns=col_order)
    diff_w = diff_w.reindex(index=order, columns=col_order)
    ratio_w = ratio_w.reindex(index=order, columns=col_order)

    rate_w.to_csv(cdir / "compare_rate_wide.csv", encoding="utf-8-sig")
    diff_w.to_csv(cdir / "compare_diff_wide.csv", encoding="utf-8-sig")
    ratio_w.to_csv(cdir / "compare_ratio_wide.csv", encoding="utf-8-sig")

    if plt is not None:
        dot_compare(plt, comb, overall, cdir / "compare_dot.png")

        ratio_plot = ratio_w.head(PLOT_TOP_ITEMS).drop(
            columns=[f"{OVERALL_LABEL} | 전체"], errors="ignore"
        )
        heatmap(
            plt,
            ratio_plot,
            "모드별 집단 처방률 배수 히트맵 (전체 처방률 = 1.0배)",
            cdir / "compare_diff_heatmap.png",
            cbar_label="전체 처방률 대비 배수",
            cmap="RdBu_r",
            fmt="{:.2f}배",
            center=1.0,
        )

    return cdir


# ---------- 데이터 준비 ----------
def item_matrix(items, vocab):
    """사람 x 종목 0/1 행렬."""
    idx = {v: i for i, v in enumerate(vocab)}
    M = np.zeros((len(items), len(vocab)), dtype=bool)
    for r, lst in enumerate(items):
        for it in set(lst):
            M[r, idx[it]] = True
    return M


def build_labels(df, mode, kmeans_file, kmeans_col):
    """모드별 집단 라벨 생성."""
    if mode == "overall":
        return (
            pd.Series("전체", index=df.index, name="GROUP"),
            "전체 집단 (분할 없음, 처방률 기준선)",
        )

    if mode == "cross":
        bits = (df[FEATURES].to_numpy(float) >= CROSS_THRESHOLD).astype(int)
        labels = ["".join(map(str, r)) for r in bits]
        desc = (
            "6항목 상/하 교차 그룹 (백분위 %d 기준, 1=상 0=하, 순서: %s)"
            % (CROSS_THRESHOLD, ", ".join(KO[f] for f in FEATURES))
        )
        return pd.Series(labels, index=df.index, name="GROUP"), desc

    ga = pd.read_csv(kmeans_file, encoding="utf-8-sig", dtype={ID_COL: str})
    if ID_COL not in ga.columns or kmeans_col not in ga.columns:
        raise SystemExit(
            f"[오류] 할당 파일에 {ID_COL} 또는 {kmeans_col} 열이 없습니다.\n"
            f"  사용 가능한 열: {list(ga.columns)}"
        )

    ga = ga.drop_duplicates(ID_COL)
    mp = ga.set_index(ID_COL)[kmeans_col]
    ids = df[ID_COL].astype(str)
    matched = ids.isin(mp.index).mean()
    print(f"[K-means] M_CODE 매칭률: {matched:.1%} ({kmeans_col})")

    if matched < 0.5:
        raise SystemExit(
            "[오류] M_CODE 매칭률이 50% 미만입니다. "
            "할당 파일과 분석 데이터의 M_CODE 형식을 확인하세요."
        )

    s = ids.map(mp).fillna(UNMATCHED).astype(str)
    desc = f"K-means 군집 할당 ({Path(kmeans_file).name} / 열 {kmeans_col})"
    return s.rename("GROUP"), desc


def overall_table(M, vocab):
    """전체 처방 빈도·처방률."""
    N = M.shape[0]
    total = M.sum()
    t = pd.DataFrame({"종목": vocab, "처방 빈도": M.sum(0).astype(int)})
    t["처방률(%)"] = (t["처방 빈도"] / N * 100).round(2)
    t["처방 건수 비율(%)"] = (t["처방 빈도"] / total * 100).round(2)
    t = t.sort_values("처방 빈도", ascending=False, kind="stable").reset_index(drop=True)
    t.insert(0, "순위", range(1, len(t) + 1))
    return t[OVERALL_COLS]


# ---------- 통계 보조 ----------
def chi_test(table):
    """범주 x [처방 O, 처방 X] 교차표의 카이제곱 검정."""
    table = np.asarray(table, float)
    table = table[table.sum(1) > 0]

    if (
        table.shape[0] < 2
        or table[:, 0].sum() == 0
        or table[:, 0].sum() == table.sum()
    ):
        return np.nan, np.nan, np.nan, np.nan

    chi2, p, _, exp = stats.chi2_contingency(table, correction=False)
    N = table.sum()
    k = min(table.shape) - 1
    V = np.sqrt(chi2 / (N * k))
    sparse = float((exp < MIN_EXPECTED).mean())
    return chi2, p, V, sparse


def adj_resid(table):
    """처방 O 열의 조정잔차."""
    table = np.asarray(table, float)
    N = table.sum()
    row = table.sum(1, keepdims=True)
    col = table.sum(0, keepdims=True)
    E = row * col / N

    with np.errstate(divide="ignore", invalid="ignore"):
        r = (table - E) / np.sqrt(E * (1 - row / N) * (1 - col / N))

    return np.nan_to_num(r[:, 0])


def holm(p):
    """Holm step-down 다중검정 보정."""
    p = np.nan_to_num(np.asarray(p, float), nan=1.0)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0

    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(running, 1.0)

    return adj


def verdict(p_holm, V):
    if np.isnan(p_holm):
        return "검정 불가"
    if p_holm < ALPHA and V >= EFFECT_MIN:
        return "유의·효과 있음"
    if p_holm < ALPHA:
        return "유의·효과 미약"
    return "비유의"


def direction(r):
    if np.isnan(r):
        return "-"
    if r >= RES_CUT:
        return "과처방"
    if r <= -RES_CUT:
        return "과소처방"
    return "차이 없음"


# ---------- 분석 본체 ----------
def group_analysis(groups, M, vocab, order, min_group, min_item):
    """집단별 처방률·배수 및 집단-종목 연관성 검정."""
    gsize = groups.value_counts()
    levels = sorted(l for l in gsize[gsize >= min_group].index if l != UNMATCHED)
    small = gsize[gsize < min_group]
    unmatched_n = int(gsize.get(UNMATCHED, 0))

    res = {
        "levels": levels,
        "small": small,
        "unmatched": unmatched_n,
        "group_long": pd.DataFrame(columns=GROUP_LONG_COLS),
        "wide": pd.DataFrame(index=order),
        "g_test": pd.DataFrame(columns=G_TEST_COLS),
        "g_resid": pd.DataFrame(columns=G_RESID_COLS),
    }

    if not levels:
        return res

    keep = groups.isin(levels).to_numpy()
    Mg = M[keep]
    gi = pd.Categorical(groups[keep], categories=levels).codes
    ng = np.bincount(gi, minlength=len(levels))

    # 중요: 전체 분석 대상 M을 기준으로 계산한다.
    # 소규모 집단·미분류 집단이 분석에서 빠져도 기준 처방률은 바뀌지 않는다.
    base_rate = M.mean(0) * 100
    cnt = np.vstack([Mg[gi == g].sum(0) for g in range(len(levels))])

    rows = []
    for g, lvl in enumerate(levels):
        for j, it in enumerate(vocab):
            rate = cnt[g, j] / ng[g] * 100
            ratio = rate / base_rate[j] if base_rate[j] > 0 else np.nan
            rows.append({
                "집단": lvl,
                "집단 N": int(ng[g]),
                "종목": it,
                "처방 빈도": int(cnt[g, j]),
                "처방률(%)": round(rate, 2),
                "전체 처방률(%)": round(base_rate[j], 2),
                "차이(%p)": round(rate - base_rate[j], 2),
                "배수": round(ratio, 2),
            })

    group_long = pd.DataFrame(rows, columns=GROUP_LONG_COLS)
    wide = group_long.pivot(
        index="종목", columns="집단", values="처방률(%)"
    ).reindex(order)

    res["group_long"] = group_long
    res["wide"] = wide

    if len(levels) < 2:
        return res

    tested = [j for j in range(len(vocab)) if Mg[:, j].sum() >= min_item]
    g_test_rows, g_resid_rows = [], []

    for j in tested:
        yes = np.bincount(gi, weights=Mg[:, j], minlength=len(levels))
        table = np.column_stack([yes, ng - yes])
        chi2, p, V, sparse = chi_test(table)
        r = adj_resid(table)

        over = [levels[g] for g in range(len(levels)) if r[g] >= RES_CUT]
        under = [levels[g] for g in range(len(levels)) if r[g] <= -RES_CUT]

        for g, lvl in enumerate(levels):
            g_resid_rows.append({
                "집단": lvl,
                "종목": vocab[j],
                "처방률(%)": round(yes[g] / ng[g] * 100, 2),
                "전체 처방률(%)": round(base_rate[j], 2),
                "조정잔차": round(r[g], 2),
                "방향": direction(r[g]),
            })

        g_test_rows.append({
            "종목": vocab[j],
            "처방 빈도": int(Mg[:, j].sum()),
            "chi2": chi2,
            "p": p,
            "Cramér V": V,
            "희소셀 비율(%)": round(sparse * 100, 1),
            "과처방 집단": ", ".join(over) if over else "-",
            "과소처방 집단": ", ".join(under) if under else "-",
        })

    g_test = pd.DataFrame(g_test_rows, columns=G_TEST_COLS)
    if len(g_test):
        g_test["p_holm"] = holm(g_test["p"].to_numpy())
        g_test["판정"] = [
            verdict(ph, v) for ph, v in zip(g_test["p_holm"], g_test["Cramér V"])
        ]
        g_test = g_test.sort_values("p_holm").reset_index(drop=True)

    res["g_test"] = g_test
    res["g_resid"] = pd.DataFrame(g_resid_rows, columns=G_RESID_COLS)
    return res


def bin_analysis(df, M, vocab, min_item):
    """체력 변수별 구간 처방률 및 구간-종목 연관성 검정."""
    bin_tests, bin_tables = [], {}

    for f in FEATURES:
        bcodes = pd.cut(df[f], BIN_EDGES, labels=False).to_numpy().astype(int)
        nb = np.bincount(bcodes, minlength=len(BIN_LABELS))
        rate_rows = []

        for j in range(len(vocab)):
            if M[:, j].sum() < min_item:
                continue

            yes = np.bincount(bcodes, weights=M[:, j], minlength=len(BIN_LABELS))
            table = np.column_stack([yes, nb - yes])
            chi2, p, V, sparse = chi_test(table)

            with np.errstate(divide="ignore", invalid="ignore"):
                rates = np.nan_to_num(yes / nb * 100)

            hi, lo = int(np.argmax(rates)), int(np.argmin(rates))
            bin_tests.append({
                "구간 변수": KO[f],
                "종목": vocab[j],
                "처방 빈도": int(M[:, j].sum()),
                "chi2": chi2,
                "p": p,
                "Cramér V": V,
                "희소셀 비율(%)": round(sparse * 100, 1),
                "최고 처방률 구간": BIN_LABELS[hi],
                "최고 처방률(%)": round(rates[hi], 2),
                "최저 처방률 구간": BIN_LABELS[lo],
                "최저 처방률(%)": round(rates[lo], 2),
            })

            row = {"종목": vocab[j]}
            row.update({BIN_LABELS[b]: round(rates[b], 2) for b in range(len(BIN_LABELS))})
            row["구간 간 차이(%p)"] = round(rates[hi] - rates[lo], 2)
            rate_rows.append(row)

        bin_tables[KO[f]] = pd.DataFrame(rate_rows).sort_values(
            "구간 간 차이(%p)", ascending=False
        )

    bin_test = pd.DataFrame(bin_tests, columns=B_TEST_COLS)
    if len(bin_test):
        bin_test["p_holm"] = holm(bin_test["p"].to_numpy())
        bin_test["판정"] = [
            verdict(ph, v) for ph, v in zip(bin_test["p_holm"], bin_test["Cramér V"])
        ]
        bin_test = bin_test.sort_values("p_holm").reset_index(drop=True)

    return bin_test, bin_tables


# ---------- 보고서 ----------
def _fmt(v):
    if isinstance(v, (float, np.floating)):
        if np.isnan(v):
            return "-"
        return f"{v:.3f}" if abs(v) < 1 and v != 0 else f"{v:.2f}"
    return str(v)


def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(_fmt(v) for v in r) + " |")
    return "\n".join(lines)


def write_report(path, mode, info, overall, res, bin_test, has_graphs, cand):
    testable = len(res["levels"]) >= 2
    g_test = res["g_test"]
    n_eff = int((g_test["판정"] == "유의·효과 있음").sum()) if len(g_test) else 0
    n_weak = int((g_test["판정"] == "유의·효과 미약").sum()) if len(g_test) else 0
    b_eff = int((bin_test["판정"] == "유의·효과 있음").sum()) if len(bin_test) else 0
    b_weak = int((bin_test["판정"] == "유의·효과 미약").sum()) if len(bin_test) else 0

    L = []
    L.append(f"# 운동처방 빈도·처방률 및 집단 간 연관성 보고서 ({MODE_LABEL[mode]})\n")
    L.append("## 0. 분석 개요")
    L.append(f"- 분석 대상: {info['N']:,}명 (결측 제외 전 {info['N_raw']:,}명)")
    L.append(f"- 집단 정의: {info['group_desc']}")

    small_text = ", ".join(f"{k}({v}명)" for k, v in res["small"].items()) or "없음"
    L.append(
        f"- 분석 집단 수: {len(res['levels'])}개 "
        f"(최소 {info['min_group']}명 기준 미달로 제외: {small_text})"
    )

    if res["unmatched"]:
        L.append(f"- 군집 할당이 없어 제외된 인원: {res['unmatched']:,}명")

    if testable:
        L.append(
            f"- 검정 대상: 처방 {info['min_item']}건 이상 종목 — "
            f"집단 검정 {len(g_test)}개, 구간 검정 {len(bin_test)}개"
        )
    else:
        L.append("- 집단 검정: 수행하지 않음 (분석 집단이 2개 미만)")

    L.append(
        f"- 유의수준 α={ALPHA}, 다중검정 보정: Holm, "
        f"효과크기: Cramér's V (실질 기준 {EFFECT_MIN} 이상)"
    )
    L.append("- 배수: 집단 처방률 ÷ 전체 처방률 (예: 2.0은 전체의 2배)\n")

    L.append("## 1. 전체 처방 빈도·처방률")
    L.append(
        md_table(overall.head(TOP_REPORT)[
            ["순위", "종목", "처방 빈도", "처방률(%)", "처방 건수 비율(%)"]
        ]) + "\n"
    )
    if has_graphs:
        L.append("그래프: `../graphs/overall_top_items.png`\n")

    L.append("## 2. 집단별 처방 빈도·처방률 (집단별 상위 3종목, 배수 포함)")
    if len(res["group_long"]):
        top_rows = []
        for g, sub in res["group_long"].groupby("집단", sort=False):
            s = sub.sort_values("처방률(%)", ascending=False).head(3)
            row = {"집단": g, "N": int(sub["집단 N"].iloc[0])}
            for i, (_, r) in enumerate(s.iterrows(), 1):
                row[f"{i}위 종목"] = (
                    f"{r['종목']} ({r['처방률(%)']:.1f}%, {r['배수']:.2f}배)"
                )
            top_rows.append(row)

        L.append(md_table(pd.DataFrame(top_rows)) + "\n")
        L.append(
            "전체 집단별 빈도·처방률·배수는 `freq_by_group.csv`, "
            "피벗 형태는 `freq_group_rate_matrix.csv`에 있습니다.\n"
        )

        if has_graphs:
            L.append(
                "그래프: `graphs/group_rate_heatmap.png`, "
                "`graphs/group_diff_heatmap.png`, `graphs/group_top_items_bar.png`\n"
            )
    else:
        L.append("분석 가능한 집단이 없습니다.\n")

    L.append("## 3. 집단-처방 연관성 판정")
    if not testable:
        if mode == "overall":
            L.append(
                "전체 집단은 분할이 없는 기준선이므로 연관성 검정을 수행하지 않습니다. "
                "위 1·2절의 처방률이 다른 집단 비교의 기준값이 됩니다.\n"
            )
        else:
            L.append("분석 가능한 집단이 2개 미만이어서 연관성 검정을 수행하지 않았습니다.\n")
    else:
        L.append(f"**모드 결론: {mode_conclusion(res, g_test)}**\n")

        if n_eff:
            L.append(
                f"- 효과 있음(통계 유의 + Cramér's V ≥ {EFFECT_MIN}): {n_eff}개 종목\n"
            )
        if n_weak:
            L.append(
                f"- 통계적으로만 유의(V < {EFFECT_MIN}): {n_weak}개 종목 — "
                "차이는 있으나 효과 크기는 작음\n"
            )
        if not n_eff and not n_weak:
            L.append("- 보정 후 통계적으로 유의한 집단-종목 연관은 없습니다.\n")

        if len(g_test):
            show_cols = [
                "종목", "처방 빈도", "p_holm", "Cramér V",
                "과처방 집단", "과소처방 집단", "판정"
            ]
            L.append(
                md_table(g_test.sort_values("p_holm")[show_cols].head(TOP_REPORT)) + "\n"
            )

        L.append(
            "전체 결과는 `group_item_test.csv`, "
            "집단별 조정잔차는 `group_item_residuals.csv`에 있습니다.\n"
        )

    L.append("## 4. 집단별 결론")
    if testable:
        L.append(md_table(group_summary(res, cand)) + "\n")
        L.append(
            "과처방/과소처방 종목은 전체 처방률이 기준 이상인 종목 중 배수 상위·하위 "
            f"{TOP_GROUP_ITEMS}개입니다. 결론 기준: 강한 후보가 있으면 '차이 확인', "
            "참고 후보만 있으면 '차이 가능성', 없으면 '뚜렷한 차이 없음'입니다.\n"
        )
    else:
        L.append("집단별 결론은 분석 집단이 2개 이상일 때 제공됩니다.\n")

    L.append("## 5. 종목 구간별 처방 비율")
    if b_eff or b_weak:
        L.append(
            f"검정한 {len(bin_test)}개 구간 검정 중 효과 있음 {b_eff}개, "
            f"통계적으로만 유의(효과 작음) {b_weak}개입니다.\n"
        )
        show_b = [
            "구간 변수", "종목", "Cramér V", "p_holm", "판정",
            "최고 처방률 구간", "최고 처방률(%)",
            "최저 처방률 구간", "최저 처방률(%)"
        ]
        L.append(
            md_table(
                bin_test.sort_values("Cramér V", ascending=False)[show_b].head(TOP_REPORT * 2)
            ) + "\n"
        )
    else:
        L.append("보정 후 구간 간 처방률 차이가 유의한 종목은 없습니다.\n")

    L.append("구간별 처방률 전체 표는 `bin_rate_<변수>.csv`에 있습니다.\n")
    if has_graphs:
        L.append("그래프: `../graphs/bin_rate_<변수>.png`\n")

    L.append("## 6. 후보 칸 스크리닝 (전체 대비 배수 기준)")
    L.append(
        f"기준: 인원 {SCREEN_MIN_N}명 이상, 전체 처방률 {SCREEN_MIN_BASE}% 이상, "
        f"배수 {SCREEN_MIN_RATIO}배 이상 또는 {1 / SCREEN_MIN_RATIO:.2f}배 이하, "
        f"같은 종목에서 같은 방향 집단 {SCREEN_MIN_CONSIST}개 이상, "
        "배수의 95% 신뢰구간이 1을 포함하지 않을 것.\n"
    )

    if mode == "overall" or cand is None or cand.empty:
        L.append("조건을 모두 만족하는 후보 칸이 없습니다.\n")
    else:
        n_strong = int((cand["후보 등급"] == "강한 후보").sum())
        L.append(
            f"후보 {len(cand)}개 중 강한 후보 {n_strong}개, "
            f"참고 후보 {len(cand) - n_strong}개입니다.\n"
        )
        show = [
            "후보 등급", "집단", "집단 N", "종목", "처방률(%)",
            "전체 처방률(%)", "배수", "배수_low", "배수_high",
            "같은방향집단수", "조정잔차", "p_holm", "Cramér V", "판정"
        ]
        L.append(md_table(cand[show].head(SCREEN_TOP_REPORT)) + "\n")
        L.append("전체 후보는 `candidates.csv`에 있습니다.\n")

    L.append("## 7. 해석 시 유의사항")
    L.append("- 본 분석은 관찰 자료에 기반한 연관성 분석이며, 인과관계를 입증하지 않습니다.")
    if mode == "cross":
        L.append(
            "- 교차 그룹은 입력 체력 변수로 만들어졌으므로, "
            "구간 검정과 교차집단 검정은 서로 독립적이지 않습니다."
        )
    if mode == "kmeans":
        L.append(
            "- K-means 군집도 체력 변수로 만들어졌으므로 구간 검정과 독립적이지 않습니다. "
            "군집 수 선택(실루엣 계수)과 함께 해석하십시오."
        )
    L.append(
        "- 기대빈도 5 미만 셀이 많은 검정은 카이제곱 근사가 부정확할 수 있으므로 "
        "해당 검정의 희소셀 비율을 함께 보십시오."
    )
    L.append(
        "- Cramér's V 기준은 Cohen의 관례(0.1 약, 0.3 중, 0.5 강)를 참고하며, "
        "자유도가 큰 검정에서는 같은 V라도 해석이 달라질 수 있습니다."
    )
    L.append(
        "- 배수는 전체 처방률을 기준으로 하므로, "
        "전체 처방률이 낮은 종목은 같은 차이라도 배수가 크게 나옵니다."
    )
    L.append(
        "- 후보 칸은 칸 단위로 여러 번 검정한 결과를 걸러낸 것이므로, "
        "칸 자체의 p값을 확정 결론으로 쓰지 마십시오."
    )

    Path(path).write_text("\n".join(L), encoding="utf-8")


def write_final_report(path, info, overall, mode_info, bin_test, cand_all):
    """모드별·집단별 결론을 통합한 최종 보고서."""
    L = []
    L.append("# 운동처방 빈도·처방률 최종 보고서\n")

    L.append("## 1. 분석 개요")
    L.append(f"- 분석 대상: {info['N']:,}명")
    L.append(f"- 집단 모드: {', '.join(MODE_LABEL[m] for m in mode_info)}")
    L.append(f"- K-means 할당: {info.get('kmeans_desc', '-')}")
    L.append(
        f"- 판정: 종목 검정은 Holm 보정 p < {ALPHA}이고 "
        f"Cramér's V ≥ {EFFECT_MIN}이면 '효과 있음', "
        f"V < {EFFECT_MIN}이면 '통계적으로만 유의'입니다."
    )
    L.append(
        f"- 후보 칸: 배수 {SCREEN_MIN_RATIO}배 이상 또는 "
        f"{1 / SCREEN_MIN_RATIO:.2f}배 이하이고 집단 인원 {SCREEN_MIN_N}명 이상, "
        f"전체 처방률 {SCREEN_MIN_BASE}% 이상, "
        "배수 95% 신뢰구간이 1을 포함하지 않는 칸\n"
    )

    L.append("## 2. 모드별 결론")
    rows = []

    for mode, mi in mode_info.items():
        res, cand = mi["res"], mi["cand"]
        g_test = res["g_test"]
        n_eff = int((g_test["판정"] == "유의·효과 있음").sum()) if len(g_test) else 0
        n_weak = int((g_test["판정"] == "유의·효과 미약").sum()) if len(g_test) else 0
        n_s = int((cand["후보 등급"] == "강한 후보").sum()) if len(cand) else 0
        n_w = len(cand) - n_s if len(cand) else 0

        rows.append({
            "모드": MODE_LABEL[mode],
            "집단 수": len(res["levels"]),
            "효과 있음 종목": n_eff,
            "통계적으로만 유의 종목": n_weak,
            "후보(강한/참고)": f"{n_s}/{n_w}",
            "결론": mode_conclusion(res, g_test) if mode != "overall" else "기준선",
        })

    L.append(md_table(pd.DataFrame(rows)) + "\n")

    L.append("## 3. 집단별 결론")
    for mode, mi in mode_info.items():
        if mode == "overall":
            continue
        res, cand = mi["res"], mi["cand"]
        L.append(f"### {MODE_LABEL[mode]}")
        if len(res["levels"]) < 2:
            L.append("분석 가능한 집단이 2개 미만입니다.\n")
            continue
        L.append(md_table(group_summary(res, cand)) + "\n")

    L.append("## 4. 강한 후보 칸")
    if len(cand_all) and (cand_all["후보 등급"] == "강한 후보").any():
        strong = cand_all[cand_all["후보 등급"] == "강한 후보"].copy()
        strong["_dev"] = np.abs(np.log(strong["배수"].astype(float)))
        strong = strong.sort_values("_dev", ascending=False).head(SCREEN_TOP_REPORT)
        show = [
            "모드", "집단", "종목", "처방률(%)", "전체 처방률(%)", "배수",
            "배수_low", "배수_high", "조정잔차", "p_holm", "Cramér V"
        ]
        L.append(md_table(strong[show]) + "\n")
    else:
        L.append(
            "강한 후보 칸이 없습니다. 칸 단위 기준(배수 + 종목 검정 + 칸 잔차)을 "
            "모두 만족하는 집단 차이는 확인되지 않았습니다.\n"
        )

    L.append("## 5. 체력 구간 결과")
    b_eff = int((bin_test["판정"] == "유의·효과 있음").sum()) if len(bin_test) else 0
    b_weak = int((bin_test["판정"] == "유의·효과 미약").sum()) if len(bin_test) else 0
    L.append(
        f"- 구간-종목 검정 {len(bin_test)}개 중 효과 있음 {b_eff}개, "
        f"통계적으로만 유의 {b_weak}개"
    )

    if b_eff == 0 and b_weak > 0:
        L.append("- 차이는 통계적으로 존재하지만 효과 크기가 작습니다.\n")
    elif b_eff == 0:
        L.append("- 체력 구간에 따른 처방률 차이는 확인되지 않았습니다.\n")
    else:
        L.append("- 효과 크기가 기준을 넘는 구간-종목 연관이 있습니다.\n")

    L.append("## 6. 종합 결론")
    strong_modes = [
        MODE_LABEL[m] for m, mi in mode_info.items()
        if mi["res"]["levels"] and len(mi["res"]["g_test"])
        and (mi["res"]["g_test"]["판정"] == "유의·효과 있음").any()
    ]
    weak_modes = [
        MODE_LABEL[m] for m, mi in mode_info.items()
        if mi["res"]["levels"] and len(mi["res"]["g_test"])
        and (mi["res"]["g_test"]["판정"] == "유의·효과 미약").any()
        and m not in [
            k for k, v in mode_info.items()
            if (v["res"]["g_test"]["판정"] == "유의·효과 있음").any()
        ]
    ]

    if strong_modes:
        L.append(
            f"- 집단과 처방 사이의 연관이 효과 크기 기준까지 확인된 모드: "
            f"{', '.join(strong_modes)}."
        )
    elif weak_modes:
        L.append(
            f"- 집단별 처방 차이는 통계적으로는 유의하나 효과 크기가 작습니다"
            f"({', '.join(weak_modes)})."
        )
    else:
        L.append("- 분석한 집단 모드에서 집단별 처방 차이는 확인되지 않았습니다.")

    n_strong_cand = (
        int((cand_all["후보 등급"] == "강한 후보").sum()) if len(cand_all) else 0
    )
    if n_strong_cand:
        L.append(
            f"- 강한 후보 칸 {n_strong_cand}개가 있으며, 위 4절의 칸을 우선 확인하십시오."
        )
    else:
        L.append(
            "- 강한 후보 칸은 없습니다. 특정 집단에서 뚜렷하게 많이 또는 적게 "
            "처방되는 종목은 확인되지 않았습니다."
        )

    L.append(
        f"- 체력 구간에 따른 처방 차이는 통계적으로 유의한 항목이 있으나 "
        "효과 크기는 작습니다(5절).\n"
    )

    L.append("## 7. 한계")
    L.append("- 관찰 자료 기반이며 인과관계를 입증하지 않습니다.")
    L.append(
        "- 교차집단과 K-means 집단은 체력 변수로 만들어졌으므로 체력과 처방의 연관은 "
        "구조적으로 포함됩니다. 이는 처방 기준과 체력 기준의 관계를 보여 주는 것이지, "
        "처방이 효과적이었다는 근거가 아닙니다."
    )
    L.append("- 칸 단위 스크리닝은 여러 번 검정한 결과를 걸러낸 것이므로 확정 결론으로 쓰지 않습니다.")
    L.append(
        "- 배수의 기준값은 전체 분석 대상의 처방률이며, 해당 집단도 전체에 포함됩니다."
    )

    Path(path).write_text("\n".join(L), encoding="utf-8")


def save_mode(
    out, mode, desc, df_info, overall, res, bin_test, bin_tables,
    min_item, min_group, plt, order, cand
):
    overall.to_csv(out / "freq_overall.csv", index=False, encoding="utf-8-sig")
    res["group_long"].to_csv(out / "freq_by_group.csv", index=False, encoding="utf-8-sig")
    res["wide"].to_csv(out / "freq_group_rate_matrix.csv", encoding="utf-8-sig")
    res["g_test"].to_csv(out / "group_item_test.csv", index=False, encoding="utf-8-sig")
    res["g_resid"].to_csv(out / "group_item_residuals.csv", index=False, encoding="utf-8-sig")
    bin_test.to_csv(out / "bin_item_test.csv", index=False, encoding="utf-8-sig")
    cand.to_csv(out / "candidates.csv", index=False, encoding="utf-8-sig")
    group_summary(res, cand).to_csv(out / "group_summary.csv", index=False, encoding="utf-8-sig")

    for name, t in bin_tables.items():
        t.to_csv(out / f"bin_rate_{name}.csv", index=False, encoding="utf-8-sig")

    try:
        with pd.ExcelWriter(out / "freq_analysis.xlsx", engine="openpyxl") as xw:
            overall.to_excel(xw, sheet_name="전체빈도", index=False)
            res["group_long"].to_excel(xw, sheet_name="집단별빈도", index=False)
            res["wide"].to_excel(xw, sheet_name="집단별처방률행렬")
            res["g_test"].to_excel(xw, sheet_name="집단검정", index=False)
            res["g_resid"].to_excel(xw, sheet_name="집단잔차", index=False)
            bin_test.to_excel(xw, sheet_name="구간검정", index=False)
            cand.to_excel(xw, sheet_name="후보칸", index=False)
            group_summary(res, cand).to_excel(xw, sheet_name="집단별결론", index=False)
            for name, t in bin_tables.items():
                t.to_excel(xw, sheet_name=f"구간_{name}"[:31], index=False)
    except ImportError:
        print("[경고] openpyxl이 없어 엑셀 저장을 건너뜁니다. (pip install openpyxl)")

    has_graphs = False
    if plt is not None and mode != "overall":
        g_dir = out / "graphs"
        g_dir.mkdir(exist_ok=True)
        plot_group_heatmaps(plt, res, order, g_dir)
        bar_group_top_items(plt, res, overall, g_dir / "group_top_items_bar.png")
        has_graphs = True

    info = dict(
        df_info,
        group_desc=desc,
        min_group=min_group,
        min_item=min_item,
        n_g_tests=len(res["g_test"]),
        n_b_tests=len(bin_test),
    )
    write_report(out / "report.md", mode, info, overall, res, bin_test, has_graphs, cand)


# ---------- 메인 ----------
def main():
    ap = argparse.ArgumentParser(
        description="운동처방 빈도·연관성 분석 (기본값은 파일 상단 설정 사용)"
    )
    ap.add_argument("--in_path", default=str(IN_PATH))
    ap.add_argument("--out_dir", default=str(OUT_DIR))
    ap.add_argument(
        "--modes",
        default=",".join(MODES),
        help="실행할 집단 모드 (cross, kmeans, overall 중 쉼표 구분). 기본: 전부",
    )
    ap.add_argument(
        "--kmeans_file",
        default=str(KMEANS_FILE),
        help="K-means 할당 CSV 경로 (기본값: 상단 KMEANS_FILE)",
    )
    ap.add_argument(
        "--kmeans_col",
        default=KMEANS_COL,
        help="할당 열 이름 (기본값: 상단 KMEANS_COL)",
    )
    ap.add_argument("--min_item", type=int, default=MIN_ITEM_COUNT)
    ap.add_argument("--min_group", type=int, default=MIN_GROUP_N)
    ap.add_argument("--no_plot", action="store_true", help="그래프 생성 생략")
    a = ap.parse_args()

    modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    bad = [m for m in modes if m not in MODES]
    if bad:
        raise SystemExit(f"알 수 없는 모드: {bad} (사용 가능: {', '.join(MODES)})")

    if "kmeans" in modes and not Path(a.kmeans_file).is_file():
        raise SystemExit(
            f"[오류] K-means 파일이 없습니다: {a.kmeans_file}\n"
            "  상단 KMEANS_FILE 경로를 확인하세요."
        )

    base = Path(a.out_dir) / "freq_analysis"
    base.mkdir(parents=True, exist_ok=True)
    plt = None if a.no_plot else _plt()

    raw = load_data(a.in_path)
    df = raw.dropna(subset=FEATURES).reset_index(drop=True)
    items = df["ITEMS"].tolist()
    vocab = sorted(count_items(items))
    M = item_matrix(items, vocab)
    overall = overall_table(M, vocab)
    order = overall["종목"].tolist()
    bin_test, bin_tables = bin_analysis(df, M, vocab, a.min_item)
    df_info = {"N": len(df), "N_raw": len(raw)}

    # 전체 공통 그래프
    if plt is not None:
        g_dir = base / "graphs"
        g_dir.mkdir(exist_ok=True)
        bar_overall(plt, overall, g_dir / "overall_top_items.png")
        plot_bin_heatmaps(plt, bin_tables, g_dir)

    summary = []
    mode_info = {}
    cand_parts = []
    kmeans_desc = "-"

    for mode in modes:
        groups, desc = build_labels(df, mode, a.kmeans_file, a.kmeans_col)
        if mode == "kmeans":
            kmeans_desc = desc

        res = group_analysis(groups, M, vocab, order, a.min_group, a.min_item)
        cand = (
            screen_candidates(mode, res)
            if mode != "overall"
            else pd.DataFrame(columns=CAND_COLS)
        )

        if len(cand):
            cand_parts.append(cand)

        mode_info[mode] = {"res": res, "cand": cand, "desc": desc}
        out = base / mode
        out.mkdir(parents=True, exist_ok=True)

        save_mode(
            out, mode, desc, df_info, overall, res, bin_test, bin_tables,
            a.min_item, a.min_group, plt, order, cand
        )

        g_test = res["g_test"]
        summary.append({
            "집단 모드": MODE_LABEL[mode],
            "집단 수": len(res["levels"]),
            "검정 종목 수": len(g_test),
            "효과 있음": int((g_test["판정"] == "유의·효과 있음").sum()) if len(g_test) else 0,
            "통계적으로만 유의": int((g_test["판정"] == "유의·효과 미약").sum()) if len(g_test) else 0,
            "후보 칸 수": len(cand),
            "폴더": str(out),
        })
        print(
            f"[{MODE_LABEL[mode]}] 집단 {len(res['levels'])}개, "
            f"후보 {len(cand)}개 저장: {out}"
        )

    if summary:
        sdf = pd.DataFrame(summary)
        sdf.to_csv(base / "mode_comparison.csv", index=False, encoding="utf-8-sig")
        print("\n=== 집단 모드 비교 ===")
        print(sdf.drop(columns=["폴더"]).to_string(index=False))

    cand_all = (
        pd.concat(cand_parts, ignore_index=True)
        if cand_parts else pd.DataFrame(columns=CAND_COLS)
    )

    comb = build_comparison(
        {m: mi["res"] for m, mi in mode_info.items()}, overall, len(df)
    )
    cdir = save_comparison(base, plt, comb, overall, order, cand_all)

    final_info = dict(df_info, kmeans_desc=kmeans_desc)
    write_final_report(
        base / "final_report.md", final_info, overall, mode_info, bin_test, cand_all
    )

    print(f"\n[비교 저장] {cdir}")
    print(f"[최종 보고서] {base / 'final_report.md'}")


if __name__ == "__main__":
    main()