"""여러 개요 화면에서 공유하는 요약 카드와 차트 영역 위젯."""

from collections.abc import Callable, Sequence
from contextlib import nullcontext

import streamlit as st

from dashboard.common.charts import show_plotly


Metric = tuple[str, str, str]


def render_metric_cards(
    metrics: Sequence[Metric],
    *,
    container_key: str | None,
    key_prefix: str,
    clickable: bool,
    clickable_keys: set[str],
    scope_signature: str,
    help_text: str,
) -> str | None:
    """요약 지표를 카드로 표시하고 클릭된 지표 키를 반환합니다."""
    clicked_metric = None
    container = st.container(key=container_key) if container_key else nullcontext()
    with container:
        for column, (metric_key, label, value) in zip(st.columns(len(metrics)), metrics):
            if clickable and metric_key in clickable_keys:
                if column.button(
                    f"**{label}**  \n**{value}**",
                    key=f"{key_prefix}_{metric_key}_{scope_signature}",
                    width="stretch",
                    help=help_text,
                ):
                    clicked_metric = metric_key
            else:
                column.metric(label, value, border=True)
    return clicked_metric


def render_paged_plotly_chart(
    chart,
    *,
    page: int,
    page_count: int,
    page_key: str,
    caption: str,
    on_page_change: Callable[[str, int, int], None],
    previous_label: str = "← 이전",
    next_label: str = "다음 →",
) -> None:
    """이전·다음 버튼과 페이지 캡션을 포함한 Plotly 차트 영역을 표시합니다."""
    previous_col, chart_col, next_col = st.columns([1, 14, 1], vertical_alignment="center")
    previous_col.button(
        previous_label,
        disabled=page == 0,
        key=f"{page_key}_previous",
        on_click=on_page_change,
        args=(page_key, -1, page_count),
    )
    with chart_col:
        st.caption(caption)
        show_plotly(chart)
    next_col.button(
        next_label,
        disabled=page >= page_count - 1,
        key=f"{page_key}_next",
        on_click=on_page_change,
        args=(page_key, 1, page_count),
    )
