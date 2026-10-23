"""가상 장병 생성, 최근 측정 연계·부상 위험 그룹 계산, Poisson 부상 생성을 테스트합니다."""

import numpy as np
import pandas as pd
import pytest

from data.scripts.paths import (
    DEFINITION_INJURY_RISK_GROUP,
    DEFINITION_KS_NFA_FINAL,
    DEFINITION_SOLDIER_INJURY,
    DEFINITION_SOLDIER_PERSONNEL,
)
from data.scripts.synthesis.generate_synthetic_injuries import (
    build_injury_records,
    generate_injury_data,
    get_region_injury_summary,
    get_repeat_injury_soldiers,
    get_unit_injury_summary,
)
from data.scripts.synthesis.generate_synthetic_injuries import run as injury_run
from data.scripts.synthesis.generate_synthetic_personnel import (
    LAST_NAMES,
    generate_personnel_data,
)
from data.scripts.synthesis.generate_synthetic_personnel import run as personnel_run
from data.scripts.synthesis.link_fitness_and_injury_risk import (
    FITNESS_COLUMNS,
    INJURIES_PER_PERSON_YEAR,
    assign_measurement_risk_groups,
    build_risk_group_table,
    calculate_injury_risk,
    percentile_cuts,
    select_latest_measurements,
    summarize_linked_categories,
)
from data.scripts.synthesis import link_fitness_and_injury_risk
from data.scripts.synthesis.link_fitness_and_injury_risk import run as link_run
from data.scripts.utils import load_definition_columns

# 원본 연구의 가중치(INJURY_RISK)는 사용자가 채울 예정이므로, 테스트는 그룹마다 다른 값을 따로 넣어 쓴다.
TEST_INJURY_RISK = {
    "LOW": {"LOW": 3.0, "MODERATE": 2.0, "HIGH": 1.5},
    "MODERATE": {"LOW": 2.0, "MODERATE": 1.0, "HIGH": 0.8},
    "HIGH": {"LOW": 3.5, "MODERATE": 2.5, "HIGH": 1.2},
}


@pytest.fixture(autouse=True)
def injury_risk_weights(monkeypatch):
    """모든 테스트에서 부상 위험 가중치를 테스트용 값으로 바꿉니다."""
    monkeypatch.setattr(link_fitness_and_injury_risk, "INJURY_RISK", TEST_INJURY_RISK)


def make_fitness_data() -> pd.DataFrame:
    """회원 4명이 한 번씩 측정한 체력 데이터를 만듭니다."""
    return pd.DataFrame({
        "MESURE_ID": [101, 102, 103, 104],
        "M_CODE": ["a", "b", "c", "d"],
        "MESURE_DE": ["20240101", "20240102", "20240103", "20240104"],
        "STRENGTH": [40.0, 50.0, 60.0, 70.0],
        "ENDURANCE": [30.0, 40.0, 50.0, 60.0],
        "CARDIO": [20.0, 30.0, 40.0, 50.0],
        "FLEXIBILITY": [-5.0, 0.0, 5.0, 10.0],
        "HEIGHT": [160.0, 170.0, 180.0, 190.0],
        "WEIGHT": [50.0, 60.0, 70.0, 80.0],
        "BMI": [17.0, 22.0, 27.0, 32.0],
        "BODY_FAT_PERCENTAGE": [10.0, 15.0, 20.0, 25.0],
    })


def make_fitness_with_repeat() -> pd.DataFrame:
    """회원 a가 한 번 더 측정한(더 늦은 날짜, BMI 24) 체력 데이터를 만듭니다."""
    return pd.concat([
        make_fitness_data(),
        make_fitness_data().iloc[[0]].assign(MESURE_ID=105, MESURE_DE="20250101", BMI=24.0),
    ], ignore_index=True)


def make_personnel(count: int) -> pd.DataFrame:
    """장병 명단 정의서 컬럼을 갖춘 가상 장병 데이터를 만듭니다."""
    return generate_personnel_data(count, seed=0)


def make_injury_soldiers(lambdas: list[float]) -> pd.DataFrame:
    """부상 생성 입력(장병 속성과 기대 부상 건수)을 만듭니다."""
    soldiers = make_personnel(len(lambdas))
    soldiers["EXPECTED_INJURY_COUNT"] = lambdas
    return soldiers


