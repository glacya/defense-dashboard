"""6번 화면: 전체 부상·종목별 등급 비교·개인 부상 이력입니다."""

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.py.injury_overview_data import filter_injuries_by_personnel, load_injury_overview
from dashboard.py.fitness_judgment import EVENTS, GRADE_LABELS
from dashboard.common.formatting import filter_signature

INJURY_LABELS={'INJURY_ID':'부상 식별자','SOLDIER_ID':'장병 식별자','INJURY_CATEGORY':'부상 대분류',
               'INJURY_LOCATION':'부상 부위','SEVERITY':'심각도','PREVENTABILITY':'예방 가능 여부'}

SEVERITY_COLORS = {'경증': '#0F766E', '중등증': '#0891B2', '중증': '#2563EB'}
GROUP_COLUMNS = {'지역별': 'REGION_NAME', '부대별': 'UNIT_NAME', '계급별': 'RANK_NAME'}
REGION_GROUP_ORDER = ['경기', '강원', '전라', '경상', '충청', '제주']


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


def _toggle_injury_region(region: str) -> None:
    selected = list(st.session_state.get('injury_filter_regions', []))
    if region in selected:
        selected.remove(region)
    else:
        selected.append(region)
    st.session_state['injury_filter_regions'] = [item for item in REGION_GROUP_ORDER if item in selected]
    st.session_state['injury_filter_units'] = []


def _toggle_injury_unit(unit: tuple[str, str]) -> None:
    selected = list(st.session_state.get('injury_filter_units', []))
    if unit in selected:
        selected.remove(unit)
    else:
        selected.append(unit)
    st.session_state['injury_filter_units'] = selected


def _toggle_injury_rank(rank: str) -> None:
    selected = list(st.session_state.get('injury_filter_ranks', []))
    if rank in selected:
        selected.remove(rank)
    else:
        selected.append(rank)
    st.session_state['injury_filter_ranks'] = selected


def _change_injury_region_page(page_key: str, offset: int, page_count: int) -> None:
    current = int(st.session_state.get(page_key, 0))
    st.session_state[page_key] = min(max(current + offset, 0), page_count - 1)


def _style_injury_chart(chart):
    chart.update_layout(
        template='plotly_white',
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        font=dict(color='#182B40'),
        legend=dict(font=dict(color='#182B40')),
        hoverlabel=dict(bgcolor='#FFFFFF', font=dict(color='#182B40')),
        margin=dict(l=12, r=20, t=24, b=12),
    )
    chart.update_traces(textfont_color='#182B40')
    chart.update_xaxes(
        tickfont_color='#182B40',
        title_font_color='#182B40',
        gridcolor='#E2E8F0',
        linecolor='#CBD5E1',
    )
    chart.update_yaxes(
        tickfont_color='#182B40',
        title_font_color='#182B40',
        gridcolor='#E2E8F0',
        linecolor='#CBD5E1',
    )
    return chart


def _render_injury_distributions(injuries: pd.DataFrame) -> None:
    """필터된 부상 기록으로 부위·심각도·조직별 그래프를 표시합니다."""
    left, right = st.columns(2)
    location_counts = (
        injuries.groupby('INJURY_LOCATION', dropna=False)
        .size()
        .rename('건수')
        .reset_index()
        .rename(columns={'INJURY_LOCATION': '부위'})
        .sort_values('건수', ascending=False)
    )
    with left, st.container(border=True):
        st.subheader('부위별 부상 건수')
        chart = px.bar(
            location_counts,
            x='부위',
            y='건수',
            text='건수',
            color_discrete_sequence=['#0F766E'],
        )
        st.plotly_chart(_style_injury_chart(chart), width='stretch', theme=None)

    severity_counts = (
        injuries.groupby('SEVERITY', dropna=False)
        .size()
        .rename('건수')
        .reset_index()
        .rename(columns={'SEVERITY': '심각도'})
    )
    severity_counts['비율'] = severity_counts['건수'] / severity_counts['건수'].sum() * 100
    with right, st.container(border=True):
        st.subheader('심각도별 부상 건수 비율')
        chart = px.pie(
            severity_counts,
            names='심각도',
            values='건수',
            color='심각도',
            color_discrete_map=SEVERITY_COLORS,
            hole=0.35,
        )
        chart.update_traces(
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>%{value:,}건 · %{percent:.1%}<extra></extra>',
        )
        chart.update_layout(showlegend=True, legend_title_text='심각도')
        st.plotly_chart(_style_injury_chart(chart), width='stretch', theme=None)

    group_label = st.selectbox('부상 건수 비교 기준', list(GROUP_COLUMNS), key='injury_group_by')
    group_column = GROUP_COLUMNS[group_label]
    group_label_name = group_label.removesuffix('별')
    grouped_counts = (
        injuries.groupby(group_column, dropna=False)
        .size()
        .rename('부상 건수')
        .reset_index()
        .rename(columns={group_column: group_label_name})
        .sort_values('부상 건수', ascending=True)
    )
    with st.container(border=True):
        st.subheader(f'{group_label} 부상 건수')
        chart = px.bar(
            grouped_counts,
            x='부상 건수',
            y=group_label_name,
            orientation='h',
            text='부상 건수',
            color_discrete_sequence=['#2563EB'],
        )
        st.plotly_chart(_style_injury_chart(chart), width='stretch', theme=None)
    st.caption('분포 그래프는 부상 건수 기준입니다. 같은 장병의 반복 부상도 각각 포함됩니다.')


