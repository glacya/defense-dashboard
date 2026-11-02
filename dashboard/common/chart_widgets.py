"""Reusable Plotly chart components shared by dashboard pages."""

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.common.charts import (
    CHART_WHITE,
    LIGHT_TEXT,
    PIE_CENTER_TEXT_COLOR,
    PIE_PALETTE,
    PIE_SHADOW_COLOR,
    PIE_TEXT_COLOR,
    RADAR_DEFAULT_FILL_COLOR,
    RADAR_DEFAULT_LINE_COLOR,
    RADAR_SHADOW_FILL_COLOR,
    RADAR_SHADOW_LINE_COLOR,
)


def make_pseudo_3d_donut(
    labels: list[str],
    values: list[int | float],
    colors: list[str],
    center_text: str,
    height: int,
) -> go.Figure:
    """그림자 레이어와 본 차트를 겹쳐 입체감 있는 도넛 차트를 만듭니다."""
    shadow = go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        sort=False,
        direction="clockwise",
        marker=dict(colors=[PIE_SHADOW_COLOR] * len(values)),
        textinfo="none",
        hoverinfo="skip",
        showlegend=False,
        domain=dict(x=[0.04, 0.98], y=[0.04, 0.95]),
    )

    main = go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        sort=False,
        direction="clockwise",
        pull=[0.04] * len(values),
        marker=dict(colors=colors, line=dict(color=CHART_WHITE, width=3)),
        textinfo="percent",
        textfont=dict(color=PIE_TEXT_COLOR, size=13),
        domain=dict(x=[0.02, 0.98], y=[0.08, 1.00]),
    )

    figure = go.Figure(data=[shadow, main])
    if center_text:
        figure.add_annotation(
            text=center_text,
            x=0.5,
            y=0.54,
            showarrow=False,
            font=dict(size=15, color=PIE_CENTER_TEXT_COLOR),
        )
    figure.update_layout(
        height=height,
        margin=dict(t=0, b=0, l=0, r=0),
        showlegend=False,
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=LIGHT_TEXT),
    )
    return figure


class PlotlyWidget:
    """Streamlit에서 재사용하는 Plotly 위젯의 기본 정의."""

    def __init__(self, title: str | None, height: int, key: str | None = None) -> None:
        self.title = title
        self.height = height
        self.key = key

    def build_figure(self) -> go.Figure:
        raise NotImplementedError

    def render(self) -> None:
        if self.title:
            st.subheader(self.title)
        st.plotly_chart(self.build_figure(), width="stretch", key=self.key)


