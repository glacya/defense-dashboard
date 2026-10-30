"""개인 체력유형의 등급·군집에 해당하는 추천 운동을 표시합니다.

추천 운동은 분석 단계(build_exercise_recommendations)가 저장한 표를 읽습니다.
DB 모드는 recommended_exercises에 유형(fitness_types)·운동 분류(exercise_classifications)·
처방 이름(exercise_prescription_details)을 JOIN하고, CSV 모드는 같은 CSV들을 pandas로 잇습니다.
운동 지침·추천 근거 문장은 저장하지 않고 분석 단계와 같은 함수로 만듭니다.
"""

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from config import DASHBOARD_DIR
from dashboard.data_source import CSV, resolve_source
from dashboard.db import DEFAULT_TTL, run_query
from data.scripts.analysis.clustering.build_exercise_recommendations import (
    FOCUSES, SOURCE_URL, recommendation_basis, relative_column, training_guidance)
from data.scripts.utils import require_columns

KEYS = ['AVERAGE_PERCENTILE_GRADE', 'CLUSTER']
COLUMNS = [*KEYS, 'RECOMMENDATION_RANK', 'TYPE_NAME', 'IMPROVEMENT_FOCUS', 'RECOMMENDED_EXERCISE', 'RELATIVE_GAP']
# 체력 요소에 맞는 유형의 상대 편차(fitness_types의 {종목}_relative). 요소 이름은 코드 상수라 SQL에 넣어도 안전하다.
_GAP_CASES = ' '.join(f"WHEN '{focus}' THEN t.{relative_column(focus).lower()}" for focus in FOCUSES)
RECOMMENDATION_SQL = f"""
SELECT r.average_percentile_grade, r.cluster, r.recommendation_rank, t.type_name,
    c.improvement_focus, d.prescription AS recommended_exercise,
    CASE c.improvement_focus {_GAP_CASES} END AS relative_gap
FROM recommended_exercises r
JOIN fitness_types t USING (average_percentile_grade, cluster)
JOIN exercise_classifications c USING (prescription_type_id)
JOIN exercise_prescription_details d USING (prescription_type_id)
WHERE r.average_percentile_grade = :grade AND r.cluster = :cluster
ORDER BY r.recommendation_rank
"""


@st.cache_data(show_spinner=False)
def _read_tables(stamps: tuple[int, ...]) -> pd.DataFrame:
    """CSV 모드: 추천·유형·운동 분류·처방 이름을 이어 DB 모드와 같은 컬럼으로 만듭니다."""
    from data.scripts.paths import (PROCESSED_EXERCISE_CLASSIFICATION_PATH, PROCESSED_FITNESS_TYPE_PATH,
                                    PROCESSED_PRESCRIPTION_DETAIL_PATH, PROCESSED_RECOMMENDED_EXERCISE_PATH)
    recommendations = pd.read_csv(PROCESSED_RECOMMENDED_EXERCISE_PATH, encoding='utf-8-sig')
    types = pd.read_csv(PROCESSED_FITNESS_TYPE_PATH, encoding='utf-8-sig')
    classifications = pd.read_csv(PROCESSED_EXERCISE_CLASSIFICATION_PATH, encoding='utf-8-sig')
    details = pd.read_csv(PROCESSED_PRESCRIPTION_DETAIL_PATH, encoding='utf-8-sig')
    data = (recommendations.merge(types, on=KEYS, validate='many_to_one')
            .merge(classifications, on='PRESCRIPTION_TYPE_ID', validate='many_to_one')
            .merge(details, on='PRESCRIPTION_TYPE_ID', validate='many_to_one')
            .rename(columns={'PRESCRIPTION': 'RECOMMENDED_EXERCISE'}))
    data['RELATIVE_GAP'] = [row[relative_column(row.IMPROVEMENT_FOCUS)] for _, row in data.iterrows()]
    return data.sort_values([*KEYS, 'RECOMMENDATION_RANK'], kind='stable').reset_index(drop=True)[COLUMNS]


def _read_selected(grade: int, cluster: int, source: str) -> pd.DataFrame:
    if source != CSV:
        return run_query(RECOMMENDATION_SQL, {'grade': grade, 'cluster': cluster}, ttl=DEFAULT_TTL)[COLUMNS]
    from data.scripts.paths import (PROCESSED_EXERCISE_CLASSIFICATION_PATH, PROCESSED_FITNESS_TYPE_PATH,
                                    PROCESSED_PRESCRIPTION_DETAIL_PATH, PROCESSED_RECOMMENDED_EXERCISE_PATH)
    paths = [PROCESSED_RECOMMENDED_EXERCISE_PATH, PROCESSED_FITNESS_TYPE_PATH,
             PROCESSED_EXERCISE_CLASSIFICATION_PATH, PROCESSED_PRESCRIPTION_DETAIL_PATH]
    data = _read_tables(tuple(path.stat().st_mtime_ns for path in paths))
    return data.loc[data.AVERAGE_PERCENTILE_GRADE.eq(grade) & data.CLUSTER.eq(cluster)].reset_index(drop=True)


