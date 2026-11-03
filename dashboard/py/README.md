# dashboard/py: 데이터 조회·가공

화면(`views/`)이 쓰는 데이터를 DB에서 읽고 화면 표 모양으로 가공하는 모듈입니다. 대시보드는 DB(PostgreSQL)를 읽습니다.

## 원칙

- **화면 조회 SQL은 `queries.py`에 모읍니다.** 다른 모듈은 `queries.load_*()`를 불러 결과를 가공만 합니다.
  - 예외 두 가지: 후속조치 기록 읽기·쓰기(`management_store.py`)와 추천 운동 JOIN(`personal_exercise_recommendations.py`)은 그 기능에만 쓰는 SQL이라 각 모듈에 둡니다.
- **필요한 결과만 받습니다.** 집계(GROUP BY), 필터(WHERE), 한 장병·한 부대 조회는 SQL에서 끝냅니다. 테이블 전체를 받아 pandas로 줄이지 않습니다. pandas는 이름 붙이기·비율 계산 같은 화면 표 가공에만 씁니다.
- **화면 입력값은 `:이름` params로 넘깁니다.** SQL에 f-string으로 값을 넣지 않습니다. 컬럼 이름처럼 SQL 구조에 들어가는 값은 허용 목록에서만 고릅니다(예: `OVERVIEW_GROUPS`).
- **캐시**: `dashboard.db.run_query`가 결과를 `st.cache_data`로 캐시합니다. 읽기 전용이라 만료가 없으므로, 데이터를 다시 올리면 앱을 재시작하거나 Clear cache를 누릅니다. 후속조치 기록은 저장할 때마다 캐시를 비웁니다.
- **빈 값·나이 범위·판정 불가는 처리하지 않습니다.** DB의 NOT NULL 제약과 전처리(19~24세)가 보장합니다.
- 결과 컬럼은 대문자, NUMERIC은 float, `*_ID`는 문자열로 옵니다(`db.tidy()`).

## 모듈

| 파일 | 주요 함수 | 내용 |
|---|---|---|
| `queries.py` | `load_*()`, `judged_cte()`, `distribution_counts()` | 화면별 SQL. 아래 "queries.py 구성" 참고 |
| `fitness_judgment.py` | `EVENTS`, `REASONS`, `GRADE_LABELS`, `join_labels()`, `event_labels()`, `grade_standards()` | 판정 화면들이 함께 쓰는 종목·집중관리 사유·등급 이름과 표시 도우미. 등급 하한은 루트 `fitness_standards.py`에서 가져옵니다. |
| `fitness_overview_data.py` | `load_overview()`, `load_group_summary(group_column)`, `summary_tables()` | p01. 회차·종목(·지역·부대)별 SQL 집계를 한글 컬럼과 미달률이 붙은 화면 표로 바꿉니다. |
| `management_targets_data.py` | `load_round_targets(n)`, `build_targets()`, `prepare_judgments()`, `targets_metadata()` | p02. 선택 회차의 집중관리 대상자에 BMI 구간, 미달·신규 미달·지속 미달 종목 이름, 선정 사유를 붙입니다. |
| `personal_detail_data.py` | `load_soldier_history(soldier_id)`, `build_changes()`, `personal_metadata()` | p02·p03. 한 장병의 회차별 판정에 1차 대비 측정값·등급 변화를 붙입니다. |
| `injury_overview_data.py` | `injury_grade_table()`, `injury_people()`, `injury_metadata()` | p06. 종목×등급 부상 집계(빈 조합은 0명으로 채움), 명단 + 장병별 부상 건수. |
| `followup_probability.py` | `load_followup_population()`, `classify_probabilities()`, `RISK_LEVELS`, `FOLLOWUP_THRESHOLD` | p07·메인. 장병별 다음 회차 미달 확률을 안전·경계1~3등급으로 나눕니다(30·50·70%). |
| `personal_exercise_recommendations.py` | `load_recommendation(grade, cluster)`, `training_guidance()`, `split_by_injuries()`, `render_recommendation()` | 메인·p03. 체력유형(등급·군집)의 추천 운동. 부상 부위와 사용 부위가 겹치는 운동은 따로 분리합니다. 지침 문장은 루트 `fitness_standards.TARGET_DIFFICULTY`(등급별 목표 난이도)로, 근거 문장은 읽은 상대 편차와 유형의 체력 요소별 추천 운동 수로 만듭니다. |
| `management_store.py` | `load_records(kind)`, `save_record()`, `save_followups_batch()`, `validate()`, `load_completion_counts()` | p07·p08·메인. 후속조치 기록(아래 "후속조치 기록") |
| `management_forms.py` | `editor(kind, soldier, all_records, injuries)`, `LABELS` | p07·p08의 기록 입력·수정 폼 |
| `group_followup.py` | `render_group_followup(people)` | p07. 선택한 등급·유형 그룹 전체에 같은 후속조치를 한 번에 등록 |
| `color_picker.py` | (단독 실행) | `style.css`의 `:root` 색상 변수를 고르는 도구. 화면에서는 쓰지 않습니다. |

