"""Plotly·Altair 차트의 공통 색상과 밝은 레이아웃입니다."""

import streamlit as st

CHART_PALETTE = (
    "#0F766E",
    "#0891B2",
    "#2563EB",
    "#38BDF8",
    "#14B8A6",
    "#6366F1",
)
CHART_CONTINUOUS_SCALE = (
    (0.0, "#DC2626"),   # 빨강: 충족률 낮음
    (0.33, "#EAB308"),  # 노랑
    (0.66, "#16A34A"),  # 초록
    (1.0, "#1D4ED8"),   # 파랑: 충족률 높음
)
NAVY_BACKGROUND = "#FFFFFF"
NAVY_SURFACE = "#F4F8FB"
NAVY_BORDER = "#D9E3EC"
LIGHT_TEXT = "#1F3349"
MUTED_TEXT = "#53657A"
BLUE_ACCENT = "#2563EB"
CYAN_ACCENT = "#0891B2"
OK_COLOR = "#0F766E"
WARN_COLOR = "#D97706"
ALERT_COLOR = "#DC5C6A"
RANK_BAR_COLOR = "#2563EB"

BMI_COLORS = {
    "저체중": "#2563EB",
    "정상": "#0F766E",
    "과체중": "#D97706",
    "비만": "#DC5C6A",
}
FITNESS_ITEM_COLORS = {
    "근력": "#2563EB",
    "근지구력": "#0891B2",
    "심폐지구력": "#0F766E",
    "유연성": "#6366F1",
}
GRADE_COLORS = {
    "1등급": OK_COLOR,
    "2등급": CYAN_ACCENT,
    "3등급": WARN_COLOR,
    "미달": ALERT_COLOR,
}


def apply_chart_layout(figure, height: int = 300, **layout) -> None:
    """Plotly 차트에 공통 밝은 테마를 적용합니다."""
    base = dict(
        height=height,
        margin=dict(l=8, r=18, t=16, b=8),
        template="plotly_white",
        paper_bgcolor=NAVY_BACKGROUND,
        plot_bgcolor=NAVY_BACKGROUND,
        font=dict(color=LIGHT_TEXT),
        legend=dict(font=dict(color=LIGHT_TEXT)),
        hoverlabel=dict(bgcolor=NAVY_BACKGROUND, font=dict(color=LIGHT_TEXT)),
    )
    base.update(layout)
    figure.update_layout(**base)
    figure.update_xaxes(
        gridcolor=NAVY_BORDER,
        zerolinecolor=NAVY_BORDER,
        tickfont_color=LIGHT_TEXT,
        title_font_color=LIGHT_TEXT,
    )
    figure.update_yaxes(
        gridcolor=NAVY_BORDER,
        zerolinecolor=NAVY_BORDER,
        tickfont_color=LIGHT_TEXT,
        title_font_color=LIGHT_TEXT,
    )
    figure.update_traces(textfont_color=LIGHT_TEXT)


def apply_dark_layout(figure, height: int = 300, **layout) -> None:
    """이전 페이지 호출을 유지하면서 공통 밝은 차트 스타일을 적용합니다."""
    apply_chart_layout(figure, height, **layout)


def style_altair(chart, height: int = 340):
    """Altair 차트에 공통 밝은 배경, 글자색, 범주 팔레트를 적용합니다."""
    return (
        chart.properties(height=height)
        .configure(background=NAVY_BACKGROUND)
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=LIGHT_TEXT,
            titleColor=LIGHT_TEXT,
            gridColor=NAVY_BORDER,
            domainColor=NAVY_BORDER,
        )
        .configure_legend(labelColor=LIGHT_TEXT, titleColor=LIGHT_TEXT)
        .configure_range(category=list(CHART_PALETTE))
    )


def show_plotly(figure) -> None:
    st.plotly_chart(
        figure,
        width="stretch",
        theme=None,
        config={"displayModeBar": False},
    )
