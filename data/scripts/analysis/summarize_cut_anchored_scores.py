"""심폐 종목 기록을 등급 컷 기준으로 선형 변환한 점수의 통계를 표로 정리합니다. (탐색용 임시 스크립트)

3등급 컷이 0, 2등급 컷이 1, 1등급 컷이 2가 되도록 종목마다 직선으로 변환합니다.
- 트레드밀·스텝검사(VO2max): 수정 컷 44.5 / 47.0 / 49.5 (공식 컷 42.0 / 44.8 / 47.6)
- 20m 왕복 오래달리기(횟수): 41 / 51.5 / 62. 실제 2등급 컷은 52회지만 컷 간격을 같게 하려고 51.5로 가정합니다.
등급 비율 표에는 VO2max의 공식 컷 기준 비율도 함께 적습니다.
비교를 위해 종목별 Z점수(표본 평균·표준편차)도 함께 계산합니다. 현재 파이프라인에서 쓰지 않습니다.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_CUT_ANCHORED, INTERMEDIATE_THREE_MEASURES
from data.scripts.analysis.standardize_cardio_scores import identify_cardio_event, read_input

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 파일 이름
SCORE_STATS_FILENAME = "score_stats.csv"
GRADE_RATIOS_FILENAME = "grade_ratios.csv"
SWITCH_CHANGES_FILENAME = "switch_changes.csv"

ID_COL = "M_CODE"
DATE_COL = "MESURE_DE"
VO2_EVENTS = ("TRAD", "STEP")
SHUTTLE_EVENT = "20M_RUN"
EVENT_LABELS = {"TRAD": "트레드밀", "STEP": "스텝검사", SHUTTLE_EVENT: "20m 왕복 오래달리기"}
# 국민체력100 공식 컷 (남자 19~24세, 2018 한국스포츠개발원 보고서 표 38·39). 각 컷 이상이면 그 등급이다.
# VO2max 컷은 2012~2017년 오래달리기 기록을 회귀식으로 환산한 값의 30/50/70 백분위라,
# 트레드밀·스텝검사 실측값에 적용하면 3등급 미만이 약 15%로 설계(30%)보다 적게 나온다.
OFFICIAL_VO2_CUTS = (42.0, 44.8, 47.6)
OFFICIAL_SHUTTLE_CUTS = (41.0, 52.0, 62.0)
# 수정 VO2max 컷. 3회분 추출 직전 단계(19~24세 전체, 2026-10-19 기준)에서 VO2max 컷 변환 점수의
# 평균·표준편차가 오래달리기와 같아지는 해(3등급 44.55, 간격 2.536)를 반올림했다.
# 이때 평균 차이 +0.03, 표준편차 비 1.015이고, 1등급 비율은 오래달리기보다 낮다(19% 대 26%).
# 오래달리기는 62회에서 측정을 멈춘 기록이 몰려 1등급 비율이 부풀려졌을 수 있어 평균·표준편차를 우선했다.
ADJUSTED_VO2_CUTS = (44.5, 47.0, 49.5)
# 선형 변환에 쓰는 (3등급, 2등급, 1등급) 컷
ANCHOR_CUTS = {"TRAD": ADJUSTED_VO2_CUTS, "STEP": ADJUSTED_VO2_CUTS, SHUTTLE_EVENT: (41.0, 51.5, 62.0)}
# 등급 비율에 쓰는 컷. 각 컷 이상이면 그 등급이다.
GRADE_CUTS = {"TRAD": ADJUSTED_VO2_CUTS, "STEP": ADJUSTED_VO2_CUTS, SHUTTLE_EVENT: OFFICIAL_SHUTTLE_CUTS}
# 등급 비율 표에 비교용으로 함께 적는 공식 컷
OFFICIAL_GRADE_CUTS = {"TRAD": OFFICIAL_VO2_CUTS, "STEP": OFFICIAL_VO2_CUTS}
GRADE_LABELS = ["등외", "3등급", "2등급", "1등급"]
DECIMALS = 4


def anchor_scores(events: pd.Series, values: pd.Series) -> pd.Series:
    """3등급 컷이 0, 1등급 컷이 2가 되도록 종목마다 선형 변환한 점수를 반환합니다."""
    lowest_cut = events.map(lambda event: ANCHOR_CUTS[event][0])
    highest_cut = events.map(lambda event: ANCHOR_CUTS[event][2])
    return (values - lowest_cut) / ((highest_cut - lowest_cut) / 2)


def within_event_z(events: pd.Series, values: pd.Series) -> pd.Series:
    """종목별 표본 평균·표준편차로 표준화한 Z점수를 반환합니다."""
    grouped = values.groupby(events)
    return (values - grouped.transform("mean")) / grouped.transform("std")


def describe(series: pd.Series) -> dict[str, float]:
    """행 수, 평균, 표준편차, 왜도, 최솟값, 중앙값, 최댓값을 반환합니다."""
    return {
        "N": len(series),
        "MEAN": series.mean(),
        "STD": series.std(),
        "SKEW": series.skew(),
        "MIN": series.min(),
        "MEDIAN": series.median(),
        "MAX": series.max(),
    }


def build_score_stats(events: pd.Series, values: pd.Series, scores: pd.Series) -> pd.DataFrame:
    """종목별·VO2max 합계·전체의 원래 값과 컷 변환 점수 통계표를 만듭니다.

    원래 값은 단위가 다른 종목을 섞으면 의미가 없으므로 전체 행에서는 비워 둡니다.
    """
    groups = {EVENT_LABELS[event]: events.eq(event) for event in ANCHOR_CUTS}
    groups["VO2max 합계(트레드밀+스텝)"] = events.isin(VO2_EVENTS)
    groups["전체"] = pd.Series(True, index=events.index)

    rows = []
    for label, mask in groups.items():
        raw = describe(values[mask]) if label != "전체" else {}
        score = describe(scores[mask])
        rows.append({
            "GROUP": label,
            "N": score["N"],
            "VALUE_MEAN": raw.get("MEAN"),
            "VALUE_STD": raw.get("STD"),
            **{f"SCORE_{key}": value for key, value in score.items() if key != "N"},
        })
    return pd.DataFrame(rows)


def build_grade_ratios(events: pd.Series, values: pd.Series) -> pd.DataFrame:
    """종목별 등급 비율(%)과, 각 컷이 종목 안에서 Z점수로 어디쯤인지를 표로 만듭니다.

    분석에 쓰는 컷(CUT_SET=수정 또는 공식) 행 뒤에, VO2max 종목은 공식 컷 기준 행을 비교용으로 덧붙입니다.
    """
    cut_sets = [
        *((event, cuts, "수정" if event in OFFICIAL_GRADE_CUTS else "공식") for event, cuts in GRADE_CUTS.items()),
        *((event, cuts, "공식") for event, cuts in OFFICIAL_GRADE_CUTS.items()),
    ]
    rows = []
    for event, cuts, cut_set in cut_sets:
        event_values = values[events.eq(event)]
        grades = pd.cut(event_values, [-np.inf, *cuts, np.inf], right=False, labels=GRADE_LABELS)
        ratios = grades.value_counts(normalize=True).reindex(GRADE_LABELS) * 100
        mean, std = event_values.mean(), event_values.std()
        rows.append({
            "EVENT": EVENT_LABELS[event],
            "CUT_SET": cut_set,
            "CUTS": "/".join(f"{cut:g}" for cut in cuts),
            "N": len(event_values),
            **{f"{label}_PCT": ratios[label] for label in reversed(GRADE_LABELS)},
            "2등급이상_PCT": ratios["2등급"] + ratios["1등급"],
            **{f"{label}_CUT_Z": (cut - mean) / std for label, cut in zip(["3등급", "2등급", "1등급"], cuts)},
        })
    return pd.DataFrame(rows)


def build_switch_changes(data: pd.DataFrame, events: pd.Series, scores: pd.Series, z_scores: pd.Series) -> pd.DataFrame:
    """같은 회원의 연속된 두 측정 사이 점수 변화를 종목 전환 유형별로 요약합니다.

    트레드밀과 스텝검사는 같은 VO2max 종목으로 묶습니다.
    같은 날 측정한 기록이 있어, 안정 정렬로 입력 순서를 유지한다.
    """
    work = pd.DataFrame({
        "member": data[ID_COL],
        "date": data[DATE_COL],
        "kind": np.where(events.eq(SHUTTLE_EVENT), "오래달리기", "VO2max"),
        "score": scores,
        "z": z_scores,
    }).sort_values(["member", "date"], kind="stable")
    grouped = work.groupby("member", sort=False)
    work["prev_kind"] = grouped["kind"].shift()
    work["score_change"] = work["score"] - grouped["score"].shift()
    work["z_change"] = work["z"] - grouped["z"].shift()
    pairs = work.dropna(subset=["prev_kind"])
    pairs = pairs.assign(SWITCH=pairs["prev_kind"] + " → " + pairs["kind"])

    table = pairs.groupby("SWITCH").agg(
        N=("score_change", "size"),
        SCORE_CHANGE_MEAN=("score_change", "mean"),
        SCORE_CHANGE_STD=("score_change", "std"),
        Z_CHANGE_MEAN=("z_change", "mean"),
        Z_CHANGE_STD=("z_change", "std"),
    )
    order = ["오래달리기 → 오래달리기", "VO2max → VO2max", "오래달리기 → VO2max", "VO2max → 오래달리기"]
    return table.reindex([switch for switch in order if switch in table.index]).reset_index()


def estimate_event_offset(switch_changes: pd.DataFrame, column: str) -> float:
    """종목을 오가는 두 방향의 평균 변화 차이의 절반으로, 같은 사람의 VO2max 점수가 오래달리기 점수보다 얼마나 높은지 추정합니다.

    시간에 따른 체력 변화가 전환 방향과 무관하면 두 방향에서 같은 크기로 더해지므로 차이를 내면 상쇄된다.
    """
    changes = switch_changes.set_index("SWITCH")[column]
    return float((changes["오래달리기 → VO2max"] - changes["VO2max → 오래달리기"]) / 2)


def run(input_path: Path, output_dir: Path) -> None:
    """input_path의 심폐 종목 기록으로 컷 변환 점수 통계, 등급 비율, 종목 전환 변화표를 output_dir에 저장합니다."""
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    score_stats_path = output_dir / SCORE_STATS_FILENAME
    grade_ratios_path = output_dir / GRADE_RATIOS_FILENAME
    switch_changes_path = output_dir / SWITCH_CHANGES_FILENAME
    # 2. 입력 로드 후 컷 변환 점수와 비교용 종목별 Z점수를 구한다.
    data = read_input(input_path).reset_index(drop=True)
    events, values = identify_cardio_event(data)
    scores = anchor_scores(events, values)
    z_scores = within_event_z(events, values)

    # 3. 표 세 개를 만든다.
    score_stats = build_score_stats(events, values, scores)
    grade_ratios = build_grade_ratios(events, values)
    switch_changes = build_switch_changes(data, events, scores, z_scores)

    # 4. 저장
    for table, path in [
        (score_stats, score_stats_path),
        (grade_ratios, grade_ratios_path),
        (switch_changes, switch_changes_path),
    ]:
        table.round(DECIMALS).to_csv(path, index=False, encoding="utf-8-sig")

    # 5. 요약 로그
    logger.info("입력 %s: %s행", display_path(input_path), f"{len(data):,}")
    for _, row in score_stats.iterrows():
        logger.info(
            "  %s: %s행, 컷 변환 점수 평균 %.3f, 표준편차 %.3f",
            row["GROUP"], f"{int(row['N']):,}", row["SCORE_MEAN"], row["SCORE_STD"],
        )
    if {"오래달리기 → VO2max", "VO2max → 오래달리기"}.issubset(switch_changes["SWITCH"]):
        logger.info(
            "같은 회원 기준 VO2max − 오래달리기 차이: 컷 변환 점수 %.3f, 종목별 Z점수 %.3f",
            estimate_event_offset(switch_changes, "SCORE_CHANGE_MEAN"),
            estimate_event_offset(switch_changes, "Z_CHANGE_MEAN"),
        )
    logger.info("저장(점수 통계): %s", display_path(score_stats_path))
    logger.info("저장(등급 비율): %s", display_path(grade_ratios_path))
    logger.info("저장(종목 전환 변화): %s", display_path(switch_changes_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_THREE_MEASURES, INTERMEDIATE_CUT_ANCHORED)


if __name__ == "__main__":
    main()
