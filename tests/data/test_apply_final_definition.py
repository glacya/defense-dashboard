"""최종 정의서 적용 단계에서 운동 처방을 처방 유형으로 나누는 함수를 확인합니다."""

import pandas as pd

from data.scripts.preprocessing.apply_final_definition import (
    MESURE_ID_COLUMN,
    PRESCRIPTION_COLUMN,
    PRESCRIPTION_ID_COLUMN,
    PRESCRIPTION_TYPE_ID_COLUMN,
    assign_prescription_types,
)


def make_items() -> pd.DataFrame:
    """측정 2건에 처방 4개(그중 '팔굽혀펴기'가 두 번)가 있는 처방 행을 만듭니다."""
    return pd.DataFrame({
        PRESCRIPTION_ID_COLUMN: [1, 2, 3, 4],
        MESURE_ID_COLUMN: [1, 1, 2, 2],
        PRESCRIPTION_COLUMN: ["팔굽혀펴기", "걷기", "팔굽혀펴기", "달리기"],
    })


def test_assign_prescription_types_lists_each_name_once():
    """서로 다른 처방 이름마다 처방 유형이 하나씩, 번호 1부터 빈틈없이 만들어지는지 확인합니다."""
    # 번호 순서에는 의미가 없으므로(사용자 결정) 어떤 이름이 몇 번인지는 확인하지 않는다.
    types, _ = assign_prescription_types(make_items())
    assert sorted(types[PRESCRIPTION_COLUMN]) == ["걷기", "달리기", "팔굽혀펴기"]
    assert sorted(types[PRESCRIPTION_TYPE_ID_COLUMN]) == [1, 2, 3]


def test_assign_prescription_types_replaces_name_with_id():
    """처방 행의 이름이 처방유형번호로 바뀌고, 같은 이름은 같은 번호를 받으며 행 순서는 그대로인지 확인합니다."""
    _, typed = assign_prescription_types(make_items())
    assert PRESCRIPTION_COLUMN not in typed.columns
    assert typed[PRESCRIPTION_ID_COLUMN].tolist() == [1, 2, 3, 4]
    type_ids = typed[PRESCRIPTION_TYPE_ID_COLUMN].tolist()
    # 1번째와 3번째 행이 모두 '팔굽혀펴기'다.
    assert type_ids[0] == type_ids[2]
    assert len(set(type_ids)) == 3


def test_assign_prescription_types_round_trips_names():
    """처방유형번호로 유형 표와 다시 이으면 원래 처방 이름이 그대로 나오는지 확인합니다."""
    items = make_items()
    types, typed = assign_prescription_types(items)
    restored = typed.merge(types, on=PRESCRIPTION_TYPE_ID_COLUMN, how="left")
    assert restored[PRESCRIPTION_COLUMN].tolist() == items[PRESCRIPTION_COLUMN].tolist()
