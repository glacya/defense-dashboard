"""3회 측정 회원 추출 단계(select_three_measures)의 측정일·나이 흐름 검사를 테스트합니다."""

import pandas as pd
import pytest

from data.scripts.preprocessing.select_three_measures import (
    REASON_COL,
    find_age_time_inconsistency,
    remove_age_time_inconsistencies,
    run,
)
from data.scripts.utils import read_text_csv


def make_member(member_id: str, dates: list[str], ages: list[int]) -> pd.DataFrame:
    """회원 1명의 측정 기록(측정일·만나이)을 만듭니다."""
    return pd.DataFrame({
        "M_CODE": [member_id] * len(dates),
        "MESURE_DE": dates,
        "AGE": [str(age) for age in ages],
    })


@pytest.mark.parametrize(
    ("dates", "ages", "expected"),
    [
        # 1년마다 한 살씩: 정상
        (["20220101", "20230101", "20240101"], [20, 21, 22], None),
        # 같은 해 안에서 생일이 지나 한 살 늘어남: 정상
        (["20220101", "20220601", "20221201"], [20, 20, 21], None),
        (["20220101", "20230101", "20240101"], [21, 20, 22], "나이 감소"),
        (["20220101", "20220101", "20230101"], [20, 21, 21], "같은 날 나이 다름"),
        # 1년 사이에 세 살 늘어남: 최대 연도 차이 + 1살
        (["20220101", "20230101", "20240101"], [20, 23, 24], "연도 차이보다 나이 증가가 큼"),
        # 3년이 지났는데 나이가 그대로: 적어도 연도 차이 - 1살은 늘어야 함
        (["20220101", "20220601", "20250601"], [20, 20, 20], "연도 차이보다 나이 증가가 작음"),
    ],
)
def test_find_age_time_inconsistency_reports_first_rule_broken(dates, ages, expected):
    """측정일·만나이 흐름의 규칙별로 모순 사유(정상이면 None)를 돌려주는지 확인합니다."""
    assert find_age_time_inconsistency(make_member("m", dates, ages)) == expected


def test_remove_age_time_inconsistencies_drops_all_rows_of_inconsistent_member():
    """모순인 회원은 3건 모두 제거 행으로 옮기고 사유를 붙이며, 정상 회원의 행 순서는 유지하는지 확인합니다."""
    data = pd.concat([
        make_member("ok", ["20220101", "20230101", "20240101"], [20, 21, 22]),
        make_member("bad", ["20220101", "20230101", "20240101"], [21, 20, 22]),
    ], ignore_index=True)

    passed, removed = remove_age_time_inconsistencies(data)

    pd.testing.assert_frame_equal(passed, data.iloc[:3])
    assert removed["M_CODE"].tolist() == ["bad"] * 3
    assert removed[REASON_COL].unique().tolist() == ["나이 감소"]


def test_run_selects_three_measures_and_saves_inconsistent_members_separately(tmp_path):
    """run()이 3건을 고른 뒤 측정일·나이 흐름이 맞는 회원만 저장하고, 모순 회원은 제거 파일에 저장하는지 확인합니다."""
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "three.csv"
    removed_path = tmp_path / "removed.csv"
    pd.concat([
        make_member("ok", ["20220101", "20220601", "20230101"], [20, 20, 21]),
        make_member("bad", ["20220101", "20220601", "20230101"], [22, 20, 21]),
        # 측정이 2건뿐이라 3건 고르기에서 빠지는 회원
        make_member("few", ["20220101", "20230101"], [20, 21]),
    ], ignore_index=True).to_csv(input_path, index=False, encoding="utf-8-sig")

    run(input_path, output_path, removed_path)

    passed = read_text_csv(output_path)
    removed = read_text_csv(removed_path)
    assert passed["M_CODE"].tolist() == ["ok"] * 3
    assert removed["M_CODE"].tolist() == ["bad"] * 3
    assert removed[REASON_COL].unique().tolist() == ["나이 감소"]
