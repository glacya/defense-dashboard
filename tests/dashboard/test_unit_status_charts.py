import pandas as pd

from dashboard.common.charts import BMI_COLORS
from dashboard.views.p04_unit_status import _bmi_distribution_figure


def test_bmi_distribution_uses_shared_pseudo_3d_donut():
    distribution = pd.DataFrame(
        {
            "BMI 구간": ["저체중", "정상", "과체중", "비만"],
            "인원": [5, 60, 25, 10],
            "비율(%)": [5.0, 60.0, 25.0, 10.0],
        }
    )

    figure = _bmi_distribution_figure(distribution, total=100)

    assert len(figure.data) == 2
    shadow, main = figure.data
    assert shadow.type == "pie"
    assert list(shadow.marker.colors) == ["rgba(31,51,73,0.25)"] * 4
    assert shadow.hole == 0.55
    assert main.type == "pie"
    assert main.hole == 0.55
    assert list(main.marker.colors) == [BMI_COLORS[category] for category in distribution["BMI 구간"]]
    assert list(main.text) == [5.0, 60.0, 25.0, 10.0]
    assert figure.layout.annotations[0].text == "100<br>명"
