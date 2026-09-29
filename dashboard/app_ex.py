import sys
from pathlib import Path
import json
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import os
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DIR_DICT
globals().update(DIR_DICT)
from dashboard.py.loader import  load_css, _load_csv,load_css_colors 
from dashboard.py.dataloader import get_kpi_data, get_risk_distribution, get_high_risk_personnel, get_individual_scores, get_persons

with open(BASE64_DIR, "r", encoding="utf-8") as f:
    bg_data = json.load(f)
    # 사용할 모든 이미지base64를 사욜할 수 있도록 불러옵니다.

# ============================================================================
# CSS 로드 함수
# ============================================================================

# ============================================================================
# Streamlit 페이지 설정 및 CSS 로드
# ============================================================================
st.set_page_config(page_title="장병 체력요소 진단 대시보드", page_icon="🪖", layout="wide")

# 색상을 즉시 변경하기 위한 frag입니다.
@st.fragment(run_every="1s")
def refresh_when_css_changes():
    try:
        css_mtime = Path(CSS_PATH).stat().st_mtime_ns
    except OSError:
        return

    previous_mtime = st.session_state.get("_css_mtime_ns")
    st.session_state["_css_mtime_ns"] = css_mtime
    if previous_mtime is not None and css_mtime != previous_mtime:
        st.rerun()


refresh_when_css_changes()
COLOR_DICT= load_css(CSS_PATH)

# 색상 정의 (파이썬 코드에서도 사용)
colors = SimpleNamespace(**load_css_colors(CSS_PATH))
_missing_files: list[str] = []


# ============================================================================
# 1. 데이터 로딩 (샘플 데이터 포함)
# ============================================================================


# ============================================================================
# 2. 화면 구성
# ============================================================================
st.title("체력검정 기록 기반 개인별 취약 체력요소 진단")

# 백그라운드 이미지 설정 (base64 이미지가 있을 경우)
base64_str = bg_data.get("bg_img", "")
if base64_str:
    bg_css = f"""
    <style>
    :root {{
        /* 배경이미지 적용하는 방식
        --bg-image: url("data:image/png;base64,{base64_str}");*/
        --background-color: #F0F0F0;
    }}
    </style>
    """
st.markdown(bg_css, unsafe_allow_html=True)
tab_unit, tab_person = st.tabs(["부대 현황판", "개인별 진단"])

