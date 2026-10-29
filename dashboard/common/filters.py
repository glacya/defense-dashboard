"""측정 기간·지역·부대·계급·나이 조건입니다. prefix별로 상태가 분리됩니다.

같은 prefix를 주면 페이지 사이에서 조건을 공유하고, 다른 prefix를 주면 페이지마다 독립됩니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from dashboard.common.formatting import BMI_CATEGORY_ORDER, RANK_ORDER, latest_measurements


@dataclass
class FilterResult:
    date_start: date
    date_end: date
    regions: list[str]
    units: list[str]
    ranks: list[str]
    age_range: tuple[int, int]
    bmi: list[str]
    population: pd.DataFrame
    scoped: pd.DataFrame


def _key(prefix: str, name: str) -> str:
    return f"{prefix}_{name}"


def _sync_selection(key: str, options: list[str]) -> None:
    """보관된 선택값이 현재 선택지에 없으면 전체 선택으로 맞춥니다."""
    current = st.session_state.get(key)
    if current is None or not set(current).issubset(options):
        st.session_state[key] = list(options)


def _reset_units(region_key: str, unit_key: str, units_by_region: dict) -> None:
    """지역이 바뀌면 새 지역 범위의 부대를 모두 선택합니다."""
    regions = st.session_state.get(region_key, [])
    st.session_state[unit_key] = sorted({u for r in regions for u in units_by_region.get(r, [])})


def render_filters(
    measurements: pd.DataFrame,
    prefix: str,
    show_bmi: bool = False,
    show_date: bool = True,
    show_controls: bool = True,
) -> FilterResult:
    min_date = measurements["MESURE_DE"].min().date()
    max_date = measurements["MESURE_DE"].max().date()
    if show_date:
        columns = st.columns([1.2, 1.6, 1.6, 1.25, 1.25])
        with columns[0]:
            picked = st.date_input(
                "측정일 기간",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                format="YYYY/MM/DD",
                key=_key(prefix, "date"),
            )
        dates = list(picked) if isinstance(picked, (tuple, list)) else [picked]
        if not dates:
            dates = [min_date]
        if len(dates) == 1:  # 시작일만 고른 중간 상태
            dates = dates * 2
        date_start, date_end = sorted(dates[:2])
    else:
        columns = st.columns([1.6, 1.6, 1.25, 1.25])
        date_start, date_end = min_date, max_date

    population = latest_measurements(measurements, date_start, date_end)
    if population.empty:
        st.info("선택한 측정일 기간에 해당하는 측정 기록이 없습니다.")
        st.stop()

    if not show_controls:
        regions = sorted(population["REGION_NAME"].dropna().unique().tolist())
        units = sorted(population["UNIT_NAME"].dropna().unique().tolist())
        ranks = [rank for rank in RANK_ORDER if rank in population["RANK_NAME"].unique()]
        age_range = (int(population["AGE"].min()), int(population["AGE"].max()))
        scoped = population.copy()
        st.caption(f"전체 측정 기록 기준 · 장병별 최신 측정 · 현재 조건 {len(scoped):,}명")
        return FilterResult(
            date_start=date_start,
            date_end=date_end,
            regions=regions,
            units=units,
            ranks=ranks,
            age_range=age_range,
            bmi=list(BMI_CATEGORY_ORDER),
            population=population,
            scoped=scoped,
        )

    region_key = _key(prefix, "region")
    unit_key = _key(prefix, "unit")
    rank_key = _key(prefix, "rank")
    age_key = _key(prefix, "age")
    bmi_key = _key(prefix, "bmi")

    all_regions = sorted(population["REGION_NAME"].dropna().unique().tolist())
    units_by_region = population.groupby("REGION_NAME")["UNIT_NAME"].unique().map(list).to_dict()
    _sync_selection(region_key, all_regions)
    region_column = 1 if show_date else 0
    unit_column = 2 if show_date else 1
    rank_column = 3 if show_date else 2
    age_column = 4 if show_date else 3
    with columns[region_column]:
        regions = st.multiselect(
            "지역",
            options=all_regions,
            key=region_key,
            on_change=_reset_units,
            args=(region_key, unit_key, units_by_region),
        )

    region_population = population.loc[population["REGION_NAME"].isin(regions)]
    all_units = sorted(region_population["UNIT_NAME"].dropna().unique().tolist())
    _sync_selection(unit_key, all_units)
    with columns[unit_column]:
        units = st.multiselect("부대", options=all_units, key=unit_key)

    available_ranks = [rank for rank in RANK_ORDER if rank in population["RANK_NAME"].unique()]
    _sync_selection(rank_key, available_ranks)
    with columns[rank_column]:
        ranks = st.multiselect("계급", options=available_ranks, key=rank_key)

    age_min = int(population["AGE"].min())
    age_max = int(population["AGE"].max())
    with columns[age_column]:
        if age_min < age_max:
            stored = st.session_state.get(age_key)
            if not stored or len(stored) != 2 or stored[0] < age_min or stored[1] > age_max:
                st.session_state[age_key] = (age_min, age_max)
            age_range = st.slider("나이 범위", min_value=age_min, max_value=age_max, key=age_key)
        else:
            age_range = (age_min, age_max)
            st.caption(f"나이 범위: {age_min}세")

    bmi = list(BMI_CATEGORY_ORDER)
    if show_bmi:
        _sync_selection(bmi_key, list(BMI_CATEGORY_ORDER))
        with st.expander("추가 조건", expanded=False):
            bmi = st.multiselect("BMI 구간", options=list(BMI_CATEGORY_ORDER), key=bmi_key)

    scoped = population.loc[
        population["REGION_NAME"].isin(regions)
        & population["UNIT_NAME"].isin(units)
        & population["RANK_NAME"].isin(ranks)
        & population["AGE"].between(age_range[0], age_range[1])
    ].copy()

    scope_caption = (
        f"측정 기간 {date_start:%Y-%m-%d} ~ {date_end:%Y-%m-%d} · "
        f"장병별 기간 내 최신 측정 기준 · 현재 조건 {len(scoped):,}명"
        if show_date else
        f"전체 측정 기록 기준 · 장병별 최신 측정 · 현재 조건 {len(scoped):,}명"
    )
    st.caption(scope_caption)
    return FilterResult(
        date_start=date_start,
        date_end=date_end,
        regions=regions,
        units=units,
        ranks=ranks,
        age_range=age_range,
        bmi=bmi,
        population=population,
        scoped=scoped,
    )