# 가상 장병 명단


def test_personnel_generation_creates_one_soldier_per_member(tmp_path):
    """측정 행 수가 아니라 회원(M_CODE) 수만큼 장병을 만들고 정의서 컬럼대로 저장하는지 확인합니다."""
    fitness_path = tmp_path / "fitness.csv"
    output_path = tmp_path / "personnel.csv"
    pd.DataFrame({"MESURE_ID": [11, 12, 13], "M_CODE": ["a", "a", "b"]}).to_csv(
        fitness_path, index=False, encoding="utf-8-sig"
    )

    personnel_run(fitness_path, DEFINITION_SOLDIER_PERSONNEL, output_path)

    personnel = pd.read_csv(output_path, encoding="utf-8-sig")
    assert len(personnel) == 2
    assert personnel.columns.tolist() == load_definition_columns(DEFINITION_SOLDIER_PERSONNEL)
    assert personnel["SOLDIER_ID"].is_unique


def test_personnel_generation_is_reproducible_with_seed():
    """같은 시드면 같은 명단을, 다른 시드면 다른 명단을 만드는지 확인합니다."""
    first = generate_personnel_data(50, seed=42)

    pd.testing.assert_frame_equal(first, generate_personnel_data(50, seed=42))
    assert not first["SOLDIER_ID"].equals(generate_personnel_data(50, seed=7)["SOLDIER_ID"])


def test_last_names_have_no_duplicates():
    """성씨 목록에 같은 성이 두 번 들어 있지 않은지 확인합니다."""
    # 중복된 성은 그 성이 뽑힐 확률을 두 배로 만든다.
    assert len(LAST_NAMES) == len(set(LAST_NAMES))


# 최근 측정 연계·부상 위험 그룹


def test_latest_measurement_is_chosen_per_member():
    """회원마다 측정일이 가장 늦은 측정을, 같은 날이면 MESURE_ID가 큰 측정을 고르는지 확인합니다."""
    fitness = pd.DataFrame({
        "MESURE_ID": [1, 2, 3, 4, 5],
        "M_CODE": ["a", "b", "a", "b", "b"],
        "MESURE_DE": ["20240101", "20240105", "20240301", "20240110", "20240110"],
    })

    latest = select_latest_measurements(fitness)

    assert latest["MESURE_ID"].tolist() == [3, 5]
    assert latest["M_CODE"].tolist() == ["a", "b"]


def test_linkage_uses_latest_measurement_of_each_member():
    """장병이 회원별 가장 최근 측정과 연결되고 그 측정의 체력값을 갖는지 확인합니다."""
    linked = calculate_injury_risk(make_personnel(4), make_fitness_with_repeat())

    assert len(linked) == 4
    assert linked["MESURE_ID"].tolist() == [102, 103, 104, 105]
    assert linked.set_index("M_CODE").loc["a", "BMI"] == 24.0


def test_linkage_uses_all_measurements_for_percentile_cuts():
    """BMI와 심폐지구력 모두 최근 측정이 아니라 전체 측정의 25·75 백분위수로 구간을 나누는지 확인합니다."""
    # 회원 a의 이전 측정(BMI 17, CARDIO 20)은 최근 측정이 아니지만 경계 계산에는 들어가야 한다.
    fitness = make_fitness_with_repeat().assign(CARDIO=[20.0, 30.0, 40.0, 50.0, 60.0])
    linked = calculate_injury_risk(make_personnel(4), fitness).set_index("M_CODE")

    assert percentile_cuts(fitness["BMI"]) == (22.0, 27.0)
    assert percentile_cuts(fitness["CARDIO"]) == (30.0, 50.0)
    # 하위 경계 이하는 LOW, 상위 경계 이상은 HIGH다. 최근 측정만 쓰면 BMI 경계가 (23.5, 28.25)라 b가 LOW, c가 MODERATE가 된다.
    assert linked["BMI_LEVEL"].to_dict() == {"b": "LOW", "c": "HIGH", "d": "HIGH", "a": "MODERATE"}
    assert linked["CARDIO_LEVEL"].to_dict() == {"b": "LOW", "c": "MODERATE", "d": "HIGH", "a": "HIGH"}


