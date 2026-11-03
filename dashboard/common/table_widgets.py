"""대시보드 표의 공통 정렬과 표시를 관리합니다."""

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler


def _table_data(data: pd.DataFrame | Styler) -> pd.DataFrame:
    if isinstance(data, Styler):
        return data.data
    if isinstance(data, pd.DataFrame):
        return data
    raise TypeError(f"표 데이터는 pandas DataFrame 또는 Styler여야 합니다: {type(data).__name__}")


def style_dataframe(data: pd.DataFrame | Styler) -> Styler:
    """속성명은 가운데, 데이터 셀은 왼쪽 정렬하는 공통 스타일을 적용합니다."""
    styles = [
        {"selector": "th.col_heading", "props": [("text-align", "center")]},
        {"selector": "td", "props": [("text-align", "left"), ("vertical-align", "middle")]},
    ]
    if isinstance(data, Styler):
        return data.set_table_styles(styles, overwrite=False)
    return data.style.set_table_styles(styles)


def _aligned_column_config(
    data: pd.DataFrame,
    column_config: dict | None,
) -> dict:
    config = dict(column_config or {})
    for column in data.columns:
        if column in config:
            column_definition = config[column]
            if isinstance(column_definition, dict):
                config[column] = {**column_definition, "alignment": "left"}
            continue
        if pd.api.types.is_numeric_dtype(data[column]):
            config[column] = st.column_config.NumberColumn(alignment="left")
    return config


def render_dataframe(data: pd.DataFrame | Styler, *args, **kwargs):
    """표를 공통 스타일로 렌더링하고 기존 열 설정을 보존합니다."""
    table_data = _table_data(data)
    kwargs["column_config"] = _aligned_column_config(table_data, kwargs.get("column_config"))
    return st.dataframe(style_dataframe(data), *args, **kwargs)
