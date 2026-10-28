"""운동 처방 상세 테이블을 만들고(build_prescription_details), 처방 행에 처방유형번호를 붙이는(apply_refined_definition) 함수를 확인합니다."""

import pandas as pd
import pytest

from data.scripts.preprocessing.apply_refined_definition import (
    MESURE_ID_COLUMN,
    PRESCRIPTION_ID_COLUMN,
    map_prescription_types,
)
from data.scripts.preprocessing.build_prescription_details import (
    PRESCRIPTION_COLUMN,
    PRESCRIPTION_TYPE_ID_COLUMN,
    build_prescription_types,
)


def make_items() -> pd.DataFrame:
    """측정 2건에 처방 4개(그중 '팔굽혀펴기'가 두 번)가 있는 처방 행을 만듭니다."""
    return pd.DataFrame({
        PRESCRIPTION_ID_COLUMN: [1, 2, 3, 4],
        MESURE_ID_COLUMN: [1, 1, 2, 2],
        PRESCRIPTION_COLUMN: ["팔굽혀펴기", "걷기", "팔굽혀펴기", "달리기"],
    })


def test_build_prescription_types_lists_each_name_once():
    """처방 목록에서 서로 다른 이름마다 처방 유형이 하나씩, 번호 1부터 빈틈없이 만들어지는지 확인합니다."""
    # 번호 순서에는 의미가 없으므로(사용자 결정) 어떤 이름이 몇 번인지는 확인하지 않는다.
    lists = pd.Series(["팔굽혀펴기,걷기", " 걷기 , 달리기,", ""])
    types = build_prescription_types(lists)
    assert sorted(types[PRESCRIPTION_COLUMN]) == ["걷기", "달리기", "팔굽혀펴기"]
    assert sorted(types[PRESCRIPTION_TYPE_ID_COLUMN]) == [1, 2, 3]


def test_map_prescription_types_replaces_name_with_id():
    """처방 행의 이름이 상세 테이블의 처방유형번호로 바뀌고, 다른 컬럼과 행 순서는 그대로인지 확인합니다."""
    types = pd.DataFrame({PRESCRIPTION_TYPE_ID_COLUMN: [7, 8, 9], PRESCRIPTION_COLUMN: ["걷기", "달리기", "팔굽혀펴기"]})
    typed = map_prescription_types(make_items(), types)
    assert PRESCRIPTION_COLUMN not in typed.columns
    assert typed[PRESCRIPTION_ID_COLUMN].tolist() == [1, 2, 3, 4]
    # 번호를 새로 매기지 않고 상세 테이블의 번호를 그대로 쓴다.
    assert typed[PRESCRIPTION_TYPE_ID_COLUMN].tolist() == [9, 7, 9, 8]


def test_map_prescription_types_round_trips_names():
    """상세 테이블로 만든 번호를 다시 이으면 원래 처방 이름이 그대로 나오는지 확인합니다."""
    items = make_items()
    types = build_prescription_types(pd.Series(["달리기,걷기", "팔굽혀펴기"]))
    typed = map_prescription_types(items, types)
    restored = typed.merge(types, on=PRESCRIPTION_TYPE_ID_COLUMN, how="left")
    assert restored[PRESCRIPTION_COLUMN].tolist() == items[PRESCRIPTION_COLUMN].tolist()


def test_map_prescription_types_rejects_unknown_name():
    """상세 테이블에 없는 처방 이름이 있으면 오류를 내는지 확인합니다."""
    # 상세 테이블은 걸러 내기 전 전체 데이터로 만들므로, 모르는 이름은 단계 순서나 입력이 어긋났다는 뜻이다.
    types = pd.DataFrame({PRESCRIPTION_TYPE_ID_COLUMN: [1], PRESCRIPTION_COLUMN: ["걷기"]})
    with pytest.raises(ValueError, match="없는 처방 이름"):
        map_prescription_types(make_items(), types)
