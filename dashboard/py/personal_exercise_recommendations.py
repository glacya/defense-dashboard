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
    with st.container(border=True):
        st.markdown('**운동 추천의 한계점**')
        st.markdown(
            '- 원본 처방 자료는 운동명 목록이며, 체력요소별 분류와 추천 연결은 수동으로 구성했습니다. '
            '실제 장병별 처방 이력이나 운동 효과를 분석한 결과는 아닙니다.\n'
            '- 강점형에서 강점 종목을 제외한 세 종목은 보완 대상으로 지정한 것이며, '
            '해당 종목이 실제 약점이거나 기준 미달이라는 뜻은 아닙니다.\n'
            '- 부상·질환·통증·회복 상태와 개인별 운동 경험을 반영하지 않았습니다. '
            '개인별 운동 적합성은 별도로 확인해야 합니다.\n'
            '- 별도 장비가 없는 운동을 선정했으나, 부대별 공간·바닥 상태·훈련 일정·'
            '기상 여건에 따라 실시 가능 여부가 달라집니다.\n'
            '- 안내는 일반 지침이며, 개인별 횟수·세트·강도·휴식·진행 계획은 제공하지 않습니다.'
        )
    with st.expander('운동 추천 참고 자료'):
        urls = dict.fromkeys(url.strip() for sources in recommendation.SOURCE_URL
                             for url in sources.split('|') if url.strip())
        for index, url in enumerate(urls, start=1):
            st.markdown(f'[일반 운동 지침 {index}]({url})')
