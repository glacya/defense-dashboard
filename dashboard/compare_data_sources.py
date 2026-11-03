"""대시보드 로더의 CSV 모드와 DB 모드 결과가 같은지 비교합니다(전환 기간용, 단독 실행).

실제 DB(dashboard/.env)에 접속해 읽기만 합니다. 테스트(CI)에서는 실행하지 않습니다.
비교 기준:
- DataFrame은 행 순서와 값을 비교하고, 실수는 상대 오차 1e-9까지 같다고 봅니다.
- DB 결과의 컬럼은 모두 CSV 결과에 있어야 합니다. DB 모드에서 뺀 컬럼(판정 불가 관련 등)은 CSV 쪽에서 무시하고
  DB 결과의 컬럼 순서로 비교합니다.
- 개인 프로필 백분위는 DB에 소수 둘째 자리로 저장하므로 절대 오차 0.005까지 같다고 봅니다.
- 문자열 컬럼의 pandas 타입(object와 string) 차이는 무시하고, 숫자·날짜 타입은 같아야 합니다.
- dict(분석 설명)는 생성일시를 빼고 비교합니다.
CSV 모드를 지울 때 이 파일도 함께 지웁니다.

실행: python dashboard/compare_data_sources.py [로더 이름 ...]
"""

import argparse
import logging
import sys
from collections.abc import Callable
from typing import Any

import pandas as pd

from dashboard.data_source import CSV, DB
from dashboard.main_data import load_main_data
from dashboard.py.fitness_overview_data import load_group_summary, load_overview
from dashboard.py.followup_fitness_types import load_fitness_types
from dashboard.py.followup_probability import load_probabilities
from dashboard.py.injury_overview_data import load_injury_overview
from dashboard.py.management_targets_data import load_targets
from dashboard.py.personal_detail_data import load_personal
from dashboard.py.personal_exercise_recommendations import load_recommendation
from dashboard.py.personal_fitness_profile import load_profiles
from dashboard.py.roster_data import load_injuries_text, load_latest_measurements, load_personnel_text

logger = logging.getLogger(__name__)

# 생성일시는 실행할 때마다 달라지고, 입력측정·입력명단(CSV 파일 경로)은 DB 모드에 없으며 화면에서 쓰지 않는다.
IGNORED_KEYS = {"생성일시", "입력측정", "입력명단"}
RTOL = 1e-9
ATOL = {"personal_fitness_profile.load_profiles": 0.005}  # 로더별 절대 오차(없으면 0)
# 행 순서에 의미가 없는 로더는 이 컬럼으로 정렬한 뒤 비교한다(CSV 명단은 생성 순서, DB에는 그 순서가 없음).
SORT_KEYS = {
    "roster_data.load_personnel_text": ["SOLDIER_ID"],
    "injury_overview_data.load_injury_overview": ["SOLDIER_ID"],
}


def _all_recommendations(source: str) -> pd.DataFrame:
    # 16개 유형(등급 1~4 × 군집 0~3)의 추천을 모두 이어 비교한다.
    return pd.concat([load_recommendation(grade, cluster, source) for grade in range(1, 5) for cluster in range(4)],
                     ignore_index=True)


def _fitness_types(source: str) -> Any:
    # 두 모드에 같은 장병 입력을 넣어 분류 표 읽기만 비교한다.
    measurements, _ = load_main_data(CSV)
    return load_fitness_types(measurements[["SOLDIER_ID", "MESURE_ID"]], source)


LOADERS: dict[str, Callable[[str], Any]] = {
    "main_data.load_main_data": load_main_data,
    "followup_fitness_types.load_fitness_types": _fitness_types,
    "followup_probability.load_probabilities": load_probabilities,
    "personal_fitness_profile.load_profiles": load_profiles,
    "roster_data.load_personnel_text": load_personnel_text,
    "roster_data.load_injuries_text": load_injuries_text,
    "roster_data.load_latest_measurements": load_latest_measurements,
    "fitness_overview_data.load_overview": load_overview,
    "fitness_overview_data.load_group_summary(REGION_NAME)": lambda source: load_group_summary("REGION_NAME", source),
    "fitness_overview_data.load_group_summary(UNIT_NAME)": lambda source: load_group_summary("UNIT_NAME", source),
    "management_targets_data.load_targets": load_targets,
    "personal_detail_data.load_personal": load_personal,
    "injury_overview_data.load_injury_overview": load_injury_overview,
    "personal_exercise_recommendations.load_recommendation(16개 유형)": _all_recommendations,
}


def _sorted(result: Any, keys: list[str]) -> Any:
    if isinstance(result, pd.DataFrame) and set(keys) <= set(result.columns):
        return result.sort_values(keys, kind="stable")
    if isinstance(result, tuple):
        return tuple(_sorted(item, keys) for item in result)
    return result


def _text_as_object(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.reset_index(drop=True)
    for column in frame.columns:
        if pd.api.types.is_string_dtype(frame[column]):
            frame[column] = frame[column].astype(object).where(frame[column].notna(), None)
    return frame


def compare(expected: Any, actual: Any, where: str = "결과", atol: float = 0.0) -> None:
    """두 결과가 같은지 확인합니다.

    Raises:
        AssertionError: 다른 곳이 있을 때(위치를 메시지에 적음)
    """
    if isinstance(expected, pd.DataFrame):
        assert isinstance(actual, pd.DataFrame), f"{where}: DataFrame이 아님 ({type(actual).__name__})"
        extra = [column for column in actual.columns if column not in expected.columns]
        assert not extra, f"{where}: CSV 결과에 없는 컬럼 {extra}"
        try:
            pd.testing.assert_frame_equal(_text_as_object(expected[actual.columns]), _text_as_object(actual),
                                          rtol=RTOL, atol=atol)
        except AssertionError as error:
            raise AssertionError(f"{where}: {error}") from None
    elif isinstance(expected, pd.Series):
        pd.testing.assert_series_equal(expected, actual, rtol=RTOL, atol=atol, obj=where)
    elif isinstance(expected, (tuple, list)):
        assert len(expected) == len(actual), f"{where}: 길이 {len(expected)} != {len(actual)}"
        for index, (left, right) in enumerate(zip(expected, actual)):
            compare(left, right, f"{where}[{index}]", atol)
    elif isinstance(expected, dict):
        keys = set(expected) - IGNORED_KEYS
        assert keys == set(actual) - IGNORED_KEYS, f"{where}: 키 {sorted(keys ^ (set(actual) - IGNORED_KEYS))}"
        for key in sorted(keys):
            compare(expected[key], actual[key], f"{where}[{key!r}]", atol)
    else:
        assert expected == actual, f"{where}: {expected!r} != {actual!r}"


def run(names: list[str]) -> bool:
    """고른 로더를 두 모드로 실행해 비교하고, 모두 같으면 True를 돌려줍니다."""
    passed = True
    for name in names:
        try:
            expected, actual = LOADERS[name](CSV), LOADERS[name](DB)
            if name in SORT_KEYS:
                expected, actual = _sorted(expected, SORT_KEYS[name]), _sorted(actual, SORT_KEYS[name])
            compare(expected, actual, atol=ATOL.get(name, 0.0))
            logger.info("같음    %s", name)
        except Exception as error:  # 하나가 실패해도 나머지를 계속 비교한다.
            passed = False
            message = str(error).strip().splitlines()
            logger.error("다름    %s\n        %s", name, "\n        ".join(message[:12]))
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", choices=[[], *LOADERS], metavar="로더", help="생략하면 전부")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(0 if run(args.names or list(LOADERS)) else 1)


if __name__ == "__main__":
    main()
