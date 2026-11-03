"""화면별 조회(dashboard/py/queries.py)의 SQL 조립과 결과 가공을 검증합니다. 실제 DB에는 접속하지 않습니다."""

import pandas as pd
import pytest

from dashboard.py import injury_overview_data, management_targets_data, queries


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
    assert "WHERE unit_name = :unit_name" in queries.judged_cte(one_unit=True)


def test_unit_card_people_pick_latest_round_or_selected_round(monkeypatch):
    """p01 부대 카드 명단: 전체는 장병별 최신 회차(측정 없는 장병 포함), 나머지는 선택 회차에서 조건대로 고르는지 확인합니다."""
    from dashboard.views import p01_fitness_overview as p01

    calls = []
    judged = pd.DataFrame({
        "SOLDIER_ID": ["a", "a", "b", "c"], "ROUND": [1, 2, 1, None],
        "FAIL_COUNT": [1, 0, 0, None], "MANAGED": [True, False, False, None],
    })
    monkeypatch.setattr(p01.queries, "load_unit_judgments", lambda unit: calls.append(unit) or judged)

    assert p01._people_for_metric("total", 1, "1사단").ROUND.tolist()[:2] == [2, 1]
    assert p01._people_for_metric("total", 1, "1사단").SOLDIER_ID.tolist() == ["a", "b", "c"]
    assert p01._people_for_metric("measured", 1, "1사단").SOLDIER_ID.tolist() == ["a", "b"]
    assert p01._people_for_metric("deficient", 1, "1사단").SOLDIER_ID.tolist() == ["a"]
    assert p01._people_for_metric("managed", 2, "1사단").empty
    assert p01._people_for_metric("total", 1, "1사단", ("b",)).SOLDIER_ID.tolist() == ["b"]
    assert set(calls) == {"1사단"}


@pytest.mark.parametrize("group_column", ["SOLDIER_NAME", "region_name; DROP TABLE soldiers"])
def test_overview_rejects_unknown_group(group_column):
    """조직 구분 컬럼은 허용 목록에서만 SQL에 넣는지 확인합니다."""
    with pytest.raises(ValueError, match="지원하지 않는"):
        queries.load_overview_rounds(group_column)


def test_overview_applies_selected_soldiers_with_bound_parameters(calls):
    """공용 필터에서 고른 장병만 창 함수 전에 좁혀 계산합니다."""
    queries.load_overview_rounds(soldier_ids=("soldier-1", "soldier-2"))

    sql, params = calls[0]
    assert "WHERE m.soldier_id = ANY(CAST(:soldier_ids AS text[]))" in sql
    assert "WHERE j.soldier_id" not in sql
    assert params == {
        "high_bmi": queries.HIGH_BMI,
        "soldier_ids": ["soldier-1", "soldier-2"],
    }


def test_overview_without_soldier_filter_keeps_all_personnel(calls):
    """기본 전체 조회는 군번 조건을 추가하지 않습니다."""
    queries.load_overview_events()

    sql, params = calls[0]
    assert "person_filter" not in sql
    assert "WHERE m.soldier_id = ANY" not in sql
    assert params == {"high_bmi": queries.HIGH_BMI}


def test_round_details_combines_summary_and_targets_in_one_query(calls):
    """요약과 대상 명단을 단일 판정 CTE 조회로 가져오며 빈 명단도 보존합니다."""
    calls.results["next"] = pd.DataFrame({
        "SUMMARY_MEASURED": [2, 2],
        "SUMMARY_MANAGED": [1, 1],
        "SUMMARY_HIGH_BMI_FAIL": [1, 1],
        "SUMMARY_MULTIPLE_FAIL": [0, 0],
        "SUMMARY_WORSENED": [0, 0],
        "SUMMARY_PERSISTENT_FAIL": [0, 0],
        "SOLDIER_ID": ["s1", "s2"],
        "SOLDIER_NAME": ["A", "B"],
    })

    summary, targets = queries.load_round_details(3)

    assert summary["MEASURED"] == 2 and summary["MANAGED"] == 1
    assert targets["SOLDIER_ID"].tolist() == ["s1", "s2"]
    assert len(calls) == 1
    assert "LEFT JOIN targets ON true" in calls[0][0]


def test_round_details_targets_include_management_view_columns():
    """병합 조회 결과도 기존 대상자 가공을 거쳐 표와 상세 카드의 컬럼을 제공해야 합니다."""
    raw = pd.DataFrame({
        "MESURE_DE": [20250101],
        "BMI": [27.0],
        "FAIL_COUNT": [2],
        "FIRST_FAIL_COUNT": [1],
        "STRENGTH_GRADE": [0],
        "ENDURANCE_GRADE": [2],
        "CARDIO_GRADE": [1],
        "FLEXIBILITY_GRADE": [3],
        "STRENGTH_FIRST_GRADE": [1],
        "ENDURANCE_FIRST_GRADE": [2],
        "CARDIO_FIRST_GRADE": [1],
        "FLEXIBILITY_FIRST_GRADE": [3],
        "STRENGTH_PERSISTENT": [False],
        "ENDURANCE_PERSISTENT": [False],
        "CARDIO_PERSISTENT": [False],
        "FLEXIBILITY_PERSISTENT": [False],
        "HIGH_BMI_FAIL": [True],
        "MULTIPLE_FAIL": [True],
        "WORSENED": [True],
        "PERSISTENT_FAIL": [False],
    })

    targets = management_targets_data.prepare_round_targets(raw)

    assert {
        "BMI_GROUP",
        "FAILED_EVENTS",
        "FAIL_COUNT_CHANGE",
        "NEW_FAILED_EVENTS",
        "PERSISTENT_EVENTS",
        "SELECTION_REASONS",
    }.issubset(targets.columns)
    assert targets.loc[0, "BMI_GROUP"] == "높음"
    assert targets.loc[0, "SELECTION_REASONS"]


def test_injury_distribution_passes_none_for_empty_filters(calls):
    """부대·계급 필터가 비어 있으면 None(조건 없음)으로, (지역, 부대) 쌍은 두 목록으로 나눠 넘기는지 확인합니다."""
    queries.load_injury_distribution([("서울", "1사단"), ("경기", "2사단")], [])

    sql, params = calls[0]
    assert params == {"unit_regions": ["서울", "경기"], "unit_names": ["1사단", "2사단"], "ranks": None}
    assert "unnest(CAST(:unit_regions AS text[]), CAST(:unit_names AS text[]))" in sql and "GROUPING SETS" in sql


def test_injury_records_uses_same_filter_and_picked_category(calls):
    """클릭 조회는 분포와 같은 필터에 고른 부위(또는 심각도)만 더해 넘기는지 확인합니다."""
    queries.load_injury_records([], ["병장"], location="무릎")

    sql, params = calls[0]
    assert params == {"unit_regions": None, "unit_names": None, "ranks": ["병장"],
                      "location": "무릎", "severity": None}
    assert queries.INJURY_FILTER_WHERE in sql


def test_injury_records_maps_display_unknown_label_to_source_value(calls):
    """차트의 '미상' 선택을 기존 원본 분류값으로 조회합니다."""
    queries.load_injury_records([], [], location='미상')

    assert calls[0][1]['location'] == '미지정'


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
