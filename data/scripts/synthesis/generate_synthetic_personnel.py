"""가상 장병 명단(군번·이름·지역·부대·계급·전후방 구분)을 만듭니다.

전처리된 측정 데이터의 회원(M_CODE) 한 명당 장병 한 명을 만들고, SOLDIER_PERSONNEL_DEFINITION.csv 구성으로 저장합니다.
장병과 회원(측정)은 다음 단계(link_fitness_and_injury_risk)에서 연결합니다.
"""

import argparse
import logging
import random
from pathlib import Path

import numpy as np
import pandas as pd

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import (
    DEFINITION_SOLDIER_PERSONNEL,
    INTERMEDIATE_REFINED,
    SYNTHETIC_PERSONNEL_PATH,
)
from data.scripts.utils import positive_int, read_text_csv, write_by_definition

logger = logging.getLogger(__name__)

# 군번·이름·속성을 매번 같게 만들려고 기본 시드를 둔다. None을 주면 실행할 때마다 달라진다.
DEFAULT_SEED = 42
MEMBER_ID_COLUMN = "M_CODE"

# 지역별 가중치. 전방 지역(경기·강원·서울·인천)에 장병이 많도록 9:1로 둔다.
# 이렇게 가중치를 부여하면 (전방 총합):(후방 총합) = 36:12 = 3:1 로 원하는 비율이 된다.
REGION_WEIGHTS = {
    "경기도": 9,
    "강원특별자치도": 9,
    "서울특별시": 9,
    "인천광역시": 9,
    "충청북도": 1,
    "충청남도": 1,
    "전북특별자치도": 1,
    "전남광주통합특별시": 1,
    "경상북도": 1,
    "경상남도": 1,
    "대전광역시": 1,
    "대구광역시": 1,
    "울산광역시": 1,
    "부산광역시": 1,
    "세종특별자치시": 1,
    "제주특별자치도": 1,
}
REGIONS = list(REGION_WEIGHTS)
REGION_PROBABILITIES = np.array(list(REGION_WEIGHTS.values()), dtype=float)
REGION_PROBABILITIES /= REGION_PROBABILITIES.sum()

UNITS_BY_REGION = {
    "경기도": ["경기_1사단", "경기_5사단", "경기_9사단"],
    "강원특별자치도": ["강원_2사단", "강원_7사단", "강원_12사단"],
    "서울특별시": ["수방사_1부대", "수방사_2부대"],
    "인천광역시": ["인천_17사단"],
    "충청북도": ["충북_37사단"],
    "충청남도": ["충남_32사단"],
    "전북특별자치도": ["전북_35사단"],
    "전남광주통합특별시": ["전남_31사단"],
    "경상북도": ["경북_45사단"],
    "경상남도": ["경남_39사단"],
    "대전광역시": ["대전_군수사"],
    "대구광역시": ["대구_50사단"],
    "울산광역시": ["울산_55사단"],
    "부산광역시": ["부산_53사단"],
    "세종특별자치시": ["세종_자운대"],
    "제주특별자치도": ["제주_9여단"],
}
FRONT_REGIONS = ("경기도", "강원특별자치도", "서울특별시", "인천광역시")

RANKS = ["이병", "일병", "상병", "병장"]
RANK_WEIGHTS = [2.5, 6.0, 6.0, 3.5]
RANK_PROBABILITIES = np.array(RANK_WEIGHTS) / sum(RANK_WEIGHTS)
# 메모: 계급별 복무 개월 수를 무작위로 주던 함수(assign_month_group)가 있었다.
#   이병 1~3, 일병 4~9, 상병 10~15, 병장 16~18개월. 기대 부상 건수를 복무 기간(노출 기간)에
#   비례하게 바꿀 때 다시 쓸 수 있다(이전 코드는 git 기록 참고).

LAST_NAMES = (
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "류", "전",
    "홍", "고", "문", "양", "손", "배", "백", "허", "유", "남",
    "심", "노", "하", "곽", "성", "차", "주", "우",
    "남궁", "황보", "제갈", "사공", "선우", "서문", "독고",
)
FIRST_NAME_SYLLABLES = (
    "강", "건", "경", "고", "관", "나", "남", "노", "누", "다",
    "단", "담", "대", "덕", "도", "동", "라", "래", "로", "루",
    "마", "만", "명", "무", "문", "미", "민", "백", "범", "별",
    "병", "보", "빛", "사", "산", "상", "새", "서", "석", "선",
    "아", "안", "애", "우", "영", "예", "오", "옥", "완", "은",
    "진", "장", "재", "전", "정", "조", "종", "주", "준", "지",
    "찬", "창", "채", "천", "철", "초", "춘", "복", "치", "탐",
    "태", "택", "하", "한", "해", "혁", "현", "환", "혜", "호",
)


