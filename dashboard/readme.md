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

### 4.3 로더 (`dashboard/py/`)

| 파일 | 함수 | 읽는 원본 | 캐시 키 |
|---|---|---|---|
| `main_data.py` | `load_main_data()` | `SOLDIER_PERSONNEL.csv`, `KS_NFA_PROCESSED.csv`, `SOLDIER_INJURY.csv` | 파일의 수정 시각과 크기 |
| `fitness_overview_data.py` | `load_overview()` | 전체 현황 분석 결과 | 파일 수정 시각 |
| `management_targets_data.py` | `load_targets()` | 집중관리 분석 결과 | 파일 수정 시각 |
| `personal_detail_data.py` | `load_personal()` | 개인 상세 분석 결과 | 파일 수정 시각 |
| `injury_overview_data.py` | `load_injury_overview()` | 부상 현황 분석 결과 | 파일 수정 시각 |
| `management_store.py` | `load_records(kind)` | `MANAGEMENT_DIR/*.csv` | 캐시하지 않음 (입력 기록은 즉시 반영) |
| `management_forms.py` | `editor(...)`, `LABELS` | 관리 기록 | - |

개인 장병 상세 화면의 `장병 찾기`에서는 지역을 먼저 선택한 뒤 해당 지역의 부대를 선택해 장병 목록을 좁힐 수 있습니다. 두 필터를 비워 두면 전체를 조회합니다.
