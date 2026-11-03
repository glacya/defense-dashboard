"""Plotly·Altair 차트의 공통 색상과 밝은 레이아웃입니다."""

import math

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

CHART_PALETTE = (
    "#0F766E",
    "#0891B2",
    "#2563EB",
    "#38BDF8",
    "#14B8A6",
    "#6366F1",
)
PIE_PALETTE = ("#2589FF", "#16C79A", "#F2A93B", "#F15B70", "#6E7F95")
_PIE_GRADIENT_COLORS = tuple(reversed(PIE_PALETTE[:-1]))
PIE_CONTINUOUS_SCALE = tuple(
    (index / (len(_PIE_GRADIENT_COLORS) - 1), color)
    for index, color in enumerate(_PIE_GRADIENT_COLORS)
)
FITNESS_DEVIATION_COLORS = ("#F15B70", "#F2A93B", "#FACC15", "#16C79A", "#2589FF")
FITNESS_DEVIATION_SCALE = (
    (0.0, FITNESS_DEVIATION_COLORS[0]),
    (0.12499, FITNESS_DEVIATION_COLORS[0]),
    (0.12501, FITNESS_DEVIATION_COLORS[1]),
    (0.37499, FITNESS_DEVIATION_COLORS[1]),
    (0.37501, FITNESS_DEVIATION_COLORS[2]),
    (0.62499, FITNESS_DEVIATION_COLORS[2]),
    (0.62501, FITNESS_DEVIATION_COLORS[3]),
    (0.87499, FITNESS_DEVIATION_COLORS[3]),
    (0.87501, FITNESS_DEVIATION_COLORS[4]),
    (1.0, FITNESS_DEVIATION_COLORS[4]),
)
CHART_WHITE = "#FFFFFF"
BAR_EDGE_DARKENING = 0.74
BAR_EDGE_FALLBACK = "#334155"
BAR_EDGE_WIDTH = 1.25
BAR_CORNER_RADIUS = "5px"
BAR_FRONT_LIGHTENING = 0.4
BAR_SIDE_DARKENING = 0.58
BAR_TOP_LIGHTENING = 0.56
BAR_DEPTH_RATIO = 0.16
PIE_SHADOW_COLOR = "rgba(31,51,73,0.25)"
PIE_TEXT_COLOR = CHART_WHITE
PIE_CENTER_TEXT_COLOR = "#1F3349"
RADAR_DEFAULT_LINE_COLOR = "#2563EB"
RADAR_DEFAULT_FILL_COLOR = "rgba(37, 99, 235, 0.18)"
RADAR_SHADOW_LINE_COLOR = "rgba(31, 51, 73, 0.25)"
RADAR_SHADOW_FILL_COLOR = "rgba(31, 51, 73, 0.10)"
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
CYAN_ACCENT = "#0891B2"
OK_COLOR = "#0F766E"
WARN_COLOR = "#D97706"
ALERT_COLOR = "#DC5C6A"

BMI_COLORS = {
    "저체중": "#2563EB",
    "정상": "#0F766E",
    "과체중": "#D97706",
    "비만": "#DC5C6A",
}
GRADE_COLORS = {
    "1등급": OK_COLOR,
    "2등급": CYAN_ACCENT,
    "3등급": WARN_COLOR,
    "미달": ALERT_COLOR,
}


def _darken_bar_color(color: str) -> str:
    if not color.startswith("#"):
        return BAR_EDGE_FALLBACK

    value = color[1:]
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    if len(value) != 6:
        return BAR_EDGE_FALLBACK

    try:
        channels = [int(value[index:index + 2], 16) for index in (0, 2, 4)]
    except ValueError:
        return BAR_EDGE_FALLBACK
    darkened = [round(channel * BAR_EDGE_DARKENING) for channel in channels]
    return "#" + "".join(f"{channel:02X}" for channel in darkened)


def _lighten_bar_color(color: str, amount: float) -> str:
    if not color.startswith("#"):
        return color

    value = color[1:]
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    if len(value) != 6:
        return color

    try:
        channels = [int(value[index:index + 2], 16) for index in (0, 2, 4)]
    except ValueError:
        return color
    lightened = [round(channel + (255 - channel) * amount) for channel in channels]
    return "#" + "".join(f"{channel:02X}" for channel in lightened)


def _bar_fill_gradient(color: str) -> list[list[str | float]]:
    return [
        [0.0, _darken_bar_color(color)],
        [0.38, color],
        [1.0, _lighten_bar_color(color, BAR_FRONT_LIGHTENING)],
    ]


