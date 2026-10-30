# dashboard 폴더 구조와 동작 방식

## 폴더 구조

```text
dashboard/
├─ app.py                     # 엔트리: 페이지 설정, CSS/JS 주입, 내비게이션 실행
├─ 중재자.py                   # 페이지 등록(st.Page)과 URL 경로 정의
├─ common/
│  ├─ assets.py               # CSS/JS 로딩
│  ├─ charts.py               # Plotly·Altair 색상과 공통 레이아웃
│  ├─ filters.py              # 측정 기간·지역·부대·계급·나이 조건 UI
│  ├─ formatting.py           # 상수, BMI 분류, 미달 플래그, 기간 마스크
│  └─ widgets.py              # 공통 장병 상세 패널·Plotly 차트 위젯
├─ dashboard/py/              # 데이터 로더 (파일 읽기·검증·캐시)
│  ├─ main_data.py
│  ├─ fitness_overview_data.py
│  ├─ management_targets_data.py
│  ├─ personal_detail_data.py
│  ├─ injury_overview_data.py
│  ├─ management_store.py     # 관리 기록 CSV 읽기·쓰기
│  └─ management_forms.py     # 관리 기록 입력 폼
├─ views/                     # 화면(페이지) 파일
│  ├─ mainpage.py             # 대시보드 홈
│  ├─ p01_fitness_overview.py
│  ├─ p02_management_targets.py
│  ├─ p03_personal_detail.py
│  ├─ p04_unit_status.py
│  ├─ p06_injury_overview.py
│  ├─ p07_guidance_followup.py
│  └─ p08_injury_followup.py
├─ styles/                    # CSS (style1.css 공통, 페이지 전용 파일 선택)
├─ scripts/                   # JS (선택)
└─ img/
   └─ personnel_health.svg    # 사이드바 로고
```

## 동작 흐름

```text
브라우저 → Streamlit 서버
  1. dashboard/app.py 실행 (매 rerun마다)
     - set_page_config
     - inject_assets()  → CSS/JS 주입
     - st.logo()
     - build_navigation().run()
  2. 중재자.py의 build_navigation()
     - st.Page(...)로 8개 화면 등록, 세션에 바로가기 목록 저장
  3. 선택된 페이지의 render() 실행
     - 로더 호출 → 필터 → 차트·표 출력
```

## 파일별 설명

### 4.1 엔트리와 라우팅

**`dashboard/app.py`**

- 앱의 시작점입니다. `st.set_page_config`는 이 파일에서만 호출합니다.
- `inject_assets()`로 공통 CSS/JS를 넣고, `st.logo()`로 로고를 표시합니다.
- 마지막 줄 `build_navigation().run()`이 선택된 페이지를 실행합니다.

**`dashboard/중재자.py`**

- `NAV_ITEMS` 튜플 목록에 메뉴를 정의합니다. 튜플 형식은 `(표시 이름, 아이콘, 페이지 함수, URL 경로)`입니다.
- `build_navigation()`은 `st.Page`를 만들고 `st.navigation`에 넘깁니다.
- 바로가기 링크를 위해 `NAV_STATE_KEY`(`"nav_links"`) 세션 키에 목록을 저장합니다.

### 4.2 공통 모듈 (`common/`)

**`assets.py`**

- `load_text(path)`: 파일을 읽고 `@st.cache_data`로 캐시합니다.
- `inject_assets()`: `config.CSS_PATH`의 CSS를 `<style>`로, `config.JS_PATH`의 JS를 숨김 iframe으로 주입합니다.
- CSS는 빈 줄을 제거해서 넣습니다. `st.markdown`은 빈 줄에서 HTML 블록을 끊기 때문입니다.

**`charts.py`**

- 색상 상수(`NAVY_BACKGROUND`, `BMI_COLORS`, `FITNESS_ITEM_COLORS`, `GRADE_COLORS` 등)의 원본입니다.
- `apply_dark_layout(figure, height, **layout)`: Plotly 차트에 다크 테마를 적용합니다. 개별 설정은 키워드로 덮어씁니다.
- `style_altair(chart, height)`: Altair 차트에 배경과 축 색을 적용합니다.
- `show_plotly(figure)`: `st.plotly_chart`를 너비 자동, 모드바 숨김으로 호출합니다.