## queries.py 구성

| 절 | 주요 조회 | 쓰는 화면 |
|---|---|---|
| 공통 | `LATEST_CTE`(장병별 최신 측정 1건과 저장된 등급·백분위·유형), `judged_cte(one_soldier, one_unit)`(측정별 회차·미달 수·1차 값·최근 3회 지속 미달·집중관리 사유) | 여러 화면 |
| 메인 | `load_home_units`(지역·부대별 인원·미달·체력 수준), `load_home_injuries`(GROUPING SETS), `load_non_safe_count`, `load_fitness_types`, `load_home_type_profile` | mainpage |
| p01 | `load_overview_rounds/events(group_column)`, `load_measure_period`, `load_unit_judgments(unit)`(부대 카드 명단) | p01 |
| 장병 명단 | `load_roster`(3,582명, 신상만) | p03·p06·p08 등 |
| p02·p03 | `load_round_numbers`, `load_round_summary`, `load_round_targets`, `load_soldier_judgments`, `load_round_means`, `load_soldier_injuries`, `load_soldier_probability`, `load_measurement_profile` | p02·p03·p04 |
| p06 | `load_injury_summary`, `load_injury_distribution`·`load_injury_records`(지역·부대·계급 필터), `distribution_counts`, `load_injury_by_grade`, `load_soldier_injury_counts` | p06 |
| p07 | `load_followup_population`(장병별 신상·확률·최신 측정·유형) | p07 |
| p04 | `load_unit_latest`(장병별 최신 측정 + 신상 + 유형) | p04 |
| p08 | `load_injuries`(부상 기록 전체) | p08 |

판정 CTE는 장병 단위 창 함수만 쓰므로, `one_soldier`·`one_unit`으로 미리 걸러도 전체를 계산한 결과와 같습니다.

## 후속조치 기록 (`management_store.py`)

- 종류(`kind`)와 테이블: `followup_records` → `fitness_followups`, `injury_followup` → `injury_followups`. 테이블은 `data/scripts/setup_database.py`가 만듭니다(`CREATE TABLE IF NOT EXISTS`, 지우지 않음).
- 화면에는 모든 값을 문자열로 돌려줍니다(빈 값 `''`, 날짜 `YYYY-MM-DD`, 시각 KST ISO).
- 부상 후속조치에는 군번 컬럼이 없습니다. 읽을 때 `injuries`와 JOIN해 군번을 붙이고, 저장 전에 고른 부상이 그 장병의 것인지 확인합니다.
- 수정은 `UPDATED_AT`이 화면을 열 때 값과 같을 때만 합니다(다른 곳에서 먼저 고쳤으면 오류로 알림).
- 저장하면 기록 목록과 메인 화면 완료율 캐시를 비웁니다.

## 테스트

`tests/dashboard/`에 있으며 실제 DB에 접속하지 않습니다(`run_query`·`transaction`을 가짜로 바꿈).
- `test_queries.py`: SQL 조립(params, 허용 목록)과 결과 가공
- `test_management_store_db.py`: INSERT/UPDATE, 입력 검사, 캐시
- `test_fitness_overview_data.py`, `test_followup_probability.py`, `test_personal_exercise_recommendations.py`, `test_mainpage_followup_rate.py`, `test_db.py`
