import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# 저장소 루트를 import 경로에 추가 (config.py가 루트에 있으므로)
try:
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import config  # noqa: E402
    DATA_DIR = config.CSV_FINAL_DIR
except:
    # config 파일이 없을 경우를 대비한 임시 경로
    DATA_DIR = Path("data/csv_file/csv_final")

st.set_page_config(page_title="장병 체력요소 진단 대시보드", page_icon="🪖", layout="wide")

PRIMARY, GOOD, WARN, RISK, ACCENT, SOFT = "#2c3e4c", "#4f6d45", "#e5a73b", "#d9534f", "#7a8f66", "#8f8a73"
NORMAL_COLOR = "#e9ecef" # 정상군 (회색)

_missing_files: list[str] = []

def _load_csv(filename: str, columns: list[str], sample: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    path = DATA_DIR / filename
    if not path.exists():
        _missing_files.append(f"{filename}  (필요 컬럼: {', '.join(columns)})")
        return sample, False
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        missing_cols = [c for c in columns if c not in df.columns]
        if missing_cols:
            _missing_files.append(f"{filename}  (누락된 컬럼: {', '.join(missing_cols)})")
            return sample, False
        return df, True
    except Exception as e:
        _missing_files.append(f"{filename}  (읽기 오류: {e})")
        return sample, False

# ----------------------------------------------------------------------------
# 1. 데이터 로딩 (샘플 데이터 포함)
# ----------------------------------------------------------------------------

def get_kpi_data() -> dict:
    sample = pd.DataFrame([
        {"key": "diagnosis_time", "label": "취약 체력요소 진단 소요시간", "value": 1.2, "unit": "분/인", "weight": 30, "delta": "▼ 기존 대비 -46분"},
        {"key": "risk_identification", "label": "불합격 위험 인원 식별률", "value": 100, "unit": "%", "weight": 40, "delta": "종목별 기준 미달량 기반"},
        {"key": "matching_rate", "label": "부족 유형별 맞춤 운동처방", "value": 100, "unit": "%", "weight": 30, "delta": "전 유형 프로그램 연결 완료"},
    ])
    df, _ = _load_csv("kpi_data.csv", ["key", "label", "value", "unit", "weight", "delta"], sample)
    return {row["key"]: row.to_dict() for _, row in df.iterrows()}

def get_risk_distribution() -> pd.DataFrame:
    """종목별 위험군 분포 데이터 (누적 막대그래프용)"""
    sample = pd.DataFrame({
        "event": ["종목 1: BMI", "종목 2: 심폐지구력", "종목 3: 근력", "종목 4: 근지구력", "종목 5: 유연성", "종목 6: 민첩성"],
        "high_risk": [18, 25, 10, 32, 5, 8],
        "mid_risk": [12, 15, 20, 18, 15, 10],
        "normal": [70, 60, 70, 50, 80, 82]
    })
    return sample

def get_high_risk_personnel() -> pd.DataFrame:
    """특정 종목 고위험군 인원 명단"""
    sample = pd.DataFrame([
        {"이름": "김민준", "계급": "하사", "소속": "본부소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"},
        {"이름": "박도윤", "계급": "상병", "소속": "1소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"},
        {"이름": "최시우", "계급": "이병", "소속": "본부소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"},
        {"이름": "홍유준", "계급": "이병", "소속": "3소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"}
    ])
    return sample

def get_persons() -> pd.DataFrame:
    sample = pd.DataFrame([{
        "id": "P001", "name": "김민준", "rank": "하사", "unit_detail": "본부소대", "age": 23,
        "bmi": 27.4, "prior_fitness": "중", "injury_history": "무릎(경)", "type": "심폐지구력 부족형",
    }])
    df, _ = _load_csv("persons.csv", ["id", "name", "rank", "unit_detail", "age", "bmi", "prior_fitness", "injury_history", "type"], sample)
    return df

def get_individual_scores(person_id: str) -> pd.DataFrame:
    """개인별 방사형 차트를 위한 데이터 (개인, 부대, 전체 평가)"""
    sample = pd.DataFrame({
        "event": ["BMI", "근지구력", "유연성", "근력", "심폐지구력"],
        "personal": [8.0, 7.5, 6.0, 7.0, 4.0],
        "unit_avg": [6.5, 6.0, 5.0, 5.5, 5.5],
        "total_avg": [7.0, 6.5, 5.5, 6.0, 6.0]
    })
    return sample

# ----------------------------------------------------------------------------
# 2. 화면 구성
# ----------------------------------------------------------------------------
st.title("체력검정 기록 기반 개인별 취약 체력요소 진단")
st.caption(f"데이터 폴더: `{DATA_DIR}`")

tab_unit, tab_person = st.tabs(["부대 현황판", "개인별 진단"])

# ==========================================
# 탭 1: 부대 현황판
# ==========================================
with tab_unit:
    st.subheader("01. 부대 관리를 위한 핵심 지표 (KPI)")
    kpi = get_kpi_data()
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
        fig_risk.add_trace(go.Bar(name='고위험군', x=df_risk['event'], y=df_risk['high_risk'], marker_color=RISK, text=df_risk['high_risk'].astype(str)+'%', textposition='inside'))
        fig_risk.add_trace(go.Bar(name='중위험군', x=df_risk['event'], y=df_risk['mid_risk'], marker_color=WARN, text=df_risk['mid_risk'].astype(str)+'%', textposition='inside'))
        fig_risk.add_trace(go.Bar(name='정상군', x=df_risk['event'], y=df_risk['normal'], marker_color=NORMAL_COLOR))
        
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


# ==========================================
# 탭 2: 개인별 진단
# ==========================================
with tab_person:
    st.subheader("개인별 취약요소 및 상태 진단")
    df_persons = get_persons()
    labels = df_persons["rank"] + " " + df_persons["name"] + " · " + df_persons["unit_detail"]
    idx = st.selectbox("장병 선택", options=df_persons.index, format_func=lambda i: labels[i])
    person = df_persons.loc[idx]

    # --- 이미지 형태의 5개 상태 카드 구현 ---
    st.markdown("<br>", unsafe_allow_html=True)
    card_cols = st.columns(5)
    
    cards_data = [
        {"title": "근지구력", "status": "보완 (P1)", "color": RISK},
        {"title": "심폐지구력", "status": "유지/보완 (P2)", "color": WARN},
        {"title": "근력", "status": "유지 (P3)", "color": GOOD},
        {"title": "유연성", "status": "유지 (P3)", "color": GOOD},
        {"title": "BMI", "status": "유지 (P3)", "color": GOOD}
    ]
    
    for i, c in enumerate(card_cols):
        data = cards_data[i]
        c.markdown(f"""
        <div style="border-radius:10px; overflow:hidden; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); text-align:center; background-color:white;">
            <div style="background-color:{data['color']}; color:white; padding:10px; font-weight:bold; font-size:16px;">
                {data['title']}
            </div>
            <div style="padding:20px; font-weight:bold; font-size:18px; color:#333;">
                {data['status']}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # --- 장병 정보 및 스파이더 차트 ---
    c1, c2 = st.columns([1, 1.5])
    with c1:
        st.markdown(f"### {person['name']} {person['rank']}")
        st.caption(f"{person['unit_detail']}")
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
            fill="toself", line=dict(color=RISK, width=2.5),
            fillcolor="rgba(217,83,79,0.3)", name="개인평가"
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

# ----------------------------------------------------------------------------# ----------------------------------------------------------------------------
# 3. 상태 안내
# ----------------------------------------------------------------------------
st.divider()
if _missing_files:
    with st.expander(f"⚠️ 실제 데이터 미연결 항목 {len(_missing_files)}건 (현재 예시 데이터로 표시 중)", expanded=False):
        st.write(f"CSV_FINAL_DIR 경로: `{DATA_DIR}`")
        for m in sorted(set(_missing_files)):
            st.markdown(f"- `{m}`")