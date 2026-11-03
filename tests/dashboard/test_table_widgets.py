import pandas as pd

from dashboard.common import table_widgets


def test_render_dataframe_centers_headers_and_left_aligns_all_data(monkeypatch):
    display = pd.DataFrame(
        {
            "군번": ["22-001166414"],
            "회차": [3],
            "BMI": [21.27],
            "선정 사유": ["동일 종목 최근 3회 지속 미달"],
        }
    )
    rendered = {}

    def capture(data, **kwargs):
        rendered["data"] = data
        rendered["kwargs"] = kwargs

    monkeypatch.setattr(table_widgets.st, "dataframe", capture)
    table_widgets.render_dataframe(display, hide_index=True)

    styled = rendered["data"].to_html()
    column_config = rendered["kwargs"]["column_config"]
    assert "th.col_heading" in styled
    assert "text-align: center" in styled
    assert "text-align: left" in styled
    assert column_config["회차"]["alignment"] == "left"
    assert column_config["BMI"]["alignment"] == "left"
    assert "군번" not in column_config
    assert "선정 사유" not in column_config


def test_render_dataframe_preserves_column_formats_and_styler_styles(monkeypatch):
    display = pd.DataFrame({"지역": ["서울"], "인원": [12]})
    styled_data = display.style.set_properties(subset=["지역"], **{"font-weight": "bold"})
    rendered = {}
    number_config = table_widgets.st.column_config.NumberColumn(format="%d명")
    monkeypatch.setattr(
        table_widgets.st,
        "dataframe",
        lambda data, **kwargs: rendered.update(data=data, kwargs=kwargs),
    )

    table_widgets.render_dataframe(
        styled_data,
        column_config={"인원": number_config},
    )

    html = rendered["data"].to_html()
    column_config = rendered["kwargs"]["column_config"]
    assert "font-weight: bold" in html
    assert "text-align: center" in html
    assert column_config["인원"]["alignment"] == "left"
    assert column_config["인원"]["type_config"]["format"] == "%d명"
