"""개인 체력유형의 등급·군집에 해당하는 추천 운동을 표시합니다.

추천 운동은 분석 단계(build_exercise_recommendations)가 저장한 표를 읽습니다.
recommended_exercises에 유형(fitness_types)·운동 분류(exercise_classifications)·
처방 이름(exercise_prescription_details)·사용 부위(exercise_body_parts)를 JOIN합니다.
운동 지침·추천 근거 문장은 DB에 저장하지 않고 읽은 값과 fitness_standards.TARGET_DIFFICULTY로 만듭니다.
"""

import pandas as pd
import streamlit as st

from dashboard.common.table_widgets import render_dataframe
from sqlalchemy.exc import SQLAlchemyError

from dashboard.db import DEFAULT_TTL, run_query
from fitness_standards import TARGET_DIFFICULTY

SOURCE_URL = "https://nfa.kspo.or.kr/"
WEAK_SUFFIX = "약점형"  # 유형명 끝이 '○○ 약점형'이면 그 요소 운동만 추천한다(아니면 '○○ 강점형')
RECOMMENDATION_SQL = """
SELECT r.average_percentile_grade, r.cluster, r.recommendation_rank, t.type_name,
    c.improvement_focus, d.prescription AS recommended_exercise,
    (SELECT string_agg(b.body_part, ' | ' ORDER BY b.body_part)
     FROM exercise_body_parts b WHERE b.prescription_type_id = r.prescription_type_id) AS body_parts,
    CASE c.improvement_focus
        WHEN '근력' THEN t.strength_relative
        WHEN '근지구력' THEN t.endurance_relative
        WHEN '심폐지구력' THEN t.cardio_relative
        WHEN '유연성' THEN t.flexibility_relative
    END AS relative_gap
FROM recommended_exercises r
JOIN fitness_types t USING (average_percentile_grade, cluster)
JOIN exercise_classifications c USING (prescription_type_id)
JOIN exercise_prescription_details d USING (prescription_type_id)
WHERE r.average_percentile_grade = :grade AND r.cluster = :cluster
ORDER BY r.recommendation_rank
"""


def training_guidance(grade: int) -> str:
    """등급별 운동 지침 문장입니다."""
    return (f"{grade}등급 기준 동작 난이도 {TARGET_DIFFICULTY[grade]}에 가까운 운동 우선. "
            "개인별 수행 수준에 맞춰 강도와 반복량을 조절합니다.")


def allocation_text(selected: pd.DataFrame) -> str:
    """유형의 추천 운동이 체력 요소별로 몇 개씩인지 설명합니다(예: '4/2/2개 배분')."""
    if selected.TYPE_NAME.iloc[0].endswith(WEAK_SUFFIX):
        return f"유형에 명시된 약점 요소 운동 {len(selected)}개"
    counts = selected.IMPROVEMENT_FOCUS.value_counts().sort_values(ascending=False)
    return f"강점 요소 제외 후 상대 편차가 낮은 순 {'/'.join(map(str, counts))}개 배분"


def load_recommendation(grade: int, cluster: int) -> pd.DataFrame:
    """등급과 군집의 조합에 해당하는 추천 운동(순위 순)과 운동 지침·추천 근거 문장을 돌려줍니다."""
    selected = run_query(RECOMMENDATION_SQL, {'grade': int(grade), 'cluster': int(cluster)}, ttl=DEFAULT_TTL)
    if selected.empty:
        return selected
    allocation = allocation_text(selected)
    return selected.assign(
        TRAINING_GUIDANCE=selected.AVERAGE_PERCENTILE_GRADE.map(training_guidance),
        RECOMMENDATION_BASIS=[f"{row.AVERAGE_PERCENTILE_GRADE}등급 군집 {row.CLUSTER}: {row.IMPROVEMENT_FOCUS} "
                              f"상대 편차 {row.RELATIVE_GAP:+.2f}%p; {allocation}. 등급별 난이도는 수동 규칙입니다."
                              for row in selected.itertuples()],
        SOURCE_URL=SOURCE_URL,
    )


