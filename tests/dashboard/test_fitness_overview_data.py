"""전체 체력 현황의 SQL 집계 가공(summary_tables)과 조직별 합산을 검증합니다. 실제 DB에는 접속하지 않습니다."""

import pandas as pd
import plotly.express as px
import pytest

from dashboard.py import fitness_overview_data
from dashboard.py.fitness_overview_data import summary_tables
from dashboard.views.p01_fitness_overview import _combine_events, _combine_rounds


def _sql_results() -> tuple[pd.DataFrame, pd.DataFrame]:
    """queries.load_overview_rounds/events가 돌려주는 모양(대문자 컬럼, 종목 코드)의 지역별 결과."""
    rounds = pd.DataFrame({
        "GRP": ["부산", "서울"], "ROUND": [1, 1], "TOTAL_SOLDIERS": [1, 2],
        "MEASURED": [1, 2], "FAILED": [0, 1], "MANAGED": [0, 1],
    })
    events = pd.DataFrame({
        "GRP": ["서울", "서울", "부산"], "ROUND": [1, 1, 1], "EVENT": ["CARDIO", "STRENGTH", "STRENGTH"],
        "MEASURED": [2, 2, 1], "MEAN": [40.0, 50.0, 60.0], "STD": [1.0, 2.0, None], "FAILED": [0, 1, 0],
        "GRADE_1": [0, 0, 1], "GRADE_2": [1, 0, 0], "GRADE_3": [1, 1, 0],
    })
    return rounds, events


def test_summary_tables_build_korean_tables_with_rates_and_event_order():
    """한글 컬럼·미달률(측정 인원 분모)·종목 이름과 단위를 붙이고, 그룹·회차·종목 순서로 정렬하는지 확인합니다."""
    rounds, events = summary_tables(*_sql_results(), grouped=True)

    seoul = rounds.loc[rounds["그룹"].eq("서울")].iloc[0]
    assert (seoul["전체장병수"], seoul["미달인원"], seoul["미달률"]) == (2, 1, 50)
    assert events["그룹"].tolist() == ["부산", "서울", "서울"]
    assert events.loc[events["그룹"].eq("서울"), "종목"].tolist() == ["근력", "심폐지구력"]
    strength = events.iloc[1]
    assert (strength["단위"], strength["미달률"]) == ("%", 50)
    assert list(events.columns[:3]) == ["그룹", "회차", "종목"]


def test_group_summary_rejects_unsupported_column():
    with pytest.raises(ValueError, match="지원하지 않는 조직 구분"):
        fitness_overview_data.load_group_summary("RANK_NAME")


def test_group_comparison_trend_keeps_group_column_for_plotly():
    _, events = summary_tables(*_sql_results(), grouped=True)

    chart = px.line(events, x="회차", y="미달률", color="그룹", facet_col="종목", markers=True)

    assert chart.data


def test_combined_group_summaries_use_weighted_rates_and_means():
    rounds = pd.DataFrame([
        {
            "그룹": "A", "회차": 1, "전체장병수": 2, "측정인원": 2, "미달인원": 1, "관리대상인원": 1,
        },
        {
            "그룹": "B", "회차": 1, "전체장병수": 1, "측정인원": 1, "미달인원": 0, "관리대상인원": 0,
        },
    ])
    events = pd.DataFrame([
        {
            "그룹": "A", "회차": 1, "종목": "근력", "단위": "%",
            "측정인원": 2, "평균": 10.0, "표준편차": 2.0, "미달인원": 1,
            "1등급인원": 0, "2등급인원": 1, "3등급인원": 1,
        },
        {
            "그룹": "B", "회차": 1, "종목": "근력", "단위": "%",
            "측정인원": 1, "평균": 16.0, "표준편차": float("nan"), "미달인원": 0,
            "1등급인원": 1, "2등급인원": 0, "3등급인원": 0,
        },
    ])

    combined_rounds = _combine_rounds(rounds).iloc[0]
    combined_events = _combine_events(events).iloc[0]

    assert combined_rounds["미달률"] == pytest.approx(100 / 3)
    assert combined_events["미달률"] == pytest.approx(100 / 3)
    assert combined_events["평균"] == 12.0
    assert combined_events["표준편차"] == pytest.approx(14**0.5, rel=1e-6)