class PieChartWidget(PlotlyWidget):
    """범주별 건수/비율을 도넛 파이차트로 보여주는 공통 위젯."""

    def __init__(
        self,
        data: pd.DataFrame,
        names: str,
        title: str | None = None,
        values: str = "인원",
        colors: list[str] | None = None,
        show_legend: bool = False,
        center_text: str | None = None,
        *,
        height: int,
        legend_position: str = "left",
        title_size: str | None = None,
        show_percent: bool = False,
        key: str | None = None,
    ) -> None:
        super().__init__(title=title, height=height, key=key)
        self.data = data
        self.names = names
        self.values = values
        self.colors = colors
        self.show_legend = show_legend
        self.center_text = center_text
        self.legend_position = legend_position
        self.title_size = title_size
        self.show_percent = show_percent

    def build_figure(self) -> go.Figure:
        labels = self.data[self.names].astype(str).tolist()
        palette = self.colors or PIE_PALETTE
        color_map = {label: palette[index % len(palette)] for index, label in enumerate(labels)}
        total = max(float(self.data[self.values].sum()), 1.0)
        display_percent = [
            round(float(value) / total * 100, 1)
            for value in self.data[self.values]
        ]
        figure = make_pseudo_3d_donut(
            labels=labels,
            values=self.data[self.values].tolist(),
            colors=[color_map[label] for label in labels],
            center_text=self.center_text or "",
            height=self.height,
        )
        figure.data[1].update(
            text=display_percent,
            textinfo="text" if self.show_percent else "none",
            texttemplate="%{text:.1f}%" if self.show_percent else None,
            textposition="inside",
            insidetextorientation="horizontal",
        )
        return figure

    def render(self) -> None:
        if not self.show_legend:
            super().render()
            return

        if self.title:
            if self.title_size:
                st.markdown(
                    f"<div style='font-size:{self.title_size};font-weight:700;"
                    f"line-height:1.25;margin:0 0 .35rem'>{html.escape(self.title)}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.subheader(self.title)

        palette = self.colors or PIE_PALETTE
        total = max(float(self.data[self.values].sum()), 1.0)
        legend = []
        for index, row in self.data.reset_index(drop=True).iterrows():
            label = str(row[self.names])
            count = int(row[self.values])
            color = palette[index % len(palette)]
            legend.append(
                f"<div style='display:flex;justify-content:space-between;gap:6px;line-height:1.35'>"
                f"<span style='white-space:nowrap'><span style='display:inline-block;width:9px;height:9px;"
                f"background:{color};border-radius:2px;margin-right:5px'></span>{html.escape(label)}</span>"
                f"<span style='white-space:nowrap'>{count:,}명({count / total * 100:.1f}%)</span></div>"
            )

        legend_html = (
            f"<div style='font-size:.68rem;height:{self.height}px;display:flex;"
            "flex-direction:column;justify-content:center'>"
            + "".join(legend)
            + "</div>"
        )
        if self.legend_position == "bottom":
            st.plotly_chart(
                self.build_figure(),
                width="stretch",
                config={"displayModeBar": False},
                key=self.key,
            )
            compact_legend_html = (
                "<div style='font-size:.62rem;display:flex;flex-direction:column;align-items:flex-start;"
                "gap:2px;line-height:1.2;margin:-.9rem auto 0;padding-bottom:.5rem;width:max-content'>"
                + "".join(legend)
                + "</div>"
            )
            st.markdown(compact_legend_html, unsafe_allow_html=True)
            return

        legend_column, chart_column = st.columns([1.2, 1.3], gap="small")
        with legend_column:
            st.markdown(legend_html, unsafe_allow_html=True)
        with chart_column:
            st.plotly_chart(
                self.build_figure(),
                width="stretch",
                config={"displayModeBar": False},
                key=self.key,
            )


class RadarChartWidget(PlotlyWidget):
    """항목별 점수/충족률을 스파이더 차트로 보여주는 공통 위젯."""

    def __init__(
        self,
        labels: list[str],
        values: list[float] | list[list[float]],
        title: str | None = None,
        name: str | list[str] = "현재 조건",
        line_color: str | list[str] = RADAR_DEFAULT_LINE_COLOR,
        fill_color: str | list[str] = RADAR_DEFAULT_FILL_COLOR,
        *,
        height: int,
    ) -> None:
        super().__init__(title=title, height=height)
        self.labels = labels
        self.values = values
        self.name = name
        self.line_color = line_color
        self.fill_color = fill_color

    def build_figure(self) -> go.Figure:
        labels = self.labels + [self.labels[0]] if self.labels else []
        if self.values and isinstance(self.values[0], (list, tuple, pd.Series)):
            value_series = [list(series) for series in self.values]
        else:
            value_series = [list(self.values)]
        names = self.name if isinstance(self.name, list) else [self.name]
        line_colors = self.line_color if isinstance(self.line_color, list) else [self.line_color]
        fill_colors = self.fill_color if isinstance(self.fill_color, list) else [self.fill_color]
        depth = 7

        figure = go.Figure()
        for index, raw_values in enumerate(value_series):
            scores = [
                float(value) if value is not None and not pd.isna(value) else None
                for value in raw_values
            ]
            values = scores + scores[:1]
            line = line_colors[index % len(line_colors)]
            fill = fill_colors[index % len(fill_colors)]
            series_name = names[index % len(names)]
            shadow_values = [max(0, value - depth) if value is not None else None for value in values]
            middle_values = [max(0, value - depth / 2) if value is not None else None for value in values]

            figure.add_trace(
                go.Scatterpolar(
                    r=shadow_values,
                    theta=labels,
                    fill="toself",
                    line=dict(color=RADAR_SHADOW_LINE_COLOR, width=6),
                    fillcolor=RADAR_SHADOW_FILL_COLOR,
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            figure.add_trace(
                go.Scatterpolar(
                    r=middle_values,
                    theta=labels,
                    fill="toself",
                    line=dict(color=line, width=5),
                    fillcolor=fill,
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            figure.add_trace(
                go.Scatterpolar(
                    r=values,
                    theta=labels,
                    mode="lines+markers",
                    fill="toself",
                    line=dict(color=line, width=3),
                    fillcolor=fill,
                    name=series_name,
                    hovertemplate="%{theta}<br>백분위: %{r:.1f}<extra>%{fullData.name}</extra>",
                )
            )
        figure.update_layout(
            height=self.height,
            margin=dict(t=35, b=45, l=65, r=65),
            showlegend=len(value_series) > 1,
            legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], dtick=20),
                angularaxis=dict(direction="clockwise"),
                gridshape="linear",
            ),
        )
        return figure