**`filters.py`**

- `render_filters(measurements, prefix, show_bmi=False, show_date=True)`: 측정 기간(선택), 지역, 부대, 계급, 나이 조건을 그리고 `FilterResult`를 반환합니다. 홈 화면은 `show_date=False`로 전체 기간을 사용합니다.
- `prefix`가 세션 키의 접두어입니다. 같은 prefix를 쓰면 페이지 사이에서 조건이 공유되고, 다른 prefix를 쓰면 독립입니다.
  - 현재 구현: `mainpage`는 `"home"`, 부대 현황은 `"unit"`을 씁니다.
- 지역을 바꾸면 `_reset_units`가 부대 선택을 새 지역 범위로 다시 맞춥니다.
- 측정 기간에 시작일만 선택된 중간 상태에서는 시작일과 같은 날로 간주합니다.

**`formatting.py`**

- 화면 간에 공유하는 상수(`BMI_CATEGORY_ORDER`, `RANK_ORDER`, `FITNESS_ITEM_LABELS`, `GRADE_LABELS`)를 둡니다.
- `classify_bmi`: BMI를 저체중 `<18.5`, 정상 `<25`, 과체중 `<30`, 비만 `≥30`으로 나눕니다.
- `period_mask`: 시작일 00:00부터 종료일 23:59:59.999999999까지 포함하는 마스크입니다. 날짜 비교에서 같은 날짜 누락을 막기 위해 씁니다.
- `latest_measurements`: 기간 안에서 장병별 가장 최근 측정 한 건을 고릅니다.
- `add_deficiency_flags`: 종목별 미달·등급 컬럼과 `체력미달`, `관리대상` 플래그를 추가합니다.
- `add_measurement_rounds`: 장병별 측정 순서로 `측정회차`를 부여합니다.
- `filter_signature(*values)`: 조건 조합을 짧은 해시로 바꿔 위젯 `key`에 씁니다.

**`widgets.py`**

- `render_soldier_details(soldier, history, injuries)`: 장병 기본 정보, 회차별 변화, 부상 이력을 그립니다.
- `PieChartWidget`: 범주별 파이/도넛 차트의 기본 정의입니다.
- `RadarChartWidget`: 항목별 스파이더 차트의 기본 정의입니다.
- 메인 페이지는 `MainPieChart`, `MainRadarChart`로 위젯을 상속해 사용합니다.
- `show_soldier_detail_dialog(...)`: 위 내용을 `st.dialog` 모달로 엽니다.
- 모달을 닫은 뒤 같은 장병이 자동으로 다시 열리지 않도록 `soldier_detail_dismissed_id` 세션 값을 사용합니다.

### 전체 체력 현황

- 기본 전체 조회 외에 지역별·부대별 분석 기준을 선택할 수 있습니다.
- 조직 비교 화면은 회차별 전체 미달률과 종목별 미달률을 비교하고, 특정 지역·부대를 선택하면 해당 조직의 지표와 회차 추이를 확인할 수 있습니다.
- 조직별 결과는 장병의 현재 소속으로 묶으며, 판정·등급 기준은 전체 현황 분석과 동일하게 적용합니다.

### 4.3 로더 (`dashboard/py/`)

CSV → DB 전환 기간에는 로더마다 **CSV 모드/DB 모드**가 있습니다. 모든 로더가 `source` 인자(`"csv"`/`"db"`)를 받고, 비우면 환경 변수 `DASHBOARD_DATA_SOURCE` > `dashboard/.env` > 기본값 `db` 순서로 정합니다(`dashboard/data_source.py`). DB 모드는 `dashboard.db.run_query`(SQL)만 쓰고 결과를 10분(`DEFAULT_TTL`) 캐시합니다. 두 모드 결과가 같은지는 `python dashboard/compare_data_sources.py`로 확인합니다(실제 DB에 접속, CI에서는 실행하지 않음). 검증이 끝나면 CSV 모드·비교 스크립트·`data/scripts/analysis/analysis2/`를 지웁니다.

