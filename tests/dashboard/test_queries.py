"""화면별 조회(dashboard/py/queries.py)의 SQL 조립과 결과 가공을 검증합니다. 실제 DB에는 접속하지 않습니다."""

import pandas as pd
import pytest

from dashboard.py import injury_overview_data, queries


@pytest.fixture
def calls(monkeypatch):
    """run_query를 가짜로 바꿔 넘긴 SQL·params를 기록하고, 미리 정한 결과를 돌려줍니다."""
    class Recorded(list):
        results: dict

    recorded = Recorded()
    recorded.results = {}

    def fake_query(sql, params=None, ttl=None):
        recorded.append((sql, params))
        return recorded.results.get("next", pd.DataFrame())

    monkeypatch.setattr(queries, "run_query", fake_query)
    return recorded


def test_judged_cte_filters_one_soldier_before_windows():
    """한 장병만 볼 때는 창 함수 전에 거르고(결과 같음), 전체일 때는 조건이 없는지 확인합니다."""
    assert "WHERE m.soldier_id = :soldier_id" in queries.judged_cte(one_soldier=True)
    assert "WHERE m.soldier_id" not in queries.judged_cte()
    assert ":high_bmi" in queries.judged_cte()


@pytest.mark.parametrize("group_column", ["SOLDIER_NAME", "region_name; DROP TABLE soldiers"])
def test_overview_rejects_unknown_group(group_column):
    """조직 구분 컬럼은 허용 목록에서만 SQL에 넣는지 확인합니다."""
    with pytest.raises(ValueError, match="지원하지 않는"):
        queries.load_overview_rounds(group_column)


def test_injury_distribution_passes_none_for_empty_filters(calls):
    """지역·부대·계급 필터가 비어 있으면 None(조건 없음)으로, 고른 값은 목록으로 넘기는지 확인합니다."""
    queries.load_injury_distribution(["서울"], [], [])

    sql, params = calls[0]
    assert params == {"regions": ["서울"], "units": None, "ranks": None}
    assert "= ANY(CAST(:regions AS text[]))" in sql and "GROUPING SETS" in sql


def test_filtered_latest_returns_empty_when_nothing_selected(calls):
    """지역·부대·계급 중 하나라도 비면 어떤 이름과도 겹치지 않는 값을 넘겨 빈 결과가 되게 하는지 확인합니다."""
    queries.load_filtered_latest("20220101", "20221231", ["서울"], [], ["병장"], (19, 24))

    _, params = calls[0]
    assert params["regions"] == params["units"] == params["ranks"] == [""]
    assert (params["start"], params["age_min"], params["age_max"]) == ("20220101", 19, 24)


def test_distribution_counts_picks_rows_by_grouping_column():
    """GROUPING SETS 결과에서 기준별 건수와 전체 건수를 꺼내는지 확인합니다."""
    rows = pd.DataFrame({
        "INJURY_LOCATION": ["무릎", None, None, None],
        "SEVERITY": [None, "경증", None, None],
        "REGION_NAME": [None, None, "서울", None],
        "UNIT_NAME": [None] * 4,
        "RANK_NAME": [None] * 4,
        "INJURIES": [3, 3, 3, 3],
    })

    assert queries.distribution_counts(rows, None) == 3
    assert queries.distribution_counts(rows, "INJURY_LOCATION").values.tolist() == [["무릎", 3]]
    assert queries.distribution_counts(rows, "UNIT_NAME").empty


def test_injury_grade_table_fills_missing_grades(monkeypatch):
    """인원이 없는 종목·등급 조합도 0명(비율 없음)으로 채우고, 종목·등급 순서로 정렬하는지 확인합니다."""
    monkeypatch.setattr(injury_overview_data.queries, "load_injury_by_grade", lambda: pd.DataFrame({
        "EVENT": ["STRENGTH"], "GRADE": [0], "TOTAL": [4], "INJURED": [1], "INJURIES": [2],
    }))

    table = injury_overview_data.injury_grade_table()

    assert len(table) == 16 and table.iloc[0]["등급"] == "1등급"
    failed = table.loc[table["종목"].eq("근력") & table["등급"].eq("3등급 미만")].iloc[0]
    assert (failed["전체인원"], failed["부상인원"], failed["부상건수"], failed["부상자비율"]) == (4, 1, 2, 25.0)
    assert pd.isna(table.iloc[0]["부상자비율"])


def test_measurement_profile_requires_selected_measurement(calls):
    """선택 측정의 백분위가 없으면 오류를 내고, 측정 번호는 정수로 넘기는지 확인합니다."""
    calls.results["next"] = pd.DataFrame({"PROFILE": ["type"], "MEMBERS": [0], "STRENGTH": [None],
                                          "ENDURANCE": [None], "CARDIO": [None], "FLEXIBILITY": [None]})

    with pytest.raises(ValueError, match="백분위 자료가 없습니다"):
        queries.load_measurement_profile("12")
    assert calls[0][1] == {"mesure_id": 12}
