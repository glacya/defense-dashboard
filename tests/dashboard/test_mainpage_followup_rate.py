"""메인 후속조치 완료율 카드를 검증합니다(완료 건수는 DB에서 세므로 가짜 값으로 대체)."""

from dashboard.py import management_store
from dashboard.views import mainpage


def test_completion_rates_use_non_safe_and_injury_denominators(monkeypatch):
    """체력 완료율은 경계1~3등급 인원, 부상 완료율은 부상 건수가 분모인지 확인합니다."""
    rendered = []
    monkeypatch.setattr(mainpage.st, 'markdown', lambda value, **kwargs: rendered.append(value))

    mainpage._render_kpis(
        3,
        4,
        2,
        {'fitness_records': 4, 'fitness_completed': 1, 'injury_records': 1, 'injury_completed': 1},
    )

    assert '50.0%' in rendered[0] and '25.0%' in rendered[0]
    assert '경계1~3등급 2명 기준 · 안전 제외' in rendered[0]


def test_home_queries_run_concurrently(monkeypatch):
    """홈 화면에 필요한 여섯 데이터 로더가 동시에 실행되는지 확인합니다."""
    from threading import Barrier, Lock, current_thread

    barrier = Barrier(6)
    thread_names = []
    lock = Lock()

    def loader(result):
        barrier.wait(timeout=3)
        with lock:
            thread_names.append(current_thread().name)
        return result

    units = mainpage.pd.DataFrame()
    injuries = {'injuries': 1}
    types = mainpage.pd.DataFrame()
    completion = {
        'fitness_records': 2,
        'fitness_completed': 1,
        'injury_records': 1,
        'injury_completed': 1,
    }
    monkeypatch.setattr(mainpage.queries, 'load_home_units', lambda: loader(units))
    monkeypatch.setattr(mainpage.queries, 'load_home_injuries', lambda: loader(injuries))
    monkeypatch.setattr(mainpage.queries, 'load_fitness_types', lambda: loader(types))
    round_means = mainpage.pd.DataFrame()
    monkeypatch.setattr(mainpage.queries, 'load_round_means', lambda: loader(round_means))
    monkeypatch.setattr(mainpage.queries, 'load_non_safe_count', lambda threshold: loader(2))
    monkeypatch.setattr(mainpage, 'load_completion_counts', lambda threshold: loader(completion))

    units, injuries, types, non_safe_count, completion_counts, loaded_round_means = (
        mainpage._load_home_data()
    )

    assert units.empty
    assert injuries == {'injuries': 1}
    assert types.empty
    assert non_safe_count == 2
    assert completion_counts == completion
    assert loaded_round_means.empty
    assert len(thread_names) == 6
    assert len(set(thread_names)) == 6


def test_fitness_mean_figure_uses_latest_round_in_four_labeled_vertical_bars():
    round_means = mainpage.pd.DataFrame(
        {
            'ROUND': [1, 2],
            'MEASURED': [10, 8],
            'STRENGTH': [40.0, 50.0],
            'ENDURANCE': [30.0, 35.0],
            'CARDIO': [45.0, 48.0],
            'FLEXIBILITY': [10.0, 12.0],
        }
    )

    figure = mainpage._fitness_mean_figure(round_means)

    assert figure is not None
    assert len(figure.data) == 4
    assert [trace.x[0] for trace in figure.data] == [
        '근력',
        '근지구력',
        '심폐지구력',
        '유연성',
    ]
    assert [trace.y[0] for trace in figure.data] == [50.0, 35.0, 48.0, 12.0]
    assert all(trace.orientation != 'h' for trace in figure.data)
    assert figure.layout.yaxis.range != figure.layout.yaxis2.range
    assert figure.layout.xaxis.ticktext[0] == '근력<br>(%)'
    assert figure.layout.xaxis3.ticktext[0] == '심폐<br>지구력<br>(mL/kg/min)'
    assert all(trace.text[0].count(' ') == 0 for trace in figure.data)
    assert figure.layout.height == 270


def test_fitness_mean_figure_marks_missing_event_instead_of_skipping_latest_round():
    round_means = mainpage.pd.DataFrame(
        {
            'ROUND': [1, 2],
            'MEASURED': [10, 8],
            'STRENGTH': [40.0, 60.0],
            'ENDURANCE': [30.0, None],
            'CARDIO': [45.0, 50.0],
            'FLEXIBILITY': [10.0, 12.0],
        }
    )

    figure = mainpage._fitness_mean_figure(round_means)

    assert figure is not None
    assert figure.data[0].y[0] == 60.0
    assert figure.data[1].y[0] == 0
    assert figure.data[1].text[0] == '자료 없음'