def _style_categorical_bars(figure, bar_traces, categories):
    trace_count = len(bar_traces)
    mode = figure.layout.barmode or "relative"
    is_stacked = mode in {"stack", "relative"}
    group_width = 0.8
    front_faces = []
    side_faces = []
    top_faces = []
    value_labels = []
    positive_bases = {category: 0.0 for category in categories}
    negative_bases = {category: 0.0 for category in categories}
    top_trace_by_category = {}
    stack_depth_y = {}
    if is_stacked:
        stack_extents = {}
        positive_extents = {category: 0.0 for category in categories}
        negative_extents = {category: 0.0 for category in categories}
        for trace_index, trace in enumerate(bar_traces):
            for point_index, (category, raw_value) in enumerate(zip(trace.x, trace.y)):
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(value) or value == 0:
                    continue
                if trace.base is None:
                    extents = negative_extents if value < 0 else positive_extents
                    base = extents[category]
                    extents[category] += value
                elif isinstance(trace.base, (list, tuple)):
                    base = float(trace.base[point_index])
                else:
                    base = float(trace.base)
                top = base + value
                direction = 1 if value > 0 else -1
                key = (category, direction)
                previous_extent = stack_extents.get(key, 0.0)
                stack_extents[key] = (
                    max(previous_extent, top)
                    if direction > 0
                    else min(previous_extent, top)
                )
                if value != 0:
                    top_trace_by_category[category] = trace_index
        stack_depth_y = {
            key: max(abs(extent) * 0.035, 0.01)
            for key, extent in stack_extents.items()
        }

    for trace_index, trace in enumerate(bar_traces):
        has_legend_entry = False
        x_values = list(trace.x)
        y_values = list(trace.y)
        raw_colors = trace.marker.color
        if isinstance(raw_colors, str):
            colors = [raw_colors] * len(y_values)
        elif isinstance(raw_colors, (list, tuple)) and all(
            isinstance(color, str) for color in raw_colors
        ):
            colors = list(raw_colors)
        else:
            colors = [CHART_PALETTE[trace_index % len(CHART_PALETTE)]] * len(y_values)

        if is_stacked:
            bar_width = group_width * 0.9
            offset = 0.0
        else:
            bar_width = group_width * 0.78 / trace_count
            offset = (
                group_width / trace_count
            ) * (trace_index - (trace_count - 1) / 2)

        if trace.width is not None:
            bar_width = float(trace.width)
        if trace.offset is not None:
            offset = float(trace.offset)

        for point_index, (category, raw_value) in enumerate(zip(x_values, y_values)):
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value) or value == 0:
                continue

            if is_stacked and trace.base is None:
                bases = negative_bases if value < 0 else positive_bases
                base = bases[category]
                bases[category] += value
            elif trace.base is None:
                base = 0.0
            elif isinstance(trace.base, (list, tuple)):
                base = float(trace.base[point_index])
            else:
                base = float(trace.base)
            top = base + value

            category_index = categories.index(category)
            center = category_index + offset
            left = center - bar_width / 2
            right = center + bar_width / 2
            depth = min(bar_width * BAR_DEPTH_RATIO, 0.12)
            direction = 1 if value > 0 else -1
            depth_y = (
                stack_depth_y.get((category, direction), max(abs(top) * 0.035, 0.01))
                if is_stacked
                else max(abs(top) * 0.035, 0.01)
            )
            color = colors[point_index % len(colors)]
            edge_color = _darken_bar_color(color)
            vertex_customdata = None
            if trace.customdata is not None:
                vertex_customdata = [trace.customdata[point_index]] * 5

            hover_label = figure.layout.yaxis.title.text or "값"
            category_label = str(category)
            series_label = str(trace.name) if trace.name else ""
            hover_text = (
                f"{category_label}"
                + (f"<br>{series_label}" if series_label else "")
                + f"<br>{hover_label}: {value:g}"
            )
            common = {
                "mode": "lines",
                "hoveron": "fills",
                "showlegend": False,
                "legendgroup": trace.legendgroup,
                "customdata": vertex_customdata,
                "text": [hover_text] * 5,
                "hovertemplate": "%{text}<extra></extra>",
            }
            side_faces.append(
                go.Scatter(
                    x=[right, right + depth, right + depth, right, right],
                    y=[
                        base,
                        base + direction * depth_y,
                        top + direction * depth_y,
                        top,
                        base,
                    ],
                    fill="toself",
                    fillcolor=edge_color,
                    line=dict(color=edge_color, width=0.5),
                    **common,
                )
            )
            front_faces.append(
                go.Scatter(
                    x=[left, right, right, left, left],
                    y=[base, base, top, top, base],
                    fill="toself",
                    fillgradient=dict(
                        type="vertical",
                        colorscale=_bar_fill_gradient(color),
                    ),
                    line=dict(color=edge_color, width=BAR_EDGE_WIDTH),
                    name=str(trace.name or ""),
                    showlegend=bool(trace.showlegend and not has_legend_entry),
                    **{key: value for key, value in common.items() if key != "showlegend"},
                )
            )
            has_legend_entry = True

            if trace.text is not None:
                text = trace.text[point_index]
                if text is not None:
                    text_position = trace.textposition or "auto"
                    if text_position == "auto":
                        text_position = "top center"
                    elif text_position == "outside":
                        text_position = "top center"
                    elif text_position == "inside":
                        text_position = "middle center"
                    value_labels.append(
                        go.Scatter(
                            x=[center],
                            y=[top],
                            mode="text",
                            text=[text],
                            texttemplate=trace.texttemplate,
                            textposition=text_position,
                            textfont=trace.textfont.to_plotly_json(),
                            cliponaxis=trace.cliponaxis,
                            hoverinfo="skip",
                            showlegend=False,
                        )
                    )

            is_bar_top = (
                not is_stacked
                or top_trace_by_category.get(category) == trace_index
            )
            if is_bar_top:
                top_faces.append(
                    go.Scatter(
                        x=[left, right, right + depth, left + depth, left],
                        y=[
                            top,
                            top,
                            top + direction * depth_y,
                            top + direction * depth_y,
                            top,
                        ],
                        fill="toself",
                        fillcolor=_lighten_bar_color(color, BAR_TOP_LIGHTENING),
                        line=dict(
                            color=_lighten_bar_color(color, BAR_TOP_LIGHTENING),
                            width=0.5,
                        ),
                        **common,
                    )
                )
        trace.showlegend = False

    figure.data = ()
    figure.add_traces([*side_faces, *front_faces, *top_faces, *value_labels])
    depth = min(group_width * BAR_DEPTH_RATIO, 0.12)
    figure.update_xaxes(
        type="linear",
        tickmode="array",
        tickvals=list(range(len(categories))),
        ticktext=[str(category) for category in categories],
        range=[-0.5, len(categories) - 0.5 + depth],
    )
    return figure


