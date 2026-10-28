"""Plotly·Altair 차트의 공통 색상과 다크 레이아웃입니다. 색상 원본은 이 파일에 둡니다."""

import streamlit as st

NAVY_BACKGROUND = "#071321"
NAVY_SURFACE = "#10243A"
NAVY_BORDER = "#244666"
LIGHT_TEXT = "#EFF5FB"
MUTED_TEXT = "#C6D3E0"
BLUE_ACCENT = "#2589FF"
CYAN_ACCENT = "#25C6D8"
OK_COLOR = "#16C79A"
WARN_COLOR = "#F2A93B"
ALERT_COLOR = "#F15B70"
RANK_BAR_COLOR = "#438DFF"

BMI_COLORS = {"저체중": "#438DFF", "정상": "#16C79A", "과체중": "#F2A93B", "비만": "#F15B70"}
FITNESS_ITEM_COLORS = {"근력": "#438DFF", "근지구력": "#25C6D8", "심폐지구력": "#F2A93B", "유연성": "#F15B70"}
GRADE_COLORS = {"1등급": OK_COLOR, "2등급": CYAN_ACCENT, "3등급": WARN_COLOR, "미달": ALERT_COLOR}


def apply_dark_layout(figure, height: int = 300, **layout) -> None:
    """Plotly 차트에 공통 다크 테마를 적용합니다. 개별 설정은 키워드로 덮어씁니다."""
    base = dict(
        height=height,
        margin=dict(l=8, r=18, t=16, b=8),
        template="plotly_dark",
        paper_bgcolor=NAVY_BACKGROUND,
        plot_bgcolor=NAVY_BACKGROUND,
        font=dict(color=LIGHT_TEXT),
        legend=dict(font=dict(color=MUTED_TEXT)),
    )
    base.update(layout)
    figure.update_layout(**base)
    figure.update_xaxes(gridcolor=NAVY_BORDER, zerolinecolor=NAVY_BORDER)
    figure.update_yaxes(gridcolor=NAVY_BORDER, zerolinecolor=NAVY_BORDER)


def style_altair(chart, height: int = 340):
    """Altair 차트에 배경과 축 색상을 적용합니다."""
    return (
        chart.properties(height=height)
        .configure(background=NAVY_BACKGROUND)
        .configure_view(stroke=None)
        .configure_axis(labelColor=LIGHT_TEXT, titleColor=LIGHT_TEXT)
    )


def show_plotly(figure) -> None:
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})