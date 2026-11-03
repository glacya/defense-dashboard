import pandas as pd

from dashboard.py import queries
from dashboard.views import p04_unit_status


def test_unit_latest_query_includes_probability_without_excluding_missing_predictions():
    sql = queries.UNIT_LATEST_SQL

    assert "LEFT JOIN soldier_failure_probabilities p USING (soldier_id)" in sql
    assert "p.failure_probability" in sql


def test_risk_counts_follow_current_scope_and_exclude_missing_probabilities():
    scoped = pd.DataFrame({
        "SOLDIER_ID": ["a", "b", "c", "d", "e"],
        "RISK_LEVEL": ["안전", "경계1등급", "경계1등급", "경계3등급", pd.NA],
    })

    counts = p04_unit_status._risk_counts(scoped)

    assert counts.to_dict() == {
        "안전": 1,
        "경계1등급": 2,
        "경계2등급": 0,
        "경계3등급": 1,
    }


def test_population_classifies_available_probabilities_and_keeps_missing_unassigned(monkeypatch):
    rows = pd.DataFrame({
        "SOLDIER_ID": ["a", "b", "c", "d"],
        "MESURE_ID": [1, 2, 3, 4],
        "MESURE_DE": ["20260101", "20260102", "20260103", "20260104"],
        "BMI": [20.0, 21.0, 22.0, 23.0],
        "FAILURE_PROBABILITY": [0.299, 0.3, None, 0.7],
    })
    monkeypatch.setattr(p04_unit_status.queries, "load_unit_latest", lambda: rows.copy())
    p04_unit_status._load_population.clear()

    try:
        population = p04_unit_status._load_population()
    finally:
        p04_unit_status._load_population.clear()

    assert population.RISK_LEVEL.tolist()[:2] == ["안전", "경계1등급"]
    assert pd.isna(population.loc[2, "RISK_LEVEL"])
    assert population.loc[3, "RISK_LEVEL"] == "경계3등급"


def test_risk_distribution_figure_shows_one_scatter_trace_per_populated_level():
    scoped = pd.DataFrame({
        "SOLDIER_ID": ["s1", "s2", "s3"],
        "SOLDIER_NAME": ["홍길동", "김철수", "이영희"],
        "UNIT_NAME": ["1사단", "1사단", "2사단"],
        "BMI": [18.5, 24.2, 29.1],
        "FAILURE_PROBABILITY": [0.2, 0.4, 0.8],
        "RISK_LEVEL": ["안전", "경계1등급", "경계3등급"],
    })

    figure = p04_unit_status._risk_distribution_figure(scoped)

    people_traces = [trace for trace in figure.data if trace.name in p04_unit_status.RISK_LEVELS]
    assert [trace.name for trace in people_traces] == ["안전", "경계1등급", "경계3등급"]
    assert all(trace.type == "scatter" and len(trace.x) == 1 for trace in people_traces)
    assert [trace.x[0] for trace in people_traces] == [18.5, 24.2, 29.1]
    assert [trace.y[0] for trace in people_traces] == [0.2, 0.4, 0.8]
    assert len(figure.layout.shapes) == 7
    assert [shape.type for shape in figure.layout.shapes] == ["rect"] * 4 + ["line"] * 3
    assert [shape.fillcolor for shape in figure.layout.shapes[:4]] == [
        p04_unit_status.RISK_BAND_FILLS[level] for level in p04_unit_status.RISK_LEVELS
    ]
    assert [shape.y0 for shape in figure.layout.shapes[4:]] == [0.3, 0.5, 0.7]
    assert all(shape.line.color == p04_unit_status.NAVY_BORDER for shape in figure.layout.shapes[4:])
    assert figure.layout.xaxis.title.text == "BMI"
    assert figure.layout.yaxis.title.text == "다음 측정 미달 확률"
    assert list(figure.layout.yaxis.tickvals) == [0, 0.3, 0.5, 0.7, 1]
    assert figure.layout.plot_bgcolor == p04_unit_status.NAVY_SURFACE


def test_risk_soldier_table_exports_probability_as_percentage():
    soldiers = pd.DataFrame({
        "SOLDIER_ID": ["soldier-1"],
        "SOLDIER_NAME": ["홍길동"],
        "REGION_NAME": ["서울특별시"],
        "UNIT_NAME": ["1사단"],
        "RANK_NAME": ["병장"],
        "MESURE_DE": [pd.Timestamp("2026-01-02")],
        "BMI": [22.5],
        "BODY_FAT_PERCENTAGE": [15.2],
        "FAILURE_PROBABILITY": [0.3],
        "RISK_LEVEL": ["경계1등급"],
    })

    table = p04_unit_status._risk_soldier_table(soldiers)

    assert table.loc[0, "미달 확률(%)"] == 30.0
    assert table.loc[0, "확률 등급"] == "경계1등급"
    assert table.loc[0, "측정일"] == "2026-01-02"
