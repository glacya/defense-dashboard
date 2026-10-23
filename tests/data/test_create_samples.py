"""샘플 추출 코드(data/scripts/create_samples.py)와 저장소에 있는 샘플 데이터를 테스트합니다.

샘플은 독자 참고용이라 원본(최종 데이터)은 저장소에 없습니다. 그래서 저장된 샘플은
샘플 세 개가 서로 맞는지(측정·명단·부상의 군번)와 정의서 컬럼을 따르는지 확인합니다.
"""

import pandas as pd
import pytest

from config import ROOT_DIR
from data.scripts.create_samples import (
    FITNESS_SAMPLE_PATH,
    INJURY_SAMPLE_PATH,
    PERSONNEL_SAMPLE_PATH,
    SAMPLE_SOLDIER_COUNT,
    SAMPLE_TARGETS,
    build_samples,
)
from data.scripts.utils import load_definition_columns, read_text_csv

# 체력 측정은 장병(회원)마다 3건이다(전처리 5단계: 3회 측정 회원 추출).
MEASURES_PER_SOLDIER = 3


def make_sources() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """장병 4명(측정 각 3건)과 부상 기록이 있는 작은 원본 데이터를 만듭니다."""
    soldiers = ["s1", "s2", "s3", "s4"]
    fitness = pd.DataFrame({
        "MESURE_ID": [str(index) for index in range(1, 13)],
        "SOLDIER_ID": [soldier for soldier in soldiers for _ in range(3)],
        "BMI": [str(20 + index) for index in range(12)],
    })
    personnel = pd.DataFrame({"SOLDIER_ID": soldiers, "SOLDIER_NAME": ["가", "나", "다", "라"]})
    injuries = pd.DataFrame({"INJURY_ID": ["1", "2", "3"], "SOLDIER_ID": ["s1", "s1", "s4"]})
    return fitness, personnel, injuries


def test_build_samples_keeps_all_rows_of_chosen_soldiers_unchanged():
    """고른 장병의 측정·명단·부상 행을 빠짐없이, 원본 값과 순서 그대로 뽑는지 확인합니다."""
    fitness, personnel, injuries = make_sources()

    fitness_sample, personnel_sample, injury_sample = build_samples(fitness, personnel, injuries, count=2, seed=0)

    chosen = set(personnel_sample["SOLDIER_ID"])
    assert len(chosen) == 2
    pd.testing.assert_frame_equal(fitness_sample, fitness[fitness["SOLDIER_ID"].isin(chosen)])
    pd.testing.assert_frame_equal(injury_sample, injuries[injuries["SOLDIER_ID"].isin(chosen)])
    assert set(fitness_sample["SOLDIER_ID"]) == chosen


def test_build_samples_is_reproducible_with_seed():
    """같은 시드면 같은 장병을 고르는지 확인합니다."""
    first = build_samples(*make_sources(), count=2, seed=7)[1]

    pd.testing.assert_frame_equal(first, build_samples(*make_sources(), count=2, seed=7)[1])


def test_build_samples_rejects_too_many_soldiers():
    """장병 수보다 많이 뽑으려 하면 오류를 내는지 확인합니다."""
    with pytest.raises(ValueError, match="고를 수 없습니다"):
        build_samples(*make_sources(), count=5)


def test_build_samples_rejects_soldier_missing_from_personnel():
    """측정에는 있는데 장병 명단에 없는 군번이 뽑히면 오류를 내는지 확인합니다."""
    fitness, personnel, injuries = make_sources()

    with pytest.raises(ValueError, match="명단에 없는 군번"):
        build_samples(fitness, personnel.iloc[:1], injuries, count=4)


@pytest.mark.parametrize(("_source", "definition_path", "sample_path"), SAMPLE_TARGETS)
def test_saved_samples_follow_definitions(_source, definition_path, sample_path):
    """저장된 샘플 세 개가 각 정의서의 컬럼을 정의서 순서대로 갖는지 확인합니다."""
    assert read_text_csv(sample_path).columns.tolist() == load_definition_columns(definition_path)


def test_saved_samples_link_by_soldier_id():
    """저장된 샘플의 측정·명단·부상이 같은 장병 100명으로 서로 이어지는지 확인합니다."""
    fitness = read_text_csv(FITNESS_SAMPLE_PATH)
    personnel = read_text_csv(PERSONNEL_SAMPLE_PATH)
    injuries = read_text_csv(INJURY_SAMPLE_PATH)

    assert personnel["SOLDIER_ID"].is_unique
    assert len(personnel) == SAMPLE_SOLDIER_COUNT
    assert set(fitness["SOLDIER_ID"]) == set(personnel["SOLDIER_ID"])
    assert fitness.groupby("SOLDIER_ID").size().eq(MEASURES_PER_SOLDIER).all()
    assert len(fitness) == SAMPLE_SOLDIER_COUNT * MEASURES_PER_SOLDIER
    assert fitness["MESURE_ID"].is_unique
    assert set(injuries["SOLDIER_ID"]) <= set(personnel["SOLDIER_ID"])
    assert injuries["INJURY_ID"].is_unique


def test_samples_are_not_referenced_by_other_code():
    """샘플 경로를 create_samples.py(와 경로 상수를 정의한 config.py) 밖의 코드가 참조하지 않는지 확인합니다."""
    # 샘플은 독자 참고용이라 파이프라인·대시보드의 입력이 되면 안 된다.
    allowed = {ROOT_DIR / "config.py", ROOT_DIR / "data" / "scripts" / "create_samples.py"}
    markers = ("SAMPLE_DIR", "_SAMPLE.csv", "create_samples", "data/samples")
    offenders = [
        str(path.relative_to(ROOT_DIR))
        for folder in ("data", "dashboard")
        for path in (ROOT_DIR / folder).rglob("*.py")
        if path not in allowed and any(marker in path.read_text(encoding="utf-8") for marker in markers)
    ]
    assert offenders == []