# ============================================================================
# 탭 1: 부대 현황판
# ============================================================================
with tab_unit:
    st.subheader("01. 부대 관리를 위한 핵심 지표 (KPI)")
    kpi = get_kpi_data(DB_DIR)
    cols = st.columns(len(kpi))
    for col, (key, d) in zip(cols, kpi.items()):
        col.metric(f"{d['label']} (가중치 {d['weight']}%)", f"{d['value']}{d['unit']}", d["delta"])

    st.markdown("---")
    st.subheader("02. 불합격 위험 인원 식별 및 맞춤 처방")
    
    col_chart, col_table = st.columns([1.2, 1])
    
    with col_chart:
        st.markdown("**유형별 불합격 가능성이 높은 인원 비율**")
        df_risk = get_risk_distribution()
        
        # 누적 막대그래프 생성
        fig_risk = go.Figure()
        fig_risk.add_trace(go.Bar(name='고위험군', x=df_risk['event'], y=df_risk['high_risk'], marker_color=colors.risk, text=df_risk['high_risk'].astype(str)+'%', textposition='inside'))
        fig_risk.add_trace(go.Bar(name='중위험군', x=df_risk['event'], y=df_risk['mid_risk'], marker_color=colors.warn, text=df_risk['mid_risk'].astype(str)+'%', textposition='inside'))
        fig_risk.add_trace(go.Bar(name='정상군', x=df_risk['event'], y=df_risk['normal'], marker_color=colors.normal))
        
        fig_risk.update_layout(
            barmode='stack',
            height=400,
            margin=dict(l=0, r=0, t=30, b=0),
            yaxis=dict(range=[0, 100], ticksuffix="%"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_risk, use_container_width=True)

    with col_table:
        # 인터랙션을 흉내내기 위한 Selectbox (차트 클릭 대용)
        selected_event = st.selectbox("상세 정보를 확인할 종목(유형)을 선택하세요:", df_risk['event'].tolist(), index=1)
        
        st.markdown(f"**{selected_event} · 고위험군 명단 및 맞춤 운동처방**")
        # 실제 환경에서는 selected_event에 따라 데이터를 필터링합니다.
        df_personnel = get_high_risk_personnel()
        st.dataframe(df_personnel, hide_index=True, use_container_width=True)


# ============================================================================
# 탭 2: 개인별 진단
# ============================================================================
with tab_person:
    st.subheader("개인별 취약요소 및 상태 진단")
    df_persons = get_persons(DB_DIR)
    labels = df_persons["rank"] + " " + df_persons["name"] + " · " + df_persons["unit_detail"]
    idx = st.selectbox("장병 선택", options=df_persons.index, format_func=lambda i: labels[i])
    person = df_persons.loc[idx]

    # --- 이미지 형태의 5개 상태 카드 구현 (CSS 클래스 사용) ---
    st.markdown("<br>", unsafe_allow_html=True)
    card_cols = st.columns(5)
    
    cards_data = [
        {"title": "근지구력", "status": "보완 (P1)", "type": "risk"},
        {"title": "심폐지구력", "status": "유지/보완 (P2)", "type": "warn"},
        {"title": "근력", "status": "유지 (P3)", "type": "good"},
        {"title": "유연성", "status": "유지 (P3)", "type": "good"},
        {"title": "BMI", "status": "유지 (P3)", "type": "good"}
    ]
    
    for i, c in enumerate(card_cols):
        data = cards_data[i]
        header_class = f"status-card__header--{data['type']}"
        c.markdown(f"""
        <div class="status-card shadow-md">
            <div class="status-card__header {header_class}">
                {data['title']}
            </div>
            <div class="status-card__body">
                {data['status']}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # --- 장병 정보 및 스파이더 차트 ---
    c1, c2 = st.columns([1, 1.5])
    with c1:
        st.markdown(f"""
        <div class="person-info">
            <div class="person-info__title">{person['name']} {person['rank']}</div>
            <div class="person-info__subtitle">{person['unit_detail']}</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        | 항목 | 정보 |
        |---|---|
        | **연령** | {person['age']} |
        | **BMI** | {person['bmi']} |
        | **입대 전 체력** | {person['prior_fitness']} |
        | **부상 이력** | {person['injury_history']} |
        | **유형 분류** | **{person['type']}** |
        """)
        
    with c2:
        df_ind = get_individual_scores(person["id"])

        # 다각형을 닫기 위해 첫 행 추가
        df_closed = pd.concat([df_ind, df_ind.iloc[[0]]], ignore_index=True)
        risk_rgb = tuple(int(colors.risk.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        risk_fill = f"rgba({risk_rgb[0]}, {risk_rgb[1]}, {risk_rgb[2]}, 0.3)"

        fig_radar = go.Figure()
        
        # 1. 전체 평가 (점선)
        fig_radar.add_trace(go.Scatterpolar(
            r=df_closed["total_avg"], theta=df_closed["event"],
            line=dict(color="#b0b0b0", dash="dot", width=3), name="전체평가"
        ))
        # 2. 부대 평가 (검은 실선)
        fig_radar.add_trace(go.Scatterpolar(
            r=df_closed["unit_avg"], theta=df_closed["event"],
            line=dict(color="black", width=2), name="부대평가"
        ))
        # 3. 개인 평가 (빨간 면)
        fig_radar.add_trace(go.Scatterpolar(
            r=df_closed["personal"], theta=df_closed["event"],
            fill="toself", line=dict(color=colors.risk, width=2.5),
            fillcolor=risk_fill, name="개인평가"
        ))
        
        fig_radar.update_layout(
            height=450,
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 10]),
                angularaxis=dict(direction="clockwise")
            ),
            margin=dict(l=40, r=40, t=20, b=20),
            legend=dict(orientation="v", yanchor="top", y=1, xanchor="right", x=1.1)
        )
        st.plotly_chart(fig_radar, use_container_width=True)

# ============================================================================
# 3. 상태 안내
# ============================================================================
st.divider()
if _missing_files:
    with st.expander(f"⚠️ 실제 데이터 미연결 항목 {len(_missing_files)}건 (현재 예시 데이터로 표시 중)", expanded=False):
        st.write(f"CSV_FINAL_DIR 경로: `{CSV_FINAL_DIR}`")
        for m in sorted(set(_missing_files)):
            st.markdown(f"- `{m}`")