import pandas as pd
import plotly.express as px
import pytest

from dashboard.py.fitness_overview_data import summarize_by_group
from data.scripts.fitness_standards import FITNESS_EXERCISES, grade_cut
from dashboard.views.p01_fitness_overview import _combine_events, _combine_rounds


def _measurements() -> pd.DataFrame:
    rows = []
    for soldier_id, region, unit, strength in [
        ("001", "서울", "1부대", 0),
        ("002", "서울", "2부대", grade_cut("STRENGTH", 3)),
        ("003", "부산", "3부대", grade_cut("STRENGTH", 3)),
    ]:
        rows.append({
            "SOLDIER_ID": soldier_id,
            "MESURE_ID": int(soldier_id),
            "MESURE_DE": pd.Timestamp("2026-01-01"),
            "AGE": 20,
            "REGION_NAME": region,
            "UNIT_NAME": unit,
            **{
                event: strength if event == "STRENGTH" else grade_cut(event, 3)
                for event in FITNESS_EXERCISES
            },
        })
    return pd.DataFrame(rows)


def test_summarize_by_region_and_unit_preserves_rounds_and_counts():
    measurements = _measurements()

    region_rounds, region_events = summarize_by_group(measurements, "REGION_NAME")
    seoul = region_rounds.loc[region_rounds["그룹"].eq("서울")].iloc[0]
    seoul_strength = region_events.loc[
        region_events["그룹"].eq("서울") & region_events["종목"].eq("근력")
    ].iloc[0]

    assert seoul["회차"] == 1
    assert seoul["전체장병수"] == 2
    assert seoul_strength["미달인원"] == 1
    assert seoul_strength["미달률"] == 50

    unit_rounds, _ = summarize_by_group(measurements, "UNIT_NAME")
    assert set(unit_rounds["그룹"]) == {"1부대", "2부대", "3부대"}
    assert unit_rounds["전체장병수"].eq(1).all()


def test_summarize_by_group_rejects_unsupported_column():
    with pytest.raises(ValueError, match="지원하지 않는 조직 구분"):
        summarize_by_group(_measurements(), "RANK_NAME")


def test_group_comparison_trend_keeps_group_column_for_plotly():
    _, events = summarize_by_group(_measurements(), "REGION_NAME")

    chart = px.line(
        events,
        x="회차",
        y="미달률",
        color="그룹",
        facet_col="종목",
        markers=True,
    )

    assert chart.data


def test_combined_group_summaries_use_weighted_rates_and_means():
    rounds = pd.DataFrame([
        {
            "그룹": "A", "회차": 1, "전체장병수": 2, "측정인원": 2,
            "판정가능인원": 2, "판정불완전인원": 0, "미달인원": 1, "관리대상인원": 1,
        },
        {
            "그룹": "B", "회차": 1, "전체장병수": 1, "측정인원": 1,
            "판정가능인원": 1, "판정불완전인원": 0, "미달인원": 0, "관리대상인원": 0,
        },
    ])
    events = pd.DataFrame([
        {
            "그룹": "A", "회차": 1, "종목": "근력", "단위": "%",
            "유효측정인원": 2, "평균": 10.0, "표준편차": 2.0,
            "판정가능인원": 2, "판정불가인원": 0, "미달인원": 1,
            "1등급인원": 0, "2등급인원": 1, "3등급인원": 1,
        },
        {
            "그룹": "B", "회차": 1, "종목": "근력", "단위": "%",
            "유효측정인원": 1, "평균": 16.0, "표준편차": float("nan"),
            "판정가능인원": 1, "판정불가인원": 0, "미달인원": 0,
            "1등급인원": 1, "2등급인원": 0, "3등급인원": 0,
        },
    ])

    combined_rounds = _combine_rounds(rounds).iloc[0]
    combined_events = _combine_events(events).iloc[0]

    assert combined_rounds["미달률"] == pytest.approx(100 / 3)
    assert combined_events["미달률"] == pytest.approx(100 / 3)
    assert combined_events["평균"] == 12.0
    assert combined_events["표준편차"] == pytest.approx(14**0.5, rel=1e-6)