def split_by_injuries(recommendation: pd.DataFrame, injuries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """전체 부상 이력의 부위와 사용 부위가 겹치는 운동을 분리합니다."""
    locations = set(injuries['INJURY_LOCATION'].dropna().astype(str).str.strip()) if not injuries.empty else set()
    result = recommendation.copy()
    result['EXCLUSION_REASON'] = result.BODY_PARTS.map(
        lambda parts: ' | '.join(sorted(locations & {part.strip() for part in parts.split('|')})))
    excluded = result.EXCLUSION_REASON.ne('')
    return result.loc[~excluded].copy(), result.loc[excluded].copy()


def render_recommendation(grade: int, cluster: int, injuries: pd.DataFrame | None = None,
                          injury_present: bool = True) -> None:
    """유형에 지정된 각 약점의 보완 운동과 실행 지침을 표시합니다."""
    st.markdown('### 체력유형별 운동 추천')
    try:
        recommendation = load_recommendation(grade, cluster)
    except SQLAlchemyError as error:
        st.info(f'운동 추천 자료를 확인할 수 없습니다: {error}')
        return
    if recommendation.empty:
        st.info('선택한 체력유형의 운동 추천 정보가 없습니다.')
        return
    if not injury_present:
        st.warning('부상 자료가 없어 부상 부위에 따른 운동 제외를 적용하지 못했습니다.')
    allowed, excluded = split_by_injuries(recommendation, injuries if injuries is not None else pd.DataFrame())
    allowed = allowed.sort_values('RECOMMENDATION_RANK', kind='stable').head(4)
    st.caption('전체 부상 이력과 사용 부위가 겹치는 운동을 제외합니다. 현재 회복 여부를 판정한 결과는 아닙니다.')
    available_panel, excluded_panel = st.columns([1.4, 1], gap='medium')
    with excluded_panel:
        st.markdown(f'#### 제외된 운동 · {len(excluded)}개')
        if excluded.empty:
            st.caption('부상 부위와 겹쳐 제외된 운동이 없습니다.' if injury_present else '부상 자료 확인이 필요합니다.')
        else:
            render_dataframe(excluded[['RECOMMENDED_EXERCISE', 'EXCLUSION_REASON']].rename(
                columns={'RECOMMENDED_EXERCISE': '운동명', 'EXCLUSION_REASON': '겹친 부상 부위'}),
                hide_index=True, width='stretch')
    with available_panel:
        st.markdown(f'#### 추천 목록 · {len(allowed)}개')
        st.caption('부상 부위와 겹치는 운동을 제외한 뒤 추천 순위순으로 최대 4개를 표시합니다.')
        if allowed.empty:
            st.info('부상 부위와 겹쳐 추천 목록에 남은 운동이 없습니다.')
        for focus, exercises in allowed.groupby('IMPROVEMENT_FOCUS', sort=False):
            st.markdown(f'**{focus}**')
            for exercise in exercises.itertuples():
                st.markdown(f'- {exercise.RECOMMENDED_EXERCISE}')
        for instruction in allowed.TRAINING_GUIDANCE.drop_duplicates():
            st.write(instruction)
    for basis in allowed.RECOMMENDATION_BASIS.drop_duplicates():
        st.caption(basis)
    with st.container(border=True):
        st.markdown('**운동 추천의 한계점**')
        st.markdown(
            '국민체력100 데이터의 운동처방 자료를 기준으로, 16개 체력유형의 등급과 '
            '종목별 체력 편차 정보를 AI에 제공하여 운동을 분류했습니다. '
            'AI가 분류한 기준을 코드에 반영한 추천으로, 개인별 운동 효과나 적합성을 검증한 결과는 아닙니다.'
        )
