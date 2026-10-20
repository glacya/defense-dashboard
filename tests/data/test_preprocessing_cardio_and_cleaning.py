"""심폐지구력 선택(원본 통합 단계)과 결측치·이상치 제거 단계의 함수를 확인합니다."""

import pandas as pd

from data.scripts.preprocessing.merge_raw_measurements import CARDIO_SOURCE_COLUMNS, select_cardio
from data.scripts.preprocessing.remove_missings_and_outliers import (
    CARDIO_MAX,
    NULLABLE_COLUMNS,
    REASON_COLUMN,
    remove_missing,
    remove_outliers,
)

RUN_COLUMN = CARDIO_SOURCE_COLUMNS["20M_RUN"]
TRAD_COLUMN = CARDIO_SOURCE_COLUMNS["TRAD"]
STEP_COLUMN = CARDIO_SOURCE_COLUMNS["STEP"]


def make_cardio_rows(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """(오래달리기, 트레드밀, 스텝검사) VO2max 출력 값 목록으로 원본 형식의 DataFrame을 만듭니다."""
    return pd.DataFrame(rows, columns=[RUN_COLUMN, TRAD_COLUMN, STEP_COLUMN])


def test_select_cardio_uses_single_event_value():
    """한 종목만 기록된 행은 그 종목의 값을 쓰는지 확인합니다."""
    cardio, count, selected = select_cardio(make_cardio_rows([("", "45.1", ""), ("", "", "47.3")]))
    assert cardio.tolist() == ["45.1", "47.3"]
    assert count.tolist() == [1, 1]
    assert selected.tolist() == ["TRAD", "STEP"]


def test_select_cardio_prefers_shuttle_run_when_multiple():
    """두 종목 이상 기록된 행은 오래달리기 값을 쓰는지 확인합니다."""
    # 공식 VO2max 등급 컷이 오래달리기 환산값으로 만들어져 오래달리기를 우선한다.
    cardio, count, selected = select_cardio(make_cardio_rows([("43.2", "46.0", ""), ("41.0", "", "44.4")]))
    assert cardio.tolist() == ["43.2", "41.0"]
    assert count.tolist() == [2, 2]
    assert selected.tolist() == ["20M_RUN", "20M_RUN"]


def test_select_cardio_leaves_blank_when_no_event():
    """한 종목도 기록되지 않은 행은 값과 종목 이름을 빈칸으로 두는지 확인합니다."""
    cardio, count, selected = select_cardio(make_cardio_rows([("", " ", "")]))
    assert cardio.tolist() == [""]
    assert count.tolist() == [0]
    assert selected.tolist() == [""]


def test_remove_missing_drops_rows_with_blank_values():
    """측정값이 빈 행은 제거되고 비어 있던 컬럼이 제거 사유에 적히는지 확인합니다."""
    df = pd.DataFrame({"CARDIO": ["45.0", ""], "CROSS_UP": ["40", ""], NULLABLE_COLUMNS[0]: ["", ""]})
    kept, removed, counts = remove_missing(df)
    assert len(kept) == 1
    assert removed[REASON_COLUMN].tolist() == ["CARDIO 결측; CROSS_UP 결측"]
    assert counts["CARDIO"] == 1


def test_remove_missing_keeps_rows_with_blank_nullable_column():
    """운동 처방처럼 결측을 허용한 컬럼만 빈 행은 남기는지 확인합니다."""
    df = pd.DataFrame({"CARDIO": ["45.0"], "CROSS_UP": ["40"], NULLABLE_COLUMNS[0]: [""]})
    kept, removed, _ = remove_missing(df)
    assert len(kept) == 1
    assert removed.empty


def test_remove_outliers_drops_decimal_counts():
    """횟수 종목(교차윗몸일으키기)에 소수가 기록된 행만 제거하는지 확인합니다."""
    df = pd.DataFrame({"CARDIO": ["45.3", "44.0"], "CROSS_UP": ["40", "40.5"]})
    kept, removed, counts = remove_outliers(df)
    # CARDIO는 VO2max라 소수가 정상이므로 이상치로 보지 않는다.
    assert kept["CROSS_UP"].tolist() == ["40"]
    assert removed[REASON_COLUMN].tolist() == ["CROSS_UP 소수 기록"]
    assert counts["CROSS_UP 소수 기록"] == 1


def test_remove_outliers_drops_cardio_over_limit():
    """심폐지구력이 상한(CARDIO_MAX)을 넘는 행만 제거하고, 상한과 같은 값은 남기는지 확인합니다."""
    # 실제 데이터의 96.5는 스텝검사 회복기 심박수로 계산하면 약 50이 나오는 입력 오류였다.
    df = pd.DataFrame({"CARDIO": [f"{CARDIO_MAX:g}", "96.5"], "CROSS_UP": ["40", "41"]})
    kept, removed, counts = remove_outliers(df)
    assert kept["CARDIO"].tolist() == [f"{CARDIO_MAX:g}"]
    assert removed[REASON_COLUMN].tolist() == [f"CARDIO {CARDIO_MAX:g} 초과"]
    assert counts[f"CARDIO {CARDIO_MAX:g} 초과"] == 1


def test_remove_outliers_lists_every_matched_rule():
    """한 행이 여러 이상치 규칙에 걸리면 사유를 모두 적는지 확인합니다."""
    df = pd.DataFrame({"CARDIO": ["96.5"], "CROSS_UP": ["40.5"]})
    _, removed, _ = remove_outliers(df)
    assert removed[REASON_COLUMN].tolist() == [f"CROSS_UP 소수 기록; CARDIO {CARDIO_MAX:g} 초과"]
