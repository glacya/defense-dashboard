"""지역·부대·계급 카드 필터 공용 모듈 (dashboard/common/card_filters.py).

모든 페이지가 같은 모양·같은 동작의 필터를 쓰도록 하나로 모았습니다.
- 지역(왼쪽): 도 단위 카드 3열 (REGION_NAME을 경기·강원·전라·경상·충청·제주로 묶음)
- 부대(오른쪽): 지역 카드를 고르면 크기가 고정된 프레임 안에 (REGION_NAME, UNIT_NAME) 카드가 가로로 나열되고,
        내용이 넘치면 프레임 안에서 스크롤됩니다.
- 계급: RANK_ORDER 순서의 카드
- 아무것도 선택하지 않으면 해당 범위 전체를 뜻합니다.
- prefix가 같으면 페이지 사이에서 선택이 공유되고, 다르면 페이지마다 독립됩니다.

스타일은 이 파일이 아니라 전역 CSS의 "14. 카드 필터" 섹션에 있습니다.
요소는 key가 'cardfilter-{prefix}-...' 형태라 CSS 클래스(st-key-cardfilter-...)로 잡습니다.

people은 장병 1명당 1행이며 SOLDIER_ID, REGION_NAME, UNIT_NAME, RANK_NAME 컬럼이 필요합니다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from dashboard.common.formatting import RANK_ORDER, filter_signature

REGION_GROUP_ORDER = ['경기', '강원', '전라', '경상', '충청', '제주']
REGION_CARDS_PER_ROW = 3


@dataclass
class CardSelection:
    regions: list[str]               # 선택 범위의 REGION_NAME 목록 (미선택이면 전체)
    units: list[tuple[str, str]]     # 선택 범위의 (REGION_NAME, UNIT_NAME) 쌍
    ranks: list[str]                 # 선택 범위의 계급
    scoped: pd.DataFrame             # 조건에 맞는 people 행

    def unit_mask(self, frame: pd.DataFrame) -> pd.Series:
        """REGION_NAME·UNIT_NAME 컬럼이 있는 다른 표(예: 부상 기록)에 부대 조건을 적용합니다."""
        index = pd.MultiIndex.from_frame(frame[['REGION_NAME', 'UNIT_NAME']])
        return pd.Series(index.isin(self.units), index=frame.index)


def _keys(prefix: str) -> tuple[str, str, str]:
    return f'{prefix}_card_regions', f'{prefix}_card_units', f'{prefix}_card_ranks'


def reset_card_filters(prefix: str) -> None:
    """'전체 조회' 버튼용: 세 필터를 모두 비웁니다."""
    for key in _keys(prefix):
        st.session_state[key] = []


def _region_group(region_name: str) -> str:
    name = str(region_name)
    keywords = (
        ('전남광주', '전라'),
        ('서울', '경기'), ('인천', '경기'), ('경기', '경기'),
        ('강원', '강원'),
        ('충청북', '충청'), ('충북', '충청'), ('충청남', '충청'), ('충남', '충청'),
        ('대전', '충청'), ('세종', '충청'),
        ('전라북', '전라'), ('전북', '전라'), ('전라남', '전라'), ('전남', '전라'), ('광주', '전라'),
        ('경상북', '경상'), ('경북', '경상'), ('대구', '경상'),
        ('경상남', '경상'), ('경남', '경상'), ('부산', '경상'), ('울산', '경상'),
        ('제주', '제주'),
    )
    return next((label for keyword, label in keywords if keyword in name), name)


def _region_order(value: str) -> tuple[int, str]:
    return (REGION_GROUP_ORDER.index(value) if value in REGION_GROUP_ORDER else len(REGION_GROUP_ORDER), value)


def _toggle(key: str, value, reset_key: str | None = None) -> None:
    selected = list(st.session_state.get(key, []))
    if value in selected:
        selected.remove(value)
    else:
        selected.append(value)
    st.session_state[key] = selected
    if reset_key:
        st.session_state[reset_key] = []


def render_personnel_cards(
    people: pd.DataFrame,
    prefix: str,
    *,
    show_ranks: bool = True,
) -> CardSelection:
    """지역·부대(·계급) 카드를 그리고 선택 결과를 돌려줍니다."""
    region_key, unit_key, rank_key = _keys(prefix)
    scoped = people.assign(_REGION_GROUP=people['REGION_NAME'].map(_region_group))

    available_regions = sorted(scoped['_REGION_GROUP'].dropna().unique().tolist(), key=_region_order)
    selected_regions = [r for r in available_regions if r in st.session_state.get(region_key, [])]
    st.session_state[region_key] = selected_regions
    active_regions = selected_regions or available_regions
    source_regions = scoped.loc[scoped['_REGION_GROUP'].isin(active_regions), 'REGION_NAME'].dropna().unique().tolist()

    unit_pairs = sorted(
        map(tuple, scoped.loc[scoped['REGION_NAME'].isin(source_regions), ['REGION_NAME', 'UNIT_NAME']]
            .dropna().drop_duplicates().to_numpy().tolist())
    )
    selected_units = [tuple(u) for u in st.session_state.get(unit_key, []) if tuple(u) in unit_pairs]
    st.session_state[unit_key] = selected_units
    active_units = selected_units or unit_pairs

    ranks = [r for r in RANK_ORDER if r in scoped['RANK_NAME'].unique()] if show_ranks else []
    selected_ranks = [r for r in st.session_state.get(rank_key, []) if r in ranks]
    st.session_state[rank_key] = selected_ranks
    active_ranks = selected_ranks or ranks

    # 지역(왼쪽, 3열) + 부대(오른쪽, 고정 높이 프레임)
    left, right = st.columns([5, 7], gap='medium')
    with left:
        st.markdown('**지역**')
        region_counts = scoped.groupby('_REGION_GROUP')['SOLDIER_ID'].nunique().to_dict()
        for start in range(0, len(available_regions), REGION_CARDS_PER_ROW):
            for column, region in zip(st.columns(REGION_CARDS_PER_ROW, gap='small'),
                                      available_regions[start:start + REGION_CARDS_PER_ROW]):
                selected = region in selected_regions
                column.button(
                    f'{"✓ " if selected else ""}**{region}**  \n{int(region_counts.get(region, 0)):,}명',
                    key=f'cardfilter-{prefix}-region-card_{region}',
                    type='primary' if selected else 'secondary',
                    width='stretch', on_click=_toggle, args=(region_key, region, unit_key),
                )

    with right:
        st.markdown('**부대**')
        with st.container(horizontal=True, gap='small', key=f'cardfilter-{prefix}-unit-strip'):
            if not selected_regions:
                st.caption('지역을 선택하면 해당 지역의 부대가 표시됩니다. 선택하지 않으면 전체 부대입니다.')
            shown_regions = sorted(
                scoped.loc[scoped['_REGION_GROUP'].isin(selected_regions), 'REGION_NAME'].dropna().unique().tolist(),
                key=lambda name: (_region_order(_region_group(name)), name),
            )
            for region in shown_regions:
                in_region = scoped.loc[scoped['REGION_NAME'].eq(region)]
                counts = in_region.groupby('UNIT_NAME')['SOLDIER_ID'].nunique().to_dict()
                with st.container(border=True, key=f'cardfilter-{prefix}-unit-box_{filter_signature(region)}'):
                    st.caption(region)
                    for unit in sorted(in_region['UNIT_NAME'].dropna().unique().tolist()):
                        pair = (region, unit)
                        selected = pair in selected_units
                        st.button(
                            f'{"✓ " if selected else ""}{unit} · {int(counts.get(unit, 0)):,}명',
                            key=f'cardfilter-{prefix}-unit-card_{filter_signature(region, unit)}',
                            type='primary' if selected else 'secondary',
                            width='content', on_click=_toggle, args=(unit_key, pair),
                        )

    # 계급 (현재 지역·부대 범위 기준 인원수)
    if show_ranks:
        rank_base = scoped.loc[
            scoped['_REGION_GROUP'].isin(active_regions)
            & pd.MultiIndex.from_frame(scoped[['REGION_NAME', 'UNIT_NAME']]).isin(active_units)
        ]
        rank_counts = rank_base.groupby('RANK_NAME')['SOLDIER_ID'].nunique().to_dict()
        st.markdown('**계급**')
        with st.container(horizontal=True, gap='small', key=f'cardfilter-{prefix}-rank-row'):
            for rank in ranks:
                selected = rank in selected_ranks
                st.button(
                    f'{"✓ " if selected else ""}{rank} · {int(rank_counts.get(rank, 0)):,}명',
                    key=f'cardfilter-{prefix}-rank-card_{rank}',
                    type='primary' if selected else 'secondary',
                    width='content', on_click=_toggle, args=(rank_key, rank),
                )

    mask = (
        scoped['_REGION_GROUP'].isin(active_regions)
        & pd.MultiIndex.from_frame(scoped[['REGION_NAME', 'UNIT_NAME']]).isin(active_units)
    )
    if show_ranks:
        mask &= scoped['RANK_NAME'].isin(active_ranks)
    return CardSelection(
        regions=source_regions,
        units=active_units,
        ranks=active_ranks,
        scoped=people.loc[mask].copy(),
    )