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
COLUMNS = [*KEYS, 'RECOMMENDATION_RANK', 'TYPE_NAME', 'IMPROVEMENT_FOCUS', 'RECOMMENDED_EXERCISE', 'BODY_PARTS', 'RELATIVE_GAP']
# 체력 요소에 맞는 유형의 상대 편차(fitness_types의 {종목}_relative). 요소 이름은 코드 상수라 SQL에 넣어도 안전하다.
_GAP_CASES = ' '.join(f"WHEN '{focus}' THEN t.{relative_column(focus).lower()}" for focus in FOCUSES)
RECOMMENDATION_SQL = f"""
SELECT r.average_percentile_grade, r.cluster, r.recommendation_rank, t.type_name,
    c.improvement_focus, d.prescription AS recommended_exercise,
    (SELECT string_agg(b.body_part, ' | ' ORDER BY b.body_part)
     FROM exercise_body_parts b WHERE b.prescription_type_id = r.prescription_type_id) AS body_parts,
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
    from data.scripts.paths import PROCESSED_EXERCISE_BODY_PART_PATH
    parts = pd.read_csv(PROCESSED_EXERCISE_BODY_PART_PATH, encoding='utf-8-sig')
    parts = parts.groupby('PRESCRIPTION_TYPE_ID')['BODY_PART'].agg(lambda values: ' | '.join(sorted(set(values)))).rename('BODY_PARTS').reset_index()
    data = (recommendations.merge(types, on=KEYS, validate='many_to_one')
            .merge(classifications, on='PRESCRIPTION_TYPE_ID', validate='many_to_one')
            .merge(details, on='PRESCRIPTION_TYPE_ID', validate='many_to_one')
            .merge(parts, on='PRESCRIPTION_TYPE_ID', how='left', validate='many_to_one')
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
    from data.scripts.paths import PROCESSED_EXERCISE_BODY_PART_PATH
    paths.append(PROCESSED_EXERCISE_BODY_PART_PATH)
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
    except (OSError, ValueError, KeyError, pd.errors.EmptyDataError, SQLAlchemyError) as error:
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
            st.dataframe(excluded[['RECOMMENDED_EXERCISE', 'EXCLUSION_REASON']].rename(
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
