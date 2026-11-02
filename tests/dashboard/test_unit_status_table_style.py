import pandas as pd

from dashboard.views.p04_unit_status import _style_summary_table


def test_unit_summary_table_uses_dashboard_chart_colors():
    summary = pd.DataFrame(
        {
            "지역": ["서울특별시"],
            "전체 장병 수": [100],
            "정상 BMI 인원": [60],
            "정상 BMI 비율(%)": [60.0],
            "과체중·비만 인원": [35],
            "저체중 인원": [5],
        }
    )

    html = _style_summary_table(summary, "지역").to_html()

    assert "#193B60" in html
    assert "#2C65B7" in html
    assert "#0F766E" in html
    assert "#D97706" in html
    assert "#DC5C6A" in html
    assert "linear-gradient" in html
    assert "text-align: center" in html
