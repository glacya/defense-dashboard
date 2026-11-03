"""CSV/DB 모드 선택과 DB 모드 로더를 테스트합니다. 실제 DB에는 접속하지 않습니다(run_query를 가짜로 바꿈)."""

import pandas as pd
import pytest
from sqlalchemy import text

from dashboard import data_source, main_data
from dashboard.py import fitness_overview_data, followup_probability
from dashboard.py.fitness_judgment import JUDGED_SQL
from dashboard.py.fitness_overview_data import summary_tables
from dashboard.py.injury_overview_data import build_injury_tables
from dashboard.py.management_targets_data import build_targets
from dashboard.py.personal_detail_data import build_changes

EVENTS = ["STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY"]


@pytest.fixture
def no_setting(tmp_path, monkeypatch):
    """실행 환경의 설정이 끼어들지 않게 환경 변수를 지우고 빈 .env를 가리킵니다."""
    monkeypatch.delenv(data_source.SETTING_NAME, raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(data_source, "ENV_PATH", env_path)
    return env_path


def test_source_priority(no_setting, monkeypatch):
    """함수 인자 > 환경 변수 > .env > 기본값(db) 순서로 정하는지 확인합니다."""
    assert data_source.resolve_source() == data_source.DEFAULT_SOURCE == "db"
    no_setting.write_text(f"{data_source.SETTING_NAME}=csv\n", encoding="utf-8")
    assert data_source.resolve_source() == "csv"
    monkeypatch.setenv(data_source.SETTING_NAME, " DB ")
    assert data_source.resolve_source() == "db"
    assert data_source.resolve_source("csv") == "csv"


def test_invalid_source_is_rejected(no_setting):
    with pytest.raises(ValueError, match="csv 또는 db"):
        data_source.resolve_source("sqlite")


def _judged() -> pd.DataFrame:
    """판정표 SQL 결과를 흉내 낸 가짜 표: 장병 a(근력 3회 연속 미달), b(2차에 근력·심폐 미달)."""
    rows = []
    for soldier, region, grades_by_round, bmi in [
        ("a", "서울", [(0, 2, 1, 3), (0, 2, 0, 3), (0, 1, 0, 3)], 26.0),
        ("b", "부산", [(1, 1, 1, 1), (0, 1, 0, 1), (2, 1, 1, 1)], 22.0),
    ]:
        first = grades_by_round[0]
        for round_number, grades in enumerate(grades_by_round, start=1):
            fail_count = sum(grade == 0 for grade in grades)
            first_fail = sum(grade == 0 for grade in first)
            persistent = round_number == 3 and all(g[0] == 0 for g in grades_by_round)
            row = {
                "MESURE_ID": f"{soldier}{round_number}", "SOLDIER_ID": soldier, "ROUND": round_number,
                "MESURE_DE": 20240100 + round_number, "BMI": bmi, "REGION_NAME": region,
                "SOLDIER_NAME": soldier.upper(), "UNIT_NAME": "1대대", "RANK_NAME": "병장",
                "FIRST_MESURE_ID": f"{soldier}1", "FAIL_COUNT": fail_count, "FIRST_FAIL_COUNT": first_fail,
                "HIGH_BMI_FAIL": bmi >= 25 and (grades[0] == 0 or grades[2] == 0),
                "MULTIPLE_FAIL": fail_count >= 2, "WORSENED": fail_count > first_fail, "PERSISTENT_FAIL": persistent,
            }
            for index, event in enumerate(EVENTS):
                row.update({event: 10.0 * round_number, f"{event}_GRADE": grades[index],
                            f"{event}_FIRST_VALUE": 10.0, f"{event}_FIRST_GRADE": first[index],
                            f"{event}_PERSISTENT": persistent and index == 0})
            rows.append(row)
    judged = pd.DataFrame(rows)
    judged["MANAGED"] = judged[["HIGH_BMI_FAIL", "MULTIPLE_FAIL", "WORSENED", "PERSISTENT_FAIL"]].any(axis=1)
    return judged


def test_judged_sql_binds_only_high_bmi():
    """판정표 SQL은 저장된 등급을 쓰므로 바인딩 값은 고BMI 기준 하나뿐인지 확인합니다."""
    assert set(text(JUDGED_SQL).compile().params) == {"high_bmi"}


def test_summary_tables_shape_sql_results_for_screen():
    """SQL 집계 결과를 화면 표(한글 컬럼, 종목 이름·단위, 미달률, 종목 순서)로 바꾸는지 확인합니다."""
    rounds = pd.DataFrame({"GRP": ["서울", "부산"], "ROUND": [1, 1], "TOTAL_SOLDIERS": [2, 1],
                           "MEASURED": [2, 1], "FAILED": [1, 0], "MANAGED": [1, 0]})
    events = pd.DataFrame({"GRP": ["서울"] * 4, "ROUND": [1] * 4, "EVENT": ["FLEXIBILITY", "STRENGTH", "CARDIO", "ENDURANCE"],
                           "MEASURED": [2] * 4, "MEAN": [1.0] * 4, "STD": [0.5] * 4, "FAILED": [0, 1, 0, 0],
                           "GRADE_1": [1] * 4, "GRADE_2": [0] * 4, "GRADE_3": [1, 0, 1, 1]})

    round_table, event_table = summary_tables(rounds, events, grouped=True)

    assert round_table.columns.tolist() == ["그룹", "회차", "전체장병수", "측정인원", "미달인원", "미달률", "관리대상인원"]
    assert round_table["미달률"].tolist() == [50.0, 0.0]
    assert event_table["종목"].tolist() == ["근력", "근지구력", "심폐지구력", "유연성"]
    assert event_table.loc[0, ["단위", "미달률"]].tolist() == ["%", 50.0]
    overall_rounds, _ = summary_tables(rounds.drop(columns="GRP").iloc[:1], events.drop(columns="GRP"))
    assert "그룹" not in overall_rounds


def test_build_targets_names_events_and_reasons():
    targets = build_targets(_judged()).set_index("MESURE_ID")
    assert targets.loc["a3", "FAILED_EVENTS"] == "근력 · 심폐지구력"
    assert targets.loc["a3", "PERSISTENT_EVENTS"] == "근력"
    assert targets.loc["a2", "NEW_FAILED_EVENTS"] == "심폐지구력"  # 근력은 1차부터 미달
    assert targets.loc["a3", "SELECTION_REASONS"] == "BMI≥25·근력 또는 심폐 미달 · 2개 이상 종목 미달 · 1차 대비 미달 종목 수 증가 · 동일 종목 최근 3회 지속 미달"
    assert targets.loc["b1", "SELECTION_REASONS"] == "" and targets.loc["b1", "BMI_GROUP"] == "보통"
    assert not any(column.endswith("_FIRST_GRADE") for column in targets)


def test_build_changes_compares_with_first_round():
    changes = build_changes(_judged()).set_index("MESURE_ID")
    assert changes.loc["b2", "STRENGTH_GRADE_CHANGE"] == "하락"
    assert changes.loc["b3", "STRENGTH_GRADE_CHANGE"] == "하락"   # 1등급 -> 2등급
    assert changes.loc["a1", "CARDIO_GRADE_CHANGE"] == "유지"
    assert changes.loc["a3", "STRENGTH_CHANGE"] == 20.0
    assert changes.loc["b3", "IMPROVED_EVENTS"] == ""


def test_build_injury_tables_uses_latest_round():
    injuries = pd.DataFrame({"INJURY_ID": ["1", "2", "3"], "SOLDIER_ID": ["a", "a", "b"]})
    personal, grades, summary = build_injury_tables(_judged(), injuries)
    assert personal.set_index("SOLDIER_ID").INJURY_COUNT.to_dict() == {"a": 2, "b": 1}
    strength = grades.loc[grades["종목"].eq("근력")].set_index("등급")
    assert strength.loc["3등급 미만", "전체인원"] == 1 and strength.loc["2등급", "부상건수"] == 1  # 최신(3차) 등급 기준
    assert summary.iloc[0][["전체장병수", "부상인원", "부상건수", "반복부상인원"]].tolist() == [2, 2, 3, 1]


def test_group_summary_rejects_unknown_column():
    """조직 구분 컬럼은 허용 목록에서만 받아 SQL에 넣는지 확인합니다."""
    with pytest.raises(ValueError, match="지원하지 않는"):
        fitness_overview_data.load_group_summary("SOLDIER_NAME; DROP TABLE soldiers", "db")


def test_probabilities_db_mode_reads_table(monkeypatch):
    calls = []

    def fake_query(sql, params=None):
        calls.append(sql)
        return pd.DataFrame({"SOLDIER_ID": pd.Series(["a", "b"], dtype="string"), "FAILURE_PROBABILITY": [0.1, 0.8]})

    monkeypatch.setattr(followup_probability, "run_query", fake_query)
    result = followup_probability.load_probabilities("db")
    assert "soldier_failure_probabilities" in calls[0]
    assert result.RISK_LEVEL.tolist() == ["안전", "경계3등급"]


def test_main_data_db_mode_matches_csv_types(monkeypatch):
    """DB 결과(*_ID 문자열, 측정일 문자열)를 CSV 모드와 같은 타입(정수 ID, 날짜)으로 바꾸는지 확인합니다."""
    measurements = pd.DataFrame({
        "MESURE_ID": pd.Series(["2", "1"], dtype="string"),
        "SOLDIER_ID": pd.Series(["s1", "s1"], dtype="string"),
        "AGE": [20, 21], "HEIGHT": [175.0, 175.0], "WEIGHT": [70.0, 71.0], "BMI": [22.9, 23.2],
        "BODY_FAT_PERCENTAGE": [15.0, 15.5], "MESURE_DE": ["20240101", "20230101"],
    })
    injuries = pd.DataFrame({"INJURY_ID": pd.Series(["1"], dtype="string"), "SOLDIER_ID": pd.Series(["s1"], dtype="string")})
    monkeypatch.setattr(main_data, "run_query",
                        lambda sql, params=None: (injuries if "injuries" in sql else measurements).copy())
    main_data._load_main_data_db.clear()

    loaded, loaded_injuries = main_data.load_main_data("db")

    main_data._load_main_data_db.clear()
    assert loaded.MESURE_ID.tolist() == [1, 2] and loaded.MESURE_ID.dtype == "int64"  # 측정일 순서
    assert pd.api.types.is_datetime64_any_dtype(loaded.MESURE_DE)
    assert loaded["BMI구간"].tolist() == ["정상", "정상"]
    assert loaded_injuries.INJURY_ID.dtype == "int64"
