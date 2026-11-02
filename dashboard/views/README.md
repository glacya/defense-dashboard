# dashboard/views: 화면

각 파일이 화면 하나이며 `render()` 함수 하나를 공개합니다. `dashboard/router.py`의 `NAV_ITEMS`에는 화면 모듈 경로를 등록하고, 실제 모듈 import는 해당 화면이 선택될 때 수행합니다.

## 화면이 그려지는 순서

```text
브라우저 → Streamlit 서버 (조작할 때마다 다시 실행)
  1. dashboard/app.py
     - st.set_page_config (이 파일에서만 호출)
     - inject_assets()          → style.css 주입
     - build_pages()            → 사이드바에 로고와 메뉴(st.page_link) 그리기
     - build_navigation(pages).run()
  2. dashboard/router.py
     - NAV_ITEMS의 (표시 이름, 아이콘, 화면 모듈, URL 경로)로 지연 로딩 st.Page를 만들고, 메뉴 목록을 세션(NAV_STATE_KEY)에 저장
     - st.navigation(position="hidden")으로 라우팅만 수행(메뉴는 app.py가 그림)
  3. 선택된 화면의 render()
     - 데이터 조회(py/) → 필터 → 차트·표 출력
```

대시보드 홈은 독립적인 장병·부상·체력 유형·위험 인원·후속조치 조회를 최대 5개 작업 스레드에서 병렬 실행합니다. 필수 조회 실패는 홈 화면 오류로 알리고, KPI 보조 조회 실패는 해당 KPI에 경고를 표시합니다.

## 원칙

- **화면 파일에는 SQL을 두지 않습니다.** 데이터는 `dashboard/py/`(주로 `queries.py`)에서 받습니다.
- 조회 실패는 `SQLAlchemyError`(그리고 `ValueError` 등)를 잡아 `st.error`/`st.info`로 알리고, 필요하면 `st.stop()`으로 멈춥니다.
- 위젯 `key`는 조건 조합을 `common.formatting.filter_signature()`로 해시해 만들어, 조건이 바뀌면 새 위젯이 되게 합니다.
- 지역·부대·계급 선택은 `common.filters.render_personnel_cards(people, prefix)`를 씁니다. `prefix`가 같으면 화면 사이에서 선택이 공유됩니다.
- 색상과 차트 스타일은 `common/charts.py`, CSS는 `dashboard/style.css`에 둡니다.

## 화면 목록 (메뉴 순서)

| 메뉴 | 파일 | URL | 내용 | 주요 데이터 |
|---|---|---|---|---|
| 대시보드 홈 | `mainpage.py` | `home` | 지역·부대별 체력 충족률 지도(시·도 GeoJSON), 전체 장병 KPI(미달·경계 등급·후속조치 완료율), 부상 현황, 운동유형 16개와 선택 유형의 평균 백분위·추천 운동 | `queries.load_home_*`, `load_non_safe_count`, `load_fitness_types`, `management_store.load_completion_counts`, `load_recommendation` |
| 부대 현황 | `p04_unit_status.py` | `units` | 지역·부대별 인원 요약, BMI 구간별 요약과 해당 장병 목록, 선택 장병의 체력유형 | `queries.load_unit_latest`, `load_measurement_profile` |
| 전체 체력 현황 | `p01_fitness_overview.py` | `fitness-overview` | 공용 지역·부대·계급 카드 필터 기준 회차 요약, 종목별 미달률·등급 분포·측정 수준, 회차별 변화와 조회 범위 내 부대 비교. 측정 회차는 가로 선택으로 표시하고, 단일 부대를 선택하면 요약 카드를 눌러 장병 명단(모달)을 봅니다. | `fitness_overview_data.load_overview`, `load_group_summary`, `queries.load_unit_judgments` |
| 미달·악화 대상자 | `p02_management_targets.py` | `management-targets` | 회차별 집중관리 대상자(BMI≥25·근력 또는 심폐 미달, 2종목 이상 미달, 1차 대비 악화, 최근 3회 지속 미달) 명단과 개인별 선정 근거 | `queries.load_round_summary`, `management_targets_data.load_round_targets`, `personal_detail_data.load_soldier_history` |
| 개인 장병 상세 | `p03_personal_detail.py` | `personal-detail` | 장병 찾기 → 신체 정보, 체력유형, 종목별 기준 비교, 1차 대비 변화, 전체 평균과 비교, 부상 이력, 추천 운동 | `queries.load_roster`, `load_soldier_history`, `load_measurement_profile`, `load_round_means`, `load_soldier_injuries`, `render_recommendation` |
| 부상 현황 | `p06_injury_overview.py` | `injury-overview` | 전체 부상 분포(부위·심각도·지역·부대·계급, 필터와 클릭 조회), 체력 등급별 부상 비교, 개인별 부상 이력 | `queries.load_injury_*`, `injury_overview_data.injury_grade_table`, `injury_people` |
| 체력 지도·후속조치 | `p07_guidance_followup.py` | `guidance-followup` | 미달 확률 등급(안전·경계1~3)과 운동유형으로 장병을 고르고, 상담·후속조치를 개인별 또는 그룹으로 기록 | `followup_probability.load_followup_population`, `management_store.load_records`, `management_forms.editor`, `group_followup.render_group_followup` |
| 부상 후속조치 | `p08_injury_followup.py` | `injury-followup` | 부상 이력이 있는 장병을 골라 부상별 회복 상태·운동 제한을 기록 | `queries.load_roster`, `queries.load_injuries`, `management_store.load_records`, `management_forms.editor` |

p05 화면 파일은 없습니다.

### 화면별 참고

- **전체 체력 현황(p01)**: 공용 지역·부대·계급 카드 필터가 요약과 추이에 적용됩니다. 측정 회차는 `p02`와 같은 가로 라디오로 선택하며, 둘 이상의 부대가 범위에 포함되면 부대별 미달률을 비교합니다.
- **개인 장병 상세(p03)**: 장병 찾기에서 부대 선택, 계급 카드, 이름·장병번호 검색으로 목록을 좁힌 뒤 장병을 고릅니다. 모두 비우면(`전체 조회`) 전체 장병입니다.

## 새 화면을 추가할 때

1. `views/pNN_이름.py`에 `render()`를 만듭니다.
2. 필요한 SQL은 `py/queries.py`에 `load_*()` 함수로 추가하고, 표 가공이 길면 `py/`에 모듈을 따로 둡니다.
3. `router.py`의 `NAV_ITEMS`에 `(표시 이름, 아이콘, "dashboard.views.모듈명", URL 경로)`를 추가합니다.
4. `streamlit.testing.v1.AppTest`로 화면이 예외 없이 그려지는지 확인합니다(실제 DB 접속이 필요하므로 CI에서는 돌리지 않습니다).
