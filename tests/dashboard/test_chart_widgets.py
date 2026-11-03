import pandas as pd

from dashboard.common.chart_widgets import PieChartWidget, RadarChartWidget
from dashboard.common.charts import (
    BAR_CORNER_RADIUS,
    CHART_PALETTE,
    apply_chart_layout,
    make_bar,
)


def test_pie_chart_uses_view_height_and_shared_default_palette():
    chart = PieChartWidget(
        pd.DataFrame({"category": ["A", "B"], "count": [3, 2]}),
        "category",
        values="count",
        height=220,
    ).build_figure()

    assert chart.layout.height == 220
    assert list(chart.data[1].marker.colors) == ["#2589FF", "#16C79A"]


def test_pie_chart_shows_exact_percentages_and_uses_shared_canvas():
    chart = PieChartWidget(
        pd.DataFrame({"category": ["A", "B"], "count": [3, 4]}),
        "category",
        values="count",
        height=240,
        show_percent=True,
    ).build_figure()

    assert list(chart.data[1].text) == [42.9, 57.1]
    assert chart.data[1].texttemplate == "%{text:.1f}%"
    assert chart.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert chart.layout.plot_bgcolor == "rgba(0,0,0,0)"


def test_pie_chart_render_uses_explicit_unique_widget_key(monkeypatch):
    from dashboard.common import chart_widgets

    rendered = []
    monkeypatch.setattr(chart_widgets.st, "plotly_chart", lambda figure, **kwargs: rendered.append(kwargs))
    monkeypatch.setattr(chart_widgets.st, "markdown", lambda *args, **kwargs: None)
    data = pd.DataFrame({"category": ["A", "B"], "count": [3, 2]})

    for key in ("comparison-left", "comparison-right"):
        PieChartWidget(
            data,
            "category",
            values="count",
            height=165,
            show_legend=True,
            legend_position="bottom",
            key=key,
        ).render()

    assert [item["key"] for item in rendered] == ["comparison-left", "comparison-right"]


def test_pie_continuous_scale_uses_shared_pie_colors_from_low_to_high():
    from dashboard.common.charts import PIE_CONTINUOUS_SCALE, PIE_PALETTE

    assert [color for _, color in PIE_CONTINUOUS_SCALE] == [
        PIE_PALETTE[3],
        PIE_PALETTE[2],
        PIE_PALETTE[1],
        PIE_PALETTE[0],
    ]


def test_fitness_deviation_scale_has_five_distinct_color_bands():
    from dashboard.common.charts import FITNESS_DEVIATION_COLORS, FITNESS_DEVIATION_SCALE

    assert len(FITNESS_DEVIATION_COLORS) == 5
    assert len({color for _, color in FITNESS_DEVIATION_SCALE}) == 5


def test_radar_chart_uses_view_height():
    chart = RadarChartWidget(labels=["A", "B"], values=[30, 70], height=310).build_figure()

    assert chart.layout.height == 310
    assert len(chart.data) == 3


def test_bar_factory_uses_shared_palette_and_view_layout():
    chart = make_bar(
        pd.DataFrame({"category": ["A", "B"], "count": [3, 2]}),
        x="category",
        y="count",
    )

    front_faces = [
        trace for trace in chart.data
        if trace.type == "scatter" and trace.fillgradient.colorscale
    ]
    assert len(front_faces) == 2
    assert all(trace.fill == "toself" for trace in front_faces)
    assert all(trace.fillgradient.type == "vertical" for trace in front_faces)
    assert all(
        trace.fillgradient.colorscale[1][1] == CHART_PALETTE[0]
        and trace.fillgradient.colorscale[0][1] == "#0B5751"
        and trace.fillgradient.colorscale[-1][1] == "#6FADA8"
        for trace in front_faces
    )
    assert chart.layout.xaxis.ticktext == ("A", "B")
    apply_chart_layout(chart, height=275)
    assert chart.layout.height == 275


def test_bar_gradient_preserves_custom_data_for_click_selection():
    chart = make_bar(
        pd.DataFrame({"location": ["ankle", "knee"], "count": [3, 2]}),
        x="location",
        y="count",
        custom_data=["location"],
    )
    front_faces = [trace for trace in chart.data if trace.fillgradient.colorscale]

    assert list(front_faces[0].customdata[0]) == ["ankle"]
    assert list(front_faces[1].customdata[0]) == ["knee"]


def test_bar_gradient_converts_bar_text_style_to_scatter_text_style():
    chart = make_bar(
        pd.DataFrame({"category": ["A", "B"], "count": [3, 2]}),
        x="category",
        y="count",
        text="count",
    )
    text_labels = [
        trace for trace in chart.data
        if trace.type == "scatter" and trace.mode == "text"
    ]

    assert len(text_labels) == 2
    assert all(trace.textposition == "top center" for trace in text_labels)
    assert [trace.text[0] for trace in text_labels] == ["3.0", "2.0"]
    chart.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="top center",
        cliponaxis=False,
        selector={"mode": "text"},
    )
    assert [trace.texttemplate for trace in text_labels] == ["%{text:.1f}%"] * 2


def test_stacked_bar_has_individual_gradients_and_a_cap_for_last_nonzero_segment():
    chart = make_bar(
        pd.DataFrame({
            "category": ["A", "A", "B", "B"],
            "series": ["one", "two", "one", "two"],
            "count": [3, 0, 4, 2],
        }),
        x="category",
        y="count",
        color="series",
        barmode="stack",
    )

    front_faces = [
        trace for trace in chart.data
        if trace.type == "scatter" and trace.fillgradient.colorscale
    ]
    assert len(front_faces) == 3
    assert chart.layout.xaxis.ticktext == ("A", "B")
    assert all(trace.type == "scatter" for trace in chart.data)


def test_stacked_bar_side_faces_align_with_each_other_and_the_top_face():
    chart = make_bar(
        pd.DataFrame({
            "category": ["A", "A"],
            "series": ["one", "two"],
            "count": [3, 2],
        }),
        x="category",
        y="count",
        color="series",
        barmode="stack",
    )

    side_faces = chart.data[:2]
    top_face = chart.data[-1]

    assert [round(value, 3) for value in side_faces[0].y] == [0, 0.175, 3.175, 3, 0]
    assert [round(value, 3) for value in side_faces[1].y] == [3, 3.175, 5.175, 5, 3]
    assert [round(value, 3) for value in top_face.y] == [5, 5, 5.175, 5.175, 5]


def test_non_categorical_bar_keeps_rounded_bar_styling():
    chart = make_bar(
        pd.DataFrame({"round": [1, 2], "count": [3, 2]}),
        x="round",
        y="count",
    )

    assert chart.data[0].type == "bar"
    assert chart.data[0].marker.cornerradius == BAR_CORNER_RADIUS
