"""가상 데이터 합성 단계의 실행 순서와 입출력 연결을 정합니다.

합성은 전처리가 끝난 데이터를 바탕으로 하므로 전처리 다음에 실행합니다.
"""

from data.scripts.pipeline import Step

TITLE = "가상 데이터 합성"


def build_steps() -> list[Step]:
    """실행 순서대로 합성 단계 목록을 만듭니다."""
    # TODO: generate_synthetic_personnels·generate_synthetic_injuries는 아직 이전 구조(경로 직접 지정, run(입력, 출력) 없음)라
    # 단계 형식으로 정비한 뒤 여기에 추가한다.
    return []