def load_recommendation(grade: int, cluster: int, source: str | None = None) -> pd.DataFrame:
    """등급과 군집의 조합에 해당하는 추천 운동(순위 순)과 운동 지침·추천 근거 문장을 돌려줍니다."""
    selected = _read_selected(int(grade), int(cluster), resolve_source(source))
    require_columns(selected, COLUMNS)
    if selected.duplicated([*KEYS, 'IMPROVEMENT_FOCUS', 'RECOMMENDED_EXERCISE']).any():
        raise ValueError('같은 등급·군집의 추천 운동이 중복되었습니다.')
    if selected.empty:
        return selected
    selected = selected.assign(
        TRAINING_GUIDANCE=selected.AVERAGE_PERCENTILE_GRADE.map(training_guidance),
        RECOMMENDATION_BASIS=[recommendation_basis(row.AVERAGE_PERCENTILE_GRADE, row.CLUSTER, row.IMPROVEMENT_FOCUS,
                                                   row.RELATIVE_GAP, row.TYPE_NAME) for row in selected.itertuples()],
        SOURCE_URL=SOURCE_URL,
    )
    if selected.isna().any().any() or selected.astype(str).apply(
        lambda column: column.str.strip().eq('').any()
    ).any():
        raise ValueError('선택 유형의 운동 추천 정보가 누락되었습니다.')
    return selected


def render_recommendation(grade: int, cluster: int) -> None:
    """유형에 지정된 각 약점의 보완 운동과 실행 지침을 표시합니다."""
    st.markdown('### 체력유형별 운동 추천')
    try:
        recommendation = load_recommendation(grade, cluster)
    except (OSError, ValueError, KeyError, pd.errors.EmptyDataError, SQLAlchemyError) as error:
        st.info(f'운동 추천 자료를 확인할 수 없습니다: {error}')
        return
    if recommendation.empty:
        st.info('선택한 체력유형의 운동 추천 정보가 없습니다.')
        return
    groups = list(recommendation.groupby('IMPROVEMENT_FOCUS', sort=False))
    st.caption('보완할 체력 요소: ' + ' · '.join(focus for focus, _ in groups))
    illustrations = {'근력': 'strength', '근지구력': 'endurance',
                     '심폐지구력': 'cardio', '유연성': 'flexibility'}
    for column, (focus, exercises) in zip(st.columns(len(groups)), groups):
        with column, st.container(border=True):
            image_name = illustrations.get(focus)
            if image_name:
                st.image(str(DASHBOARD_DIR / 'img' / f'exercise_{image_name}.svg'),
                         caption=f'{focus} 운동 예시', width=180)
            st.markdown(f'#### {focus} 기르기')
            for exercise in exercises.RECOMMENDED_EXERCISE:
                st.markdown(f'- {exercise}')
            st.markdown('**일반 운동 지침**')
            for instruction in exercises.TRAINING_GUIDANCE.drop_duplicates():
                st.write(instruction)
    for basis in recommendation.RECOMMENDATION_BASIS.drop_duplicates():
        st.caption(basis)
    with st.container(border=True):
        st.markdown('**운동 추천의 한계점**')
        st.markdown(
            '- 원본 처방 자료는 운동명 목록이며, 체력요소별 분류와 추천 연결은 수동으로 구성했습니다. '
            '실제 장병별 처방 이력이나 운동 효과를 분석한 결과는 아닙니다.\n'
            '- 약점형은 해당 요소의 운동 8개를, 강점형은 강점 외 세 요소에서 '
            '상대 체력 편차가 낮은 순으로 운동을 4·2·2개 배분합니다. '
            '상대 편차가 낮다는 것이 실제 기준 미달을 뜻하지는 않습니다.\n'
            '- 부상·질환·통증·회복 상태와 개인별 운동 경험을 반영하지 않았습니다. '
            '개인별 운동 적합성은 별도로 확인해야 합니다.\n'
            '- 운동에 따라 철봉·덤벨·운동기구 등이 필요하며, 부대별 공간·바닥 상태·훈련 일정·'
            '기상 여건에 따라 실시 가능 여부가 달라집니다.\n'
            '- 안내는 일반 지침이며, 개인별 횟수·세트·강도·휴식·진행 계획은 제공하지 않습니다.'
        )
    with st.expander('운동 추천 참고 자료'):
        urls = dict.fromkeys(url.strip() for sources in recommendation.SOURCE_URL
                             for url in sources.split('|') if url.strip())
        for index, url in enumerate(urls, start=1):
            st.markdown(f'[일반 운동 지침 {index}]({url})')