def _render_personnel_filter_cards(people: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    """지역·부대·계급 카드를 표시하고 조건에 맞는 부상 기록을 반환합니다."""
    scoped = people.assign(_REGION_GROUP=people['REGION_NAME'].map(_region_group))
    available_regions = sorted(
        scoped['_REGION_GROUP'].dropna().unique().tolist(),
        key=lambda value: (REGION_GROUP_ORDER.index(value) if value in REGION_GROUP_ORDER else len(REGION_GROUP_ORDER), value),
    )
    selected_regions = [region for region in st.session_state.get('injury_filter_regions', []) if region in available_regions]
    st.session_state['injury_filter_regions'] = selected_regions
    active_regions = selected_regions or available_regions
    source_regions = scoped.loc[scoped['_REGION_GROUP'].isin(active_regions), 'REGION_NAME'].dropna().unique().tolist()
    unit_pairs = sorted(
        map(tuple, scoped.loc[scoped['REGION_NAME'].isin(source_regions), ['REGION_NAME', 'UNIT_NAME']]
             .dropna().drop_duplicates().to_numpy().tolist())
    )
    selected_units = [tuple(unit) for unit in st.session_state.get('injury_filter_units', []) if tuple(unit) in unit_pairs]
    st.session_state['injury_filter_units'] = selected_units
    active_units = selected_units or unit_pairs
    ranks = sorted(scoped['RANK_NAME'].dropna().unique().tolist())
    selected_ranks = [rank for rank in st.session_state.get('injury_filter_ranks', []) if rank in ranks]
    st.session_state['injury_filter_ranks'] = selected_ranks
    active_ranks = selected_ranks or ranks

    st.markdown('''<style>
        div[class*="st-key-injury-region-card"] button {
            min-height: 68px; border-radius: 10px; white-space: pre-line; padding: 4px 7px;
            border: 1px solid #7B9DB8 !important;
        }
        div[class*="st-key-injury-region-card"] button[kind="primary"] {
            border: 2px solid #93C5FD !important; background: #DBEAFE !important;
            color: #1E3A5F !important; box-shadow: 0 0 0 1px #EFF6FF;
        }
        div[class*="st-key-injury-region-card"] button[kind="primary"] * { color: #1E3A5F !important; }
        div[class*="st-key-injury-unit-card"] button,
        div[class*="st-key-injury-rank-card"] button {
            min-height: 30px; border-radius: 16px; white-space: normal; padding: 1px 6px;
            border: 1px solid #91A99A !important;
        }
        div[class*="st-key-injury-unit-card"] button[kind="primary"],
        div[class*="st-key-injury-rank-card"] button[kind="primary"] {
            border: 2px solid #86EFAC !important; background: #D1FAE5 !important;
            color: #14532D !important; box-shadow: 0 0 0 1px #ECFDF5;
        }
        div[class*="st-key-injury-unit-card"] button[kind="primary"] *,
        div[class*="st-key-injury-rank-card"] button[kind="primary"] * { color: #14532D !important; }
        div[class*="st-key-injury-unit-region"] {
            border-color: #A9BDAF !important; border-radius: 12px; padding: .15rem .3rem;
        }
    </style>''', unsafe_allow_html=True)

    st.markdown('**지역**')
    region_counts = scoped.groupby('_REGION_GROUP')['SOLDIER_ID'].nunique().to_dict()
    for start in range(0, len(available_regions), 4):
        for column, region in zip(st.columns(4, gap='small'), available_regions[start:start + 4]):
            selected = region in selected_regions
            column.button(
                f'{"✓ " if selected else ""}**{region}**  \n{int(region_counts.get(region, 0)):,}명',
                key=f'injury-region-card_{region}', type='primary' if selected else 'secondary',
                width='stretch', on_click=_toggle_injury_region, args=(region,),
            )

    if selected_regions:
        st.markdown('**부대**')
        page_count = len(selected_regions)
        page_key = f"injury_region_page_{filter_signature(tuple(selected_regions))}"
        page = min(max(int(st.session_state.get(page_key, 0)), 0), page_count - 1)
        previous, status, next_button = st.columns([1, 3, 1])
        previous.button('← 이전 지역', disabled=page == 0, key=f'{page_key}_previous',
                        on_click=_change_injury_region_page, args=(page_key, -1, page_count))
        status.markdown(f'<div style="text-align:center;padding:.45rem">{selected_regions[page]} · {page + 1} / {page_count}</div>', unsafe_allow_html=True)
        next_button.button('다음 지역 →', disabled=page >= page_count - 1, key=f'{page_key}_next',
                           on_click=_change_injury_region_page, args=(page_key, 1, page_count))
        province = selected_regions[page]
        page_regions = sorted(scoped.loc[scoped['_REGION_GROUP'].eq(province), 'REGION_NAME'].dropna().unique().tolist())
        region_columns = st.columns(4, gap='small')
        for index, region in enumerate(page_regions):
            units_in_region = sorted(scoped.loc[scoped['REGION_NAME'].eq(region), 'UNIT_NAME'].dropna().unique().tolist())
            with region_columns[index % 4]:
                with st.container(border=True, key=f'injury-unit-region_{filter_signature(region)}'):
                    st.caption(region)
                    for unit in units_in_region:
                        unit_pair = (region, unit)
                        count = scoped.loc[
                            scoped['REGION_NAME'].eq(region) & scoped['UNIT_NAME'].eq(unit), 'SOLDIER_ID'
                        ].nunique()
                        selected = unit_pair in selected_units
                        st.button(
                            f'{"✓ " if selected else ""}{unit} · {count:,}명',
                            key=f'injury-unit-card_{filter_signature(region, unit)}', type='primary' if selected else 'secondary',
                            width='content', on_click=_toggle_injury_unit, args=(unit_pair,),
                        )

    rank_base = scoped.loc[
        scoped['_REGION_GROUP'].isin(active_regions)
        & pd.MultiIndex.from_frame(scoped[['REGION_NAME', 'UNIT_NAME']]).isin(active_units)
    ]
    rank_counts = rank_base.groupby('RANK_NAME')['SOLDIER_ID'].nunique().to_dict()
    st.markdown('**계급**')
    for start in range(0, len(ranks), 4):
        for column, rank in zip(st.columns(4, gap='small'), ranks[start:start + 4]):
            selected = rank in selected_ranks
            column.button(
                f'{"✓ " if selected else ""}{rank} · {int(rank_counts.get(rank, 0)):,}명',
                key=f'injury-rank-card_{rank}', type='primary' if selected else 'secondary',
                width='stretch', on_click=_toggle_injury_rank, args=(rank,),
            )

    filtered_injuries = filter_injuries_by_personnel(
        injuries,
        people,
        regions=source_regions,
        ranks=active_ranks,
    )
    selected_unit_mask = pd.MultiIndex.from_frame(
        filtered_injuries[['REGION_NAME', 'UNIT_NAME']]
    ).isin(active_units)
    return filtered_injuries.loc[selected_unit_mask]


def render() -> None:
    """부상 기록 전체를 기준으로 현황과 개인 기록을 표시합니다."""
    st.caption('장병 체력관리 / 06')
    st.title('부상 현황')
    st.write('부상 인원과 건수를 구분하고, 체력등급에 따른 분포와 개인별 기록을 확인합니다.')
    try:
        people,grades,summary,metadata,injuries=load_injury_overview()
    except FileNotFoundError:
        st.warning('분석 결과 또는 원본 파일이 없습니다. 아래 명령으로 생성하세요.')
        st.code('python -m data.scripts.analysis.analysis2.injury_overview',language='powershell');st.stop()
    except (ValueError,KeyError,pd.errors.EmptyDataError) as error:
        st.error(f'자료를 확인해 주세요: {error}');st.stop()
    if summary.empty:
        st.info('표시할 집계 자료가 없습니다.');st.stop()
    st.info('합성 부상 자료 · 발생일이 없어 전체 보유 기록을 집계합니다. 최신 체력등급과의 비교이며 실제 부상 위험을 입증하는 결과가 아닙니다.')
    row=summary.iloc[0]
    values=[f'{int(row["전체장병수"]):,}명',f'{int(row["부상인원"]):,}명',f'{int(row["부상건수"]):,}건',
            f'{row["부상자비율"]:.1f}%' if pd.notna(row['부상자비율']) else '해당 없음',f'{int(row["반복부상인원"]):,}명']
    for col,label,value in zip(st.columns(5),['전체 장병 수','부상 기록 보유 인원','부상 건수','부상자 비율','2건 이상 부상 기록'],values):
        col.metric(label,value,border=True)
    st.caption('전체 장병 명단이 분모입니다. 한 장병에게 부상이 여러 건 있어도 부상 인원은 1명입니다.')
    overall,comparison,individual=st.tabs(['전체 부상 분포','체력등급별 비교','개인별 부상 이력'])
    with overall:
        if injuries.empty:
            st.info('부상 파일에 기록이 없습니다.')
        else:
            st.caption('지역·부대·계급 카드 선택은 아래 분포 그래프에 적용됩니다. 상단 요약 지표는 전체 자료 기준입니다.')
            filtered_injuries = _render_personnel_filter_cards(people, injuries)
            st.caption(f'선택 조건에 해당하는 부상 기록 {len(filtered_injuries):,}건')
            if filtered_injuries.empty:
                st.info('선택한 지역·부대·계급 조건에 해당하는 부상 기록이 없습니다.')
            else:
                _render_injury_distributions(filtered_injuries)
    with comparison:
        event=st.selectbox('비교할 체력 종목',list(EVENTS),format_func=lambda key:EVENTS[key][0])
        grade_table=grades.loc[grades['종목'].eq(EVENTS[event][0])]
        left,right=st.columns(2)
        with left:
            chart=px.bar(grade_table,x='등급',y='부상자비율',text='부상자비율',
                category_orders={'등급':list(GRADE_LABELS.values())},hover_data=['전체인원','부상인원','부상건수'],color_discrete_sequence=['#2563eb'])
            chart.update_traces(texttemplate='%{text:.1f}%')
            chart.update_layout(yaxis_range=[0,100],yaxis_title='부상자 비율 (%)',title='최신 종목 등급별 부상자 비율')
            st.plotly_chart(_style_injury_chart(chart),width='stretch',theme=None)
        with right:
            st.dataframe(grade_table.drop(columns='종목'),hide_index=True,width='stretch',
                column_config={'부상자비율':st.column_config.NumberColumn(format='%.1f%%')})
        st.caption('분모: 각 등급의 전체 장병 수. 0명인 등급의 비율은 계산하지 않습니다. 종합등급이 아닌 종목별 등급이며 판정 불가 집단도 별도 표시합니다.')
        st.download_button('등급별 부상 집계 CSV',grade_table.to_csv(index=False).encode('utf-8-sig'),'체력등급별_부상현황.csv','text/csv')
    with individual:
        left,right=st.columns(2)
        search=left.text_input('이름·장병번호 검색')
        condition=right.selectbox('부상 기록',['전체','기록 있음','2건 이상','기록 없음'])
        shown=people.copy()
        if search:
            shown=shown.loc[shown.SOLDIER_NAME.str.contains(search,regex=False)|shown.SOLDIER_ID.str.contains(search,regex=False)]
        if condition=='기록 있음':
            shown=shown.loc[shown.INJURY_COUNT.gt(0)]
        elif condition=='2건 이상':
            shown=shown.loc[shown.INJURY_COUNT.ge(2)]
        elif condition=='기록 없음':
            shown=shown.loc[shown.INJURY_COUNT.eq(0)]
        cols=['SOLDIER_ID','SOLDIER_NAME','RANK_NAME','UNIT_NAME','INJURY_COUNT']
        display=shown[cols].rename(columns={'SOLDIER_ID':'장병 식별자','SOLDIER_NAME':'이름','RANK_NAME':'계급','UNIT_NAME':'소속','INJURY_COUNT':'부상 건수'})
        st.caption(f'조회 결과 {len(shown):,}명 · 신상 정보는 합성 자료입니다.')
        st.dataframe(display,hide_index=True,width='stretch')
        if shown.empty:
            st.info('검색 조건에 해당하는 장병이 없습니다.')
        else:
            lookup=shown.set_index('SOLDIER_ID')
            soldier=st.selectbox('장병 선택',shown.SOLDIER_ID.tolist(),format_func=lambda sid:f'{lookup.loc[sid,"SOLDIER_NAME"]} · {sid}')
            person=lookup.loc[soldier]
            st.write(f'**{person.SOLDIER_NAME} · {person.RANK_NAME} · {person.UNIT_NAME}**')
            records=injuries.loc[injuries.SOLDIER_ID.eq(soldier)].rename(columns=INJURY_LABELS)
            if records.empty:
                st.info('보유 부상 자료에서 해당 장병의 기록이 없습니다. 현재 건강 상태나 회복 여부를 뜻하지 않습니다.')
            else:
                records['예방 가능 여부']=records['예방 가능 여부'].map({'Y':'가능','N':'불가능'}).fillna('정보 없음')
                st.dataframe(records,hide_index=True,width='stretch')
                st.download_button('개인 부상 기록 CSV',records.to_csv(index=False).encode('utf-8-sig'),f'{soldier}_부상이력.csv','text/csv')
        st.caption('발생일·회복 상태·운동 제한 항목은 원본에 없어 표시하지 않습니다.')
    with st.expander('집계 기준·자료 출처'):
        for key in ['집계범위','등급','기간','합성','중복']:
            st.write(metadata[key])
        st.caption('분석 생성일: '+metadata['생성일시'])