def test_linkage_normalizes_risk_and_calculates_expected_count():
    """상대 위험도 평균이 1이고 기대 부상 건수가 1인당 0.3건 × 상대 위험도인지 확인합니다."""
    personnel = make_personnel(4)
    fitness = make_fitness_data()

    linked = calculate_injury_risk(personnel, fitness)

    assert linked["MESURE_ID"].tolist() == fitness["MESURE_ID"].tolist()
    assert linked["SOLDIER_ID"].tolist() == personnel["SOLDIER_ID"].tolist()
    pd.testing.assert_frame_equal(linked.loc[:, FITNESS_COLUMNS], fitness.loc[:, FITNESS_COLUMNS])
    assert linked["RELATIVE_INJURY_RISK"].mean() == pytest.approx(1.0)
    # 선행 연구: 장병 1명당 연간 0.3건
    assert INJURIES_PER_PERSON_YEAR == 0.3
    # 그룹 표의 값은 정의서의 DECIMAL(7,6)에 맞춰 소수 6자리로 반올림된다.
    np.testing.assert_allclose(
        linked["EXPECTED_INJURY_COUNT"], linked["RELATIVE_INJURY_RISK"] * 0.3, atol=1e-6
    )
    assert linked["EXPECTED_INJURY_COUNT"].sum() == pytest.approx(0.3 * len(linked), abs=1e-5)


def test_risk_group_table_covers_nine_groups_with_soldier_mean_baseline():
    """그룹 표가 9개 그룹을 모두 담고, 장병 평균 기대 부상 건수가 0.3이 되는지 확인합니다."""
    soldier_group_ids = pd.Series([1, 5, 5, 9])

    groups = build_risk_group_table(soldier_group_ids)

    assert groups["INJURY_RISK_GROUP_ID"].tolist() == list(range(1, 10))
    soldier_counts = soldier_group_ids.map(groups.set_index("INJURY_RISK_GROUP_ID")["EXPECTED_INJURY_COUNT"])
    assert soldier_counts.mean() == pytest.approx(0.3, abs=1e-6)
    # 그룹 1은 BMI 하위·심폐 하위, 그룹 2는 BMI 하위·심폐 중간, 그룹 9는 BMI 상위·심폐 상위다.
    levels = groups.set_index("INJURY_RISK_GROUP_ID")[["BMI_LEVEL", "CARDIO_LEVEL"]]
    assert levels.loc[1].tolist() == ["LOW", "LOW"]
    assert levels.loc[2].tolist() == ["LOW", "MODERATE"]
    assert levels.loc[9].tolist() == ["HIGH", "HIGH"]


def test_risk_group_table_rejects_missing_weights(monkeypatch):
    """INJURY_RISK에 비어 있는 가중치가 있으면 그룹 번호를 알려 주며 오류를 내는지 확인합니다."""
    weights = {bmi: dict(cardio) for bmi, cardio in TEST_INJURY_RISK.items()}
    weights["HIGH"]["HIGH"] = None
    monkeypatch.setattr(link_fitness_and_injury_risk, "INJURY_RISK", weights)

    with pytest.raises(ValueError, match="그룹 9"):
        build_risk_group_table(pd.Series([1, 9]))


def test_measurement_risk_groups_match_linked_soldiers():
    """모든 측정에 그룹 번호를 붙이고, 장병의 최근 측정은 연계 결과와 같은 그룹이 되는지 확인합니다."""
    fitness = make_fitness_with_repeat()

    measurement_groups = assign_measurement_risk_groups(fitness)
    linked = calculate_injury_risk(make_personnel(4), fitness)

    assert len(measurement_groups) == len(fitness)
    by_measure = dict(zip(fitness["MESURE_ID"], measurement_groups))
    assert [by_measure[measure_id] for measure_id in linked["MESURE_ID"]] == (
        linked["INJURY_RISK_GROUP_ID"].tolist()
    )


