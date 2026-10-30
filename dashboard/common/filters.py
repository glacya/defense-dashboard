"""측정 기간·지역·부대·계급·나이 조건입니다. prefix별로 상태가 분리됩니다.

같은 prefix를 주면 페이지 사이에서 조건을 공유하고, 다른 prefix를 주면 페이지마다 독립됩니다.
선택지와 조건에 맞는 장병 목록은 DB에서 바로 받습니다(조건은 SQL의 WHERE·= ANY로, dashboard.py.queries).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from dashboard.common.formatting import BMI_CATEGORY_ORDER, RANK_ORDER, classify_bmi
from dashboard.py import queries


@dataclass
class FilterResult:
    date_start: date
    date_end: date
    regions: list[str]
    units: list[str]
    ranks: list[str]
    age_range: tuple[int, int]
    bmi: list[str]
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


def _yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def _prepare_scoped(rows: pd.DataFrame) -> pd.DataFrame:
    """DB 결과를 화면이 쓰던 모양으로 바꿉니다(MESURE_ID 정수, 측정일 날짜, BMI 구간)."""
    rows = rows.assign(
        SOLDIER_ID=rows["SOLDIER_ID"].astype(str),
        MESURE_ID=pd.to_numeric(rows["MESURE_ID"]).astype("int64"),
        MESURE_DE=pd.to_datetime(rows["MESURE_DE"], format="%Y%m%d"),
    )
    rows["BMI구간"] = classify_bmi(rows["BMI"])
    return rows.reset_index(drop=True)


def render_filters(prefix: str, show_bmi: bool = False, show_date: bool = True) -> FilterResult:
    """조건 위젯을 그리고, 조건에 맞는 장병별(기간 안) 최신 측정 목록을 돌려줍니다."""
    period = queries.load_measure_period()
    min_date = pd.to_datetime(period["FIRST_DATE"], format="%Y%m%d").date()
    max_date = pd.to_datetime(period["LAST_DATE"], format="%Y%m%d").date()
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

    # 선택지: 기간 안 최신 측정 장병의 지역·부대·계급 조합과 나이 범위(수십 행)
    options = queries.load_filter_options(_yyyymmdd(date_start), _yyyymmdd(date_end))
    if options.empty:
        st.info("선택한 측정일 기간에 해당하는 측정 기록이 없습니다.")
        st.stop()

    region_key = _key(prefix, "region")
    unit_key = _key(prefix, "unit")
    rank_key = _key(prefix, "rank")
    age_key = _key(prefix, "age")
    bmi_key = _key(prefix, "bmi")

    all_regions = sorted(options["REGION_NAME"].unique().tolist())
    units_by_region = options.groupby("REGION_NAME")["UNIT_NAME"].unique().map(list).to_dict()
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

    all_units = sorted(options.loc[options["REGION_NAME"].isin(regions), "UNIT_NAME"].unique().tolist())
    _sync_selection(unit_key, all_units)
    with columns[unit_column]:
        units = st.multiselect("부대", options=all_units, key=unit_key)

    available_ranks = [rank for rank in RANK_ORDER if rank in set(options["RANK_NAME"])]
    _sync_selection(rank_key, available_ranks)
    with columns[rank_column]:
        ranks = st.multiselect("계급", options=available_ranks, key=rank_key)

    age_min = int(options["AGE_MIN"].min())
    age_max = int(options["AGE_MAX"].max())
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

    scoped = _prepare_scoped(queries.load_filtered_latest(
        _yyyymmdd(date_start), _yyyymmdd(date_end), regions, units, ranks, age_range))

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
        scoped=scoped,
    )