| 파일 | 함수 | CSV 모드 | DB 모드 |
|---|---|---|---|
| `main_data.py` | `load_main_data()` | `SOLDIER_PERSONNEL.csv`, `KS_NFA_PROCESSED.csv`, `SOLDIER_INJURY.csv` | `fitness_measurements` + `soldiers`, `injuries` |
| `py/followup_fitness_types.py` | `load_fitness_types()` | `MEASUREMENT_CLASSIFICATION.csv`, `FITNESS_TYPE.csv` | `measurement_classifications`, `fitness_types` |
| `py/followup_probability.py` | `load_probabilities()` | `SOLDIER_FAILURE_PROBABILITY.csv` | `soldier_failure_probabilities` |
| `py/personal_fitness_profile.py` | `load_profiles()` | `KS_NFA_PROCESSED.csv`로 백분위 계산 + 유형 | `measurement_classifications`의 저장된 백분위 + 유형 |
| `py/roster_data.py` | `load_personnel_text()` 등 | 명단·부상·측정 CSV | `soldiers`, `injuries`, `fitness_measurements` |
| `py/fitness_overview_data.py` | `load_overview()`, `load_group_summary()` | analysis2 전체 현황 결과 | 판정표를 pandas로 회차·종목(·조직)별 집계 |
| `py/management_targets_data.py` | `load_targets()` | analysis2 집중관리 결과 | 판정표 + BMI 구간·종목 이름·선정 사유 |
| `py/personal_detail_data.py` | `load_personal()` | analysis2 개인 상세 결과 | 판정표의 1차 값으로 변화 계산, `injuries` |
| `py/injury_overview_data.py` | `load_injury_overview()` | analysis2 부상 현황 결과 | 판정표 최신 회차 × `injuries` 집계 |

B 그룹(아래 네 로더)은 `py/fitness_judgment.py`의 판정표(`JUDGED_SQL` 한 번: 측정 + 명단 + 저장된 종목 등급, 창 함수로 회차·1차 값·최근 3회 지속 미달, 미달 수·집중관리 플래그)를 `st.cache_data`로 캐시해 함께 씁니다. 빈 값·나이 범위는 DB 제약(NOT NULL)과 전처리가 보장하므로 판정 불가 항목은 두지 않습니다.
| `py/personal_exercise_recommendations.py` | `load_recommendation(grade, cluster)` | 추천·유형·운동 분류·처방 상세 CSV를 pandas로 연결 | `recommended_exercises` JOIN `fitness_types`·`exercise_classifications`·`exercise_prescription_details`(params `:grade`, `:cluster`). 지침·근거 문장은 `build_exercise_recommendations.training_guidance()`·`recommendation_basis()` |
| `views/mainpage.py` | `_load_fitness_type_links()`, `_load_prescription_data()` | 유형·처방 CSV | `fitness_types` 등, `exercise_prescriptions`·`exercise_prescription_details` |
| `py/management_store.py` | `load_records(kind)`, `save_record()`, `save_followups_batch()` | `MANAGEMENT_DIR/*.csv` | 상담·후속조치 `fitness_followups`, 부상 후속조치 `injury_followups`(군번은 `injuries`와 JOIN)에 INSERT/UPDATE. 읽기는 `st.cache_data`로 캐시하고 저장할 때마다 비움. 수정은 `UPDATED_AT`이 화면을 열 때와 같을 때만. |
| `management_forms.py` | `editor(...)`, `LABELS` | 관리 기록 | - |

개인 장병 상세 화면의 `장병 찾기`에서는 지역을 먼저 선택한 뒤 해당 지역의 부대를 선택해 장병 목록을 좁힐 수 있습니다. 두 필터를 비워 두면 전체를 조회합니다.