def test_linked_category_summary_reports_counts_and_percentages():
    """BMI·CARDIO 구간별 인원수와 비율을 집계하는지 확인합니다."""
    linked = pd.DataFrame({
        "BMI_LEVEL": ["LOW", "LOW", "HIGH", "HIGH"],
        "CARDIO_LEVEL": ["LOW", "MODERATE", "MODERATE", "HIGH"],
    })

    summary = summarize_linked_categories(linked)

    bmi_summary = summary[summary["분류"] == "BMI 구간"].set_index("구간")
    assert bmi_summary["인원수(명)"].to_dict() == {"하위 25%": 2, "중간 50%": 0, "상위 25%": 2}
    assert bmi_summary["비율(%)"].to_dict() == {"하위 25%": 50.0, "중간 50%": 0.0, "상위 25%": 50.0}
    cardio_summary = summary[summary["분류"] == "CARDIO 구간"].set_index("구간")
    assert cardio_summary["인원수(명)"].to_dict() == {"하위 25%": 1, "중간 50%": 2, "상위 25%": 1}
    assert cardio_summary["비율(%)"].to_dict() == {"하위 25%": 25.0, "중간 50%": 50.0, "상위 25%": 25.0}


def test_linkage_rejects_personnel_and_member_count_mismatch():
    """장병 수와 회원 수가 다르면 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match="수가 같아야"):
        calculate_injury_risk(make_personnel(1), make_fitness_data())


def test_linkage_rejects_negative_baseline():
    """1인당 부상 건수가 음수이면 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match="injuries_per_person"):
        calculate_injury_risk(make_personnel(4), make_fitness_data(), injuries_per_person=-0.1)


def test_link_run_writes_final_measurements_and_risk_group_table(tmp_path):
    """연계 단계가 군번·그룹 번호를 붙인 FINAL 측정 데이터와 그룹 표를 정의서 컬럼대로 저장하는지 확인합니다."""
    fitness = make_fitness_with_repeat().assign(M_SEQ_NO="1", AGE="20")
    personnel = make_personnel(4)
    paths = {name: tmp_path / f"{name}.csv" for name in ("personnel", "fitness", "linked", "groups", "final")}
    personnel.to_csv(paths["personnel"], index=False, encoding="utf-8-sig")
    fitness.to_csv(paths["fitness"], index=False, encoding="utf-8-sig")

    link_run(
        paths["personnel"],
        paths["fitness"],
        DEFINITION_KS_NFA_FINAL,
        DEFINITION_INJURY_RISK_GROUP,
        paths["linked"],
        paths["groups"],
        paths["final"],
    )

    final = pd.read_csv(paths["final"], dtype=str, encoding="utf-8-sig")
    groups = pd.read_csv(paths["groups"], encoding="utf-8-sig")
    assert final.columns.tolist() == load_definition_columns(DEFINITION_KS_NFA_FINAL)
    # 최종 측정 데이터에는 국민체력100 식별자(회원식별번호·측정일련번호)를 남기지 않는다.
    assert not {"M_CODE", "M_SEQ_NO"} & set(final.columns)
    assert len(final) == len(fitness)
    # 같은 회원의 측정은 모두 같은 군번을 갖는다. 회원식별번호는 입력에서 MESURE_ID로 찾는다.
    member_by_measure = fitness.set_index(fitness["MESURE_ID"].astype(str))["M_CODE"]
    soldiers_per_member = final.groupby(final["MESURE_ID"].map(member_by_measure))["SOLDIER_ID"].nunique()
    assert soldiers_per_member.eq(1).all()
    assert set(final["SOLDIER_ID"]) == set(personnel["SOLDIER_ID"])
    assert groups.columns.tolist() == load_definition_columns(DEFINITION_INJURY_RISK_GROUP)
    assert len(groups) == 9


# 부상 기록


def test_injury_generation_allows_repeat_injuries_with_poisson_counts():
    """λ가 크면 한 장병에게 서로 다른 부위의 부상이 여러 건 생기는지 확인합니다."""
    injuries = generate_injury_data(make_injury_soldiers([1.0] * 100), seed=3)

    assert injuries["SOLDIER_ID"].nunique() < len(injuries)
    assert injuries.groupby("SOLDIER_ID").size().max() > 1
    assert not injuries.duplicated(["SOLDIER_ID", "INJURY_LOCATION"]).any()