def test_completion_sql_counts_only_non_safe_soldiers_and_latest_injury_record():
    """완료율 SQL이 확률 기준으로 걸러 세고, 부상은 부상별 최신 기록만 보는지 확인합니다."""
    sql = management_store.COMPLETION_SQL
    assert "failure_probability >= :threshold" in sql and "count(DISTINCT f.soldier_id)" in sql
    assert "DISTINCT ON (injury_id)" in sql and "ORDER BY injury_id, check_date DESC, updated_at DESC" in sql


def test_fitness_deviation_bands_are_symmetric_and_have_five_colors():
    assert [
        mainpage._fitness_deviation_band(value)
        for value in [-5.1, -5, -2.6, -2.5, 0, 2.49, 2.5, 4.99, 5, 5.1]
    ] == [0, 0, 1, 2, 2, 2, 3, 3, 4, 4]


def test_comparison_scopes_use_nationwide_as_region_baseline_and_province_as_unit_baseline():
    summaries = {
        "전체": {"total": 100},
        "지역::서울특별시": {"total": 30},
        "부대::서울특별시::1부대": {"total": 10},
    }

    region_comparison = mainpage._comparison_scopes(summaries, "서울특별시", None)
    unit_comparison = mainpage._comparison_scopes(summaries, "서울특별시", "1부대")

    assert region_comparison == (
        ("서울특별시", {"total": 30}),
        ("전국", {"total": 100}),
    )
    assert unit_comparison == (
        ("서울특별시", {"total": 30}),
        ("1부대", {"total": 10}),
    )
    assert mainpage._comparison_scopes(summaries, None, None) is None


def test_single_unit_region_selects_its_only_unit_by_default():
    assert mainpage._default_selected_unit(None, ["부산_53사단"]) == "부산_53사단"
    assert mainpage._default_selected_unit("부산_53사단", ["부산_53사단"]) == "부산_53사단"


def test_multiple_unit_region_preserves_valid_selection_and_does_not_guess():
    units = ["서울_1부대", "서울_2부대"]
    assert mainpage._default_selected_unit("서울_2부대", units) == "서울_2부대"
    assert mainpage._default_selected_unit(None, units) is None
    assert mainpage._default_selected_unit("stale-unit", units) is None
    assert mainpage._default_selected_unit(None, []) is None


def test_gwangju_and_jeonnam_records_are_grouped_as_jeollanamdo():
    units = mainpage.pd.DataFrame(
        [
            {
                "REGION_NAME": "광주광역시",
                "UNIT_NAME": "광주부대",
                "인원": 10,
                "LEVEL_1": 1,
                "LEVEL_2": 2,
                "LEVEL_3": 3,
                "LEVEL_4": 4,
                "MULTIPLE_FAILED": 2,
            },
            {
                "REGION_NAME": "전남광주",
                "UNIT_NAME": "전남광주부대",
                "인원": 15,
                "LEVEL_1": 2,
                "LEVEL_2": 3,
                "LEVEL_3": 4,
                "LEVEL_4": 6,
                "MULTIPLE_FAILED": 3,
            },
            {
                "REGION_NAME": "전라남도",
                "UNIT_NAME": "전남부대",
                "인원": 20,
                "LEVEL_1": 3,
                "LEVEL_2": 4,
                "LEVEL_3": 5,
                "LEVEL_4": 8,
                "MULTIPLE_FAILED": 4,
            },
        ]
    )

    summaries = mainpage._precompute_scope_summaries(units)

    assert "지역::광주광역시" not in summaries
    assert summaries["지역::전라남도"]["total"] == 45
    assert summaries["지역::전라남도"]["under"] == 9
    assert summaries["지역::전라남도"]["grades"]["인원"].tolist() == [6, 9, 12, 18]


def test_jeollanamdo_map_feature_includes_gwangju_without_separate_feature():
    import json
    from pathlib import Path

    geojson = json.loads(Path(mainpage.REGION_GEOJSON_PATH).read_text(encoding="utf-8"))
    feature_names = [feature["properties"]["name"] for feature in geojson["features"]]

    assert "광주광역시" not in feature_names
    assert "전라남도" in feature_names
