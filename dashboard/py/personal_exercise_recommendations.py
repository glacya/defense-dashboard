"""개인 체력유형의 등급·군집에 해당하는 추천 운동을 표시합니다."""

import pandas as pd
import streamlit as st

from config import DASHBOARD_DIR, PROCESSED_DIR
from data.scripts.utils import require_columns


def load_recommendation(grade: int, cluster: int) -> pd.DataFrame:
    """군집 번호 대신 등급과 군집의 조합으로 추천을 연결합니다."""
    data = pd.read_csv(PROCESSED_DIR / 'FITNESS_TYPE_EXERCISE_RECOMMENDATIONS3.csv')
    require_columns(data, ['AVERAGE_PERCENTILE_GRADE', 'CLUSTER',
                          'IMPROVEMENT_FOCUS', 'RECOMMENDED_EXERCISE',
                          'TRAINING_GUIDANCE',
                          'RECOMMENDATION_BASIS', 'SOURCE_URL'])
    for column in ['AVERAGE_PERCENTILE_GRADE', 'CLUSTER']:
        data[column] = pd.to_numeric(data[column], errors='raise')
    if data.duplicated(['AVERAGE_PERCENTILE_GRADE', 'CLUSTER',
                        'IMPROVEMENT_FOCUS', 'RECOMMENDED_EXERCISE']).any():
        raise ValueError('같은 등급·군집의 추천 운동이 중복되었습니다.')
    selected = data.loc[data.AVERAGE_PERCENTILE_GRADE.eq(grade) & data.CLUSTER.eq(cluster)]
    if selected.empty:
        return selected
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
    except (OSError, ValueError, KeyError, pd.errors.EmptyDataError) as error:
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
    with st.expander('운동 추천 참고 자료'):
        urls = dict.fromkeys(url.strip() for sources in recommendation.SOURCE_URL
                             for url in sources.split('|') if url.strip())
        for index, url in enumerate(urls, start=1):
            st.markdown(f'[일반 운동 지침 {index}]({url})')