def test_zero_injury_intensity_generates_no_injuries():
    """λ가 0인 장병에게는 부상이 생기지 않는지 확인합니다."""
    assert generate_injury_data(make_injury_soldiers([0.0]), seed=3).empty


def test_injury_records_follow_definition_and_values(tmp_path):
    """부상 기록이 정의서 컬럼대로 저장되고 예방 가능 여부가 Y/N인지 확인합니다."""
    soldiers_path = tmp_path / "soldiers.csv"
    output_path = tmp_path / "injuries.csv"
    make_injury_soldiers([1.0] * 30).to_csv(soldiers_path, index=False, encoding="utf-8-sig")

    injury_run(soldiers_path, DEFINITION_SOLDIER_INJURY, output_path, seed=1)

    records = pd.read_csv(output_path, encoding="utf-8-sig")
    assert records.columns.tolist() == load_definition_columns(DEFINITION_SOLDIER_INJURY)
    assert records["INJURY_ID"].tolist() == list(range(1, len(records) + 1))
    assert set(records["PREVENTABILITY"]) <= {"Y", "N"}


def test_fixed_injury_count_and_unit_summary():
    """건수를 지정하면 정확히 그만큼 만들고, 부대·지역 요약이 부상 기록과 맞는지 확인합니다."""
    # 이전에 부상 생성 모듈 안에 있던 테스트를 옮긴 것
    soldiers = make_personnel(100)

    injuries = generate_injury_data(soldiers, seed=123, injury_count=150)

    assert len(injuries) == 150
    assert injuries["SOLDIER_ID"].duplicated().any()
    assert not injuries.duplicated(["SOLDIER_ID", "INJURY_LOCATION"]).any()
    records = build_injury_records(injuries)
    assert records.columns[0] == "INJURY_ID"
    unit_summary = get_unit_injury_summary(soldiers, injuries)
    assert unit_summary["총_부상건수"].sum() == 150
    assert {"전체인원", "부상률(%)", "예방가능_비율(%)"}.issubset(unit_summary.columns)
    region_summary = get_region_injury_summary(soldiers, injuries)
    assert region_summary["부상건수"].sum() == 150
    assert region_summary["부상인원"].sum() == injuries["SOLDIER_ID"].nunique()
    repeat = get_repeat_injury_soldiers(injuries)
    assert not repeat.empty
    assert (repeat["부상건수"] > 1).all()


def test_total_injury_count_follows_poisson_of_point_three_n():
    """연계부터 부상 생성까지 거친 총 부상 건수가 평균·분산 모두 0.3N인 Poisson을 따르는지 확인합니다."""
    rng = np.random.default_rng(0)
    member_count = 1000
    # BMI·CARDIO를 넓게 퍼뜨려 12개 위험 집단이 섞이게 한다(λ가 장병마다 다름).
    fitness = pd.DataFrame({
        "MESURE_ID": np.arange(1, member_count + 1),
        "M_CODE": [f"m{index}" for index in range(member_count)],
        "MESURE_DE": ["20240101"] * member_count,
        "STRENGTH": rng.normal(50, 5, member_count),
        "ENDURANCE": rng.normal(40, 5, member_count),
        "CARDIO": rng.normal(45, 6, member_count),
        "FLEXIBILITY": rng.normal(10, 5, member_count),
        "HEIGHT": rng.normal(174, 6, member_count),
        "WEIGHT": rng.normal(72, 10, member_count),
        "BMI": rng.uniform(16, 34, member_count),
        "BODY_FAT_PERCENTAGE": rng.normal(20, 5, member_count),
    })
    linked = calculate_injury_risk(make_personnel(member_count), fitness)
    assert linked["EXPECTED_INJURY_COUNT"].nunique() > 1

    totals = np.array([len(generate_injury_data(linked, seed=seed)) for seed in range(300)])

    expected = 0.3 * member_count
    # 평균: 300회 표본 평균의 표준오차는 sqrt(300/300) = 1이므로 ±4 이내여야 한다.
    assert abs(totals.mean() - expected) < 4
    # 분산: Poisson이면 분산 = 평균. 표본 분산의 표준편차는 약 300·sqrt(2/299) ≈ 25이므로 ±30%로 본다.
    assert 0.7 < totals.var(ddof=1) / expected < 1.3
