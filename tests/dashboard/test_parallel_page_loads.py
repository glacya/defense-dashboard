"""Verify that independent page data sources are loaded concurrently."""

from threading import Barrier, current_thread

import pandas as pd

from dashboard.py import fitness_overview_data, followup_probability, injury_overview_data, queries
from dashboard.views import p03_personal_detail, p06_injury_overview, p07_guidance_followup, p08_injury_followup


def _loader(barrier: Barrier, result, thread_names: list[str]):
    def load(*args, **kwargs):
        barrier.wait(timeout=3)
        thread_names.append(current_thread().name)
        return result

    return load


def test_personal_detail_loads_independent_soldier_data_in_parallel(monkeypatch):
    barrier = Barrier(4)
    thread_names: list[str] = []
    frame = pd.DataFrame()
    monkeypatch.setattr(p03_personal_detail, "load_soldier_history", _loader(barrier, frame, thread_names))
    monkeypatch.setattr(
        p03_personal_detail.queries,
        "load_soldier_injuries",
        _loader(barrier, frame, thread_names),
    )
    monkeypatch.setattr(
        p03_personal_detail,
        "_load_soldier_probability",
        _loader(barrier, frame, thread_names),
    )
    monkeypatch.setattr(
        p03_personal_detail.queries,
        "load_round_means",
        _loader(barrier, frame, thread_names),
    )

    loaded = p03_personal_detail._load_soldier_data("soldier-1")

    assert all(value is frame for value in loaded)
    assert len(set(thread_names)) == 4


def test_fitness_overview_loads_rounds_events_and_period_in_parallel(monkeypatch):
    barrier = Barrier(3)
    thread_names: list[str] = []
    rounds = pd.DataFrame()
    events = pd.DataFrame()
    period = pd.Series(dtype="object")
    monkeypatch.setattr(queries, "load_overview_rounds", _loader(barrier, rounds, thread_names))
    monkeypatch.setattr(queries, "load_overview_events", _loader(barrier, events, thread_names))
    monkeypatch.setattr(queries, "load_measure_period", _loader(barrier, period, thread_names))

    loaded = fitness_overview_data._load_overview_sources(None)

    assert all(value is expected for value, expected in zip(loaded, (rounds, events, period)))
    assert len(set(thread_names)) == 3


def test_followup_population_loads_population_and_type_catalog_in_parallel(monkeypatch):
    barrier = Barrier(2)
    thread_names: list[str] = []
    population = pd.DataFrame()
    catalog = pd.DataFrame()
    monkeypatch.setattr(
        queries,
        "load_followup_population",
        _loader(barrier, population, thread_names),
    )
    monkeypatch.setattr(queries, "load_fitness_types", _loader(barrier, catalog, thread_names))

    loaded = followup_probability._load_followup_sources()

    assert all(value is expected for value, expected in zip(loaded, (population, catalog)))
    assert len(set(thread_names)) == 2


def test_injury_overview_loads_three_independent_data_sources_in_parallel(monkeypatch):
    barrier = Barrier(3)
    thread_names: list[str] = []
    summary = pd.Series(dtype="int64")
    frame = pd.DataFrame()
    monkeypatch.setattr(
        p06_injury_overview.queries,
        "load_injury_summary",
        _loader(barrier, summary, thread_names),
    )
    monkeypatch.setattr(
        p06_injury_overview,
        "injury_people",
        _loader(barrier, frame, thread_names),
    )
    monkeypatch.setattr(
        p06_injury_overview,
        "injury_grade_table",
        _loader(barrier, frame, thread_names),
    )

    loaded = p06_injury_overview._load_page_data()

    assert loaded[0] is summary
    assert loaded[1] is frame
    assert loaded[2] is frame
    assert len(set(thread_names)) == 3


def test_guidance_followup_loads_population_and_records_in_parallel(monkeypatch):
    barrier = Barrier(2)
    thread_names: list[str] = []
    frame = pd.DataFrame()
    population = (frame, frame, 0)
    monkeypatch.setattr(
        p07_guidance_followup,
        "load_followup_population",
        _loader(barrier, population, thread_names),
    )
    monkeypatch.setattr(
        p07_guidance_followup,
        "load_records",
        lambda kind: _loader(barrier, frame, thread_names)(),
    )

    loaded = p07_guidance_followup._load_page_data()

    assert loaded[0] is frame
    assert loaded[1] is frame
    assert loaded[2] == 0
    assert loaded[3]["followup_records"] is frame
    assert len(set(thread_names)) == 2


def test_injury_followup_loads_roster_injuries_and_records_in_parallel(monkeypatch):
    barrier = Barrier(3)
    thread_names: list[str] = []
    frame = pd.DataFrame()
    monkeypatch.setattr(
        p08_injury_followup.queries,
        "load_roster",
        _loader(barrier, frame, thread_names),
    )
    monkeypatch.setattr(
        p08_injury_followup.queries,
        "load_injuries",
        _loader(barrier, frame, thread_names),
    )
    monkeypatch.setattr(
        p08_injury_followup,
        "load_records",
        lambda kind: _loader(barrier, frame, thread_names)(),
    )

    loaded = p08_injury_followup._load_page_data()

    assert all(value is frame for value in loaded)
    assert len(set(thread_names)) == 3


def test_injury_people_loads_roster_and_injury_counts_in_parallel(monkeypatch):
    barrier = Barrier(2)
    thread_names: list[str] = []
    roster = pd.DataFrame({"SOLDIER_ID": ["s1"], "SOLDIER_NAME": ["A"]})
    counts = pd.DataFrame({"SOLDIER_ID": ["s1"], "INJURY_COUNT": [2]})
    monkeypatch.setattr(
        injury_overview_data.queries,
        "load_roster",
        _loader(barrier, roster, thread_names),
    )
    monkeypatch.setattr(
        injury_overview_data.queries,
        "load_soldier_injury_counts",
        _loader(barrier, counts, thread_names),
    )

    people = injury_overview_data.injury_people()

    assert people.INJURY_COUNT.tolist() == [2]
    assert len(set(thread_names)) == 2
