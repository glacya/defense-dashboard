# dashboard

장병 체력·부상 관리 Streamlit 대시보드입니다. 데이터는 PostgreSQL DB에서 읽고, 후속조치 기록은 같은 DB에 저장합니다.

## 실행

```powershell
python -m streamlit run dashboard/app.py
```

DB 접속 정보는 환경 변수 또는 `dashboard/.env`(형식은 `dashboard/.env.example`)에 둡니다. 둘 다 있으면 환경 변수가 우선합니다. Streamlit Community Cloud에서는 Secrets에 같은 이름으로 넣습니다.

## 폴더와 파일

| 위치 | 역할 | 자세한 설명 |
|---|---|---|
| `app.py` | 앱의 시작점. 페이지 설정, CSS 주입, 사이드바 메뉴, 선택한 화면 실행 | [views/README.md](views/README.md) |
| `router.py` | 화면 등록(`st.Page`)과 URL 경로 | [views/README.md](views/README.md) |
| `db.py` | DB 접속, 조회(`run_query`, 결과 캐시), 쓰기 트랜잭션 | [py/README.md](py/README.md) |
| `style.css` | 전역 CSS | [common/README.md](common/README.md) |
| `views/` | 화면 파일(화면 하나에 `render()` 하나) | [views/README.md](views/README.md) |
| `py/` | 화면이 쓰는 데이터 조회(SQL)·가공·후속조치 기록 저장 | [py/README.md](py/README.md) |
| `common/` | 여러 화면이 함께 쓰는 CSS 주입, 색상·차트 스타일, 카드 필터, 상수, 위젯 | [common/README.md](common/README.md) |
| `static/` | 브라우저가 직접 받는 정적 파일(홈 지도의 시·도 경계 GeoJSON). `app/static/<파일명>`으로 제공됩니다(`.streamlit/config.toml`의 `enableStaticServing`). | - |
| `img/` | 아이콘 SVG와 그 base64 묶음(`base64.json`, `img2base64.py`로 생성) | - |

## 리팩터링 기준과 진행 기록

구조를 개선할 때도 화면 동작, 표시 컬럼명, 반환값, 캐시 동작은 변경하지 않습니다.

- `views/`는 필터·이벤트를 받고 화면을 그리는 역할만 담당합니다.
- SQL 조회, `groupby`·`merge` 집계, 체력 판정·등급 계산은 `py/`에 둡니다.
- 여러 화면에서 사용하는 UI·차트·색상은 `common/`으로 올립니다.
- `py/`의 집계 함수는 DB에 직접 연결하지 않고 DataFrame 또는 명시적 입력을 받아 테스트할 수 있게 합니다.
- 데이터베이스 접속 정보와 `.env`는 리팩터링 대상에 포함하지 않습니다.

### 기준선

2026-11-02 기준 전체 테스트는 `194 passed`입니다. CSV/DB 비교 도구는 일부 `SEVERITY`·`TYPE_NAME` 값 불일치와 `data/processed/RECOMMENDED_EXERCISE.csv` 누락으로 완전 일치하지 않았습니다. 이 결과는 리팩터링 전 기준선으로 유지합니다.

### 1단계 조사 결과

현재 화면에서 업무 로직 후보를 다음 위치에서 확인했습니다. 실제 이동 전에는 각 함수의 반환값·캐시·화면 출력이 유지되는지 확인해야 합니다.

| 파일·위치 | 확인한 로직 | 이동 후보 |
|---|---|---|
| `views/mainpage.py`의 `_render_fitness_variance`, `_precompute_scope_summaries` | 지역·부대별 `groupby`와 요약 계산 | `py/mainpage_data.py`의 `summarize_home_units()` |
| `views/p01_fitness_overview.py`의 `_combine_rounds`, `_combine_events` | 회차·종목별 `groupby` 집계 | 기존 `py/fitness_overview_data.py`의 순수 집계 함수 |
| `views/p04_unit_status.py`의 `_load_population`, `summarize_groups` | BMI 분류와 조직별 `groupby` 요약 | `py/unit_status_data.py`의 `prepare_population()`, `summarize_groups()` |
| `views/p03_personal_detail.py`의 `render()` 내부 | 계급별 `groupby`, 등급 기준 표시 계산 | `py/personal_detail_data.py`의 표시용 보조 함수 |
| `views/p07_guidance_followup.py`의 `render()` 내부 | 체력유형별 `groupby` 집계 | `py/followup_probability.py` 또는 별도 `py/guidance_data.py` |
| `views/p08_injury_followup.py`의 `render()` 내부 | 후속조치 기록과 부상 데이터 `merge` | `py/management_store.py` 또는 `py/injury_followup_data.py` |
| `views/p02_management_targets.py`, `p03_personal_detail.py`, `p07_guidance_followup.py` | `grade_cut()` 직접 호출 | `py/fitness_judgment.py`의 화면용 기준 함수 |

`views/`에서 직접 `run_query`를 호출하거나 SQL `SELECT`를 작성한 위치는 현재 없습니다.