def generate_name(rng: random.Random) -> str:
    """성 하나와 이름 두 글자로 된 가상 이름을 만듭니다."""
    return rng.choice(LAST_NAMES) + "".join(rng.sample(FIRST_NAME_SYLLABLES, 2))


def generate_service_numbers(count: int, rng: random.Random) -> list[str]:
    """'입대연도 두 자리-아홉 자리 번호' 형식의 서로 다른 군번을 만든 순서대로 반환합니다."""
    numbers: list[str] = []
    seen: set[str] = set()
    while len(numbers) < count:
        number = f"{rng.randint(22, 26)}-{rng.randint(0, 999_999_999):09d}"
        if number not in seen:
            seen.add(number)
            numbers.append(number)
    return numbers


def assign_personnel_attributes(df_personnel: pd.DataFrame, seed: int | None = DEFAULT_SEED) -> pd.DataFrame:
    """장병에게 지역·부대·계급·전후방 구분을 가중치에 따라 부여합니다."""
    rng = np.random.default_rng(seed)
    python_rng = random.Random(seed)
    regions = rng.choice(REGIONS, size=len(df_personnel), p=REGION_PROBABILITIES)
    result = df_personnel.copy()
    result["REGION_NAME"] = regions
    result["UNIT_NAME"] = [python_rng.choice(UNITS_BY_REGION[region]) for region in regions]
    result["RANK_NAME"] = rng.choice(RANKS, size=len(df_personnel), p=RANK_PROBABILITIES)
    result["FRONT_REAR_CLASSIFICATION"] = np.where(
        result["REGION_NAME"].isin(FRONT_REGIONS), "전방", "후방"
    )
    return result


def generate_personnel_data(count: int, seed: int | None = DEFAULT_SEED) -> pd.DataFrame:
    """가상 장병 count명의 군번·이름과 지역·부대·계급·전후방 구분을 만듭니다.

    Raises:
        ValueError: count가 1보다 작을 때
    """
    if count < 1:
        raise ValueError("count는 1 이상의 정수여야 합니다.")
    rng = random.Random(seed)
    personnel = pd.DataFrame({
        "SOLDIER_ID": generate_service_numbers(count, rng),
        "SOLDIER_NAME": [generate_name(rng) for _ in range(count)],
    })
    return assign_personnel_attributes(personnel, seed)


def count_members(fitness: pd.DataFrame) -> int:
    """측정 데이터의 회원(M_CODE) 수를 셉니다.

    Raises:
        ValueError: 데이터가 비었거나 M_CODE가 빈 행이 있을 때
    """
    if fitness.empty:
        raise ValueError("체력 측정 데이터가 비어 있습니다.")
    if fitness[MEMBER_ID_COLUMN].str.strip().eq("").any():
        raise ValueError("체력 데이터의 M_CODE는 비어 있으면 안 됩니다.")
    return fitness[MEMBER_ID_COLUMN].nunique()


def run(
    fitness_path: Path,
    definition_path: Path,
    output_path: Path,
    count: int | None = None,
    seed: int | None = DEFAULT_SEED,
) -> None:
    """가상 장병 명단을 만들어 정의서 컬럼 순서대로 저장합니다.

    Args:
        fitness_path: 전처리된 측정 데이터(REFINED). count가 없으면 이 데이터의 회원 수만큼 만든다
        definition_path: 장병 명단 정의서 (SOLDIER_PERSONNEL_DEFINITION.csv)
        output_path: 장병 명단 저장 경로
        count: 만들 장병 수
        seed: 난수 시드. None이면 실행할 때마다 다른 명단을 만든다
    """
    if count is None:
        count = count_members(read_text_csv(fitness_path))
    personnel = generate_personnel_data(count, seed)
    write_by_definition(personnel, definition_path, output_path)
    logger.info("가상 장병 %s명 생성 (시드 %s)", f"{len(personnel):,}", seed)
    logger.info("저장: %s", display_path(output_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 이 단계만 실행합니다."""
    parser = argparse.ArgumentParser(description="가상 장병 명단을 만듭니다.")
    parser.add_argument(
        "-n", "--count", type=positive_int, default=None,
        help="만들 장병 수 (기본: 전처리된 측정 데이터의 회원 수)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"난수 시드 (기본값: {DEFAULT_SEED})")
    args = parser.parse_args()

    setup_logging(caller_name(__file__))
    run(INTERMEDIATE_REFINED, DEFINITION_SOLDIER_PERSONNEL, SYNTHETIC_PERSONNEL_PATH, args.count, args.seed)


if __name__ == "__main__":
    main()
