# dashboard/common: 화면 공용 모듈

여러 화면이 함께 쓰는 스타일·필터·상수·위젯입니다. 데이터를 DB에서 읽지 않습니다.

| 파일 | 주요 내용 |
|---|---|
| `assets.py` | `inject_assets()`: `config.CSS_PATH`(`dashboard/style.css`)를 `<style>`로 페이지에 넣습니다. `st.markdown`은 빈 줄에서 HTML 블록을 끊으므로 빈 줄을 지우고 넣습니다. `load_text(path)`는 파일을 캐시해 읽으며, `LIVE_RELOAD`가 켜져 있으면 파일 수정 시각을 캐시 키로 써서 저장 즉시 반영합니다. `app.py`에서만 호출합니다. |
| `brand.py` | 사이드바 로고·제목(`brand_html()`) |
| `charts.py` | 색상 상수(`CHART_PALETTE`, `CHART_CONTINUOUS_SCALE`, `BMI_COLORS`, `GRADE_COLORS` 등)의 원본. `apply_chart_layout(figure, height, **layout)`는 Plotly 차트에 공통 밝은 테마를, `style_altair(chart, height)`는 Altair 차트에 배경·축 색을 적용합니다. `show_plotly(figure)`는 너비 자동·모드바 숨김으로 그립니다. |
| `filters.py` | `render_personnel_cards(people, prefix, show_ranks=True)`: 지역(도 단위로 묶음)·부대·계급 카드를 그리고 `CardSelection`(선택 범위의 지역·부대·계급과 조건에 맞는 행)을 돌려줍니다. 아무것도 고르지 않으면 전체입니다. `prefix`가 같은 화면끼리는 선택이 공유됩니다. |
| `formatting.py` | 화면 공용 상수(`NAV_STATE_KEY`, `BMI_CATEGORY_ORDER`, `RANK_ORDER`, `FITNESS_ITEM_LABELS`, `GRADE_LABELS`), `classify_bmi()`(저체중 <18.5, 정상 <25, 과체중 <30, 비만 ≥30), `add_deficiency_flags()`(종목별 미달·등급 표시), `filter_signature(*values)`(조건 조합을 짧은 해시로 바꿔 위젯 `key`에 씀) |
| `widgets.py` | `render_soldier_details(soldier, history, injuries)`: 장병 기본 정보·회차별 변화·부상 이력 패널. `PieChartWidget`·`RadarChartWidget`: 파이·레이더 차트의 기본 정의(홈 화면이 상속해 씀) |

## style.css

`dashboard/style.css`는 앱 전체에 적용되는 CSS입니다. 위젯은 `key`가 정해져 있으면 `st-key-<key>` 클래스로 잡을 수 있어, 화면 코드는 `key`만 붙이고 모양은 CSS에서 정합니다(예: 카드 필터는 `cardfilter-{prefix}-...`). `:root`의 색상 변수는 `py/color_picker.py`로 고를 수 있습니다.