def _style_non_categorical_bars(figure, bar_traces):
    values = []
    for trace in bar_traces:
        raw_values = trace.x if trace.orientation == "h" else trace.y
        for value in raw_values:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                values.append(number)

    minimum = min(values, default=0.0)
    maximum = max(values, default=0.0)
    for trace in bar_traces:
        raw_values = trace.x if trace.orientation == "h" else trace.y
        colors = trace.marker.color
        if isinstance(colors, str):
            base_colors = [colors] * len(raw_values)
        elif isinstance(colors, (list, tuple)) and all(
            isinstance(color, str) for color in colors
        ):
            base_colors = list(colors)
        else:
            base_colors = [BAR_EDGE_FALLBACK] * len(raw_values)
        shaded = []
        for color, raw_value in zip(base_colors, raw_values):
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                shaded.append(color)
                continue
            amount = (
                BAR_FRONT_LIGHTENING * (1 - (value - minimum) / (maximum - minimum))
                if maximum > minimum
                else 0
            )
            shaded.append(_lighten_bar_color(color, amount))
        trace.marker.color = shaded
        trace.marker.line.update(
            color=[_darken_bar_color(color) for color in shaded],
            width=BAR_EDGE_WIDTH,
        )
        if figure.layout.barmode != "stack" and (
            figure.layout.barmode != "relative" or len(bar_traces) == 1
        ):
            trace.marker.cornerradius = BAR_CORNER_RADIUS
    return figure


def style_bar_chart(figure: go.Figure) -> go.Figure:
    """범주형 막대는 개별 수직 그라데이션과 입체 측면으로 표시합니다."""
    bar_traces = [trace for trace in figure.data if trace.type == "bar"]
    if not bar_traces:
        return figure
    if any(trace.orientation == "h" for trace in bar_traces):
        return _style_non_categorical_bars(figure, bar_traces)

    categories = []
    category_array = figure.layout.xaxis.categoryarray
    if category_array is not None:
        categories.extend(category_array)
    for trace in bar_traces:
        for category in trace.x:
            if category not in categories:
                categories.append(category)
    if not categories or not all(isinstance(category, str) for category in categories):
        return _style_non_categorical_bars(figure, bar_traces)
    return _style_categorical_bars(figure, bar_traces, categories)


def make_bar(*args, **kwargs):
    """Plotly Express 막대 차트를 생성합니다."""
    kwargs.setdefault("color_discrete_sequence", list(CHART_PALETTE))
    return style_bar_chart(px.bar(*args, **kwargs))


def make_line(*args, **kwargs):
    """Plotly Express 선 차트를 생성합니다."""
    kwargs.setdefault("color_discrete_sequence", list(CHART_PALETTE))
    return px.line(*args, **kwargs)


def make_choropleth(*args, **kwargs):
    """Plotly Express 단계구분도를 생성합니다."""
    return px.choropleth(*args, **kwargs)


def make_figure(*args, **kwargs):
    """Graph Objects 기반 차트의 Figure를 생성합니다."""
    return go.Figure(*args, **kwargs)


def apply_chart_layout(figure, height: int, **layout) -> None:
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


def style_altair(chart, height: int):
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
