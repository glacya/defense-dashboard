import streamlit as st
import pandas as pd
from pathlib import Path
from pipeline import ColumnStandardizerPipeline
from data.csv_file.test_py_folder.config import DB_DIR, DB_DEFINE_DIR, COMPLETE_DIR, SPECS_JSON_PATH

# 페이지 설정
st.set_page_config(
    page_title="AI CSV 데이터 정제 대시보드",
    page_icon="📊",
    layout="wide"
)

st.title("📊 AI 기반 CSV 컬럼 규격화 및 파이프라인 대시보드")
st.markdown("---")

# 1. 사이드바: DB 선택 및 파일 확인
st.sidebar.header("📁 데이터 선택 및 설정")

# DB 폴더에서 사용 가능한 파일 목록 동적 탐색 (확장자 제거한 이름들)
if DB_DIR.exists():
    available_dbs = [f.stem for f in DB_DIR.glob("*.csv")]
else:
    available_dbs = []

if not available_dbs:
    st.sidebar.warning("DB 폴더에 CSV 파일이 없습니다. 파일을 추가해주세요.")
    db_name = st.sidebar.text_input("DB 이름 직접 입력 (예: A_B)", value="A_B")
else:
    db_name = st.sidebar.selectbox("대상 데이터셋 선택", available_dbs)

# 파이프라인 객체 생성
pipeline = ColumnStandardizerPipeline(db_name=db_name)

# 파일 유효성 검사 및 데이터 로드 버튼
if st.sidebar.button("파일 로드 및 검증"):
    success = pipeline.validate_and_load_files()
    if success:
        st.session_state['pipeline'] = pipeline
        st.session_state['loaded'] = True
        st.sidebar.success("파일 로드 성공!")
    else:
        st.session_state['loaded'] = False
        st.sidebar.error("파일을 찾지 못했습니다. 경로를 확인하세요.")

# 메인 화면 로직
if 'loaded' in st.session_state and st.session_state['loaded']:
    active_pipeline = st.session_state['pipeline']
    
    # 탭으로 화면 분리 (1. 데이터 미리보기, 2. 표준 규격 관리, 3. AI 정제 실행)
    tab1, tab2, tab3 = st.tabs(["📋 데이터 미리보기", "⚙️ 표준 규격(JSON) 관리", "🚀 AI 정제 및 병합 실행"])
    
    with tab1:
        st.subheader(f"[{db_name}] 원본 데이터 및 컬럼 정의서")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**[컬럼 정의서 (_define.csv)]**")
            st.dataframe(active_pipeline.df_define, use_container_width=True)
        with col2:
            st.markdown("**[원본 데이터셋 (.csv)]**")
            st.dataframe(active_pipeline.df_data, use_container_width=True)

    with tab2:
        st.subheader("⚙️ 표준 규격 리스트 관리 (standard_specs.json)")
        
        # 정의서에서 한글 속성명 목록 추출 시도
        try:
            active_pipeline.df_define.columns = active_pipeline.df_define.columns.str.strip()
            korean_cols = active_pipeline.df_define['컬럼한글명'].dropna().astype(str).tolist()
        except:
            korean_cols = ["지역", "나이", "성별"]
            
        selected_attr = st.selectbox("정의서 내 관리할 속성 선택 (한글명)", korean_cols)
        
        # 기존 저장된 규격 불러오기 시도
        existing_specs = active_pipeline.load_standard_specs(selected_attr)
        default_specs_str = ", ".join(existing_specs) if existing_specs else "충주시, 제천시, 보은군"
        
        st.info(f"현재 선택된 속성 **[{selected_attr}]**의 등록된 표준 규격입니다. 수정 후 저장할 수 있습니다.")
        
        specs_input = st.text_area(
            "표준 규격 리스트 (쉼표(,)로 구분하여 입력)", 
            value=default_specs_str,
            help="예: 경기도, 서울시, 충청도 또는 남, 여"
        )
        
        if st.button("표준 규격 저장 (JSON 업데이트)"):
            specs_list = [item.strip() for item in specs_input.split(",") if item.strip()]
            active_pipeline.save_spec_to_json(selected_attr, specs_list)
            st.success(f"[{selected_attr}] 표준 규격이 성공적으로 저장되었습니다!")

    with tab3:
        st.subheader("🚀 AI 자동 매핑 및 데이터 정제")
        
        try:
            korean_cols = active_pipeline.df_define['컬럼한글명'].dropna().astype(str).tolist()
        except:
            korean_cols = []
            
        target_attr = st.selectbox("정제할 대상 속성 선택", korean_cols, key="target_attr_run")
        
        # 저장된 JSON 규격 확인
        loaded_specs = active_pipeline.load_standard_specs(target_attr)
        
        if loaded_specs:
            st.write(f"📌 **적용될 표준 규격:** `{loaded_specs}`")
        else:
            st.warning(f"⚠️ [{target_attr}]에 대한 표준 규격이 JSON에 없습니다. 2번 탭에서 먼저 규격을 등록해주세요.")
            
        if st.button("정제 및 병합 실행 파이프라인 가동", type="primary"):
            if not loaded_specs:
                st.error("표준 규격 데이터가 없어 실행할 수 없습니다.")
            else:
                with st.spinner("AI가 비표준 데이터를 분석하고 데이터를 병합 중입니다... 잠시만 기다려주세요."):
                    result_df = active_pipeline.run_standardization_workflow(
                        target_korean_attr=target_attr, 
                        stand_data=loaded_specs
                    )
                    
                if result_df is not None:
                    st.success("데이터 정제 및 병합이 완료되었습니다!")
                    st.markdown("**[정제 및 집계된 최종 데이터]**")
                    st.dataframe(result_df, use_container_width=True)
                    
                    # 다운로드 버튼 제공
                    csv_data = result_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                    st.download_button(
                        label="📥 정제된 CSV 파일 다운로드",
                        data=csv_data,
                        file_name=f"{db_name}_completed.csv",
                        mime="text/csv"
                    )
                    st.info(f"📁 파일이 서버의 `{COMPLETE_DIR}` 경로에도 자동 저장되었습니다.")

else:
    st.info("👈 왼쪽 사이드바에서 데이터셋을 선택한 뒤 **[파일 로드 및 검증]** 버튼을 눌러주세요.")