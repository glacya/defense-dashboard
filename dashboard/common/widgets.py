"""여러 페이지에서 쓰는 장병 상세 패널입니다."""

import html
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.common.formatting import FITNESS_ITEM_LABELS, add_deficiency_flags


class PlotlyWidget:
    """Streamlit에서 재사용하는 Plotly 위젯의 기본 정의."""

    def __init__(self, title: str | None = None, height: int = 330) -> None:
        self.title = title
        self.height = height

    def build_figure(self):
        raise NotImplementedError

    def render(self) -> None:
        if self.title:
            st.subheader(self.title)
        st.plotly_chart(self.build_figure(), width="stretch")


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
        height: int = 330,
    ) -> None:
        super().__init__(title=title, height=height)
        self.data = data
        self.names = names
        self.values = values
        self.colors = colors
        self.show_legend = show_legend

    def build_figure(self):
        labels = self.data[self.names].astype(str).tolist()
        palette = self.colors or ["#2589FF", "#16C79A", "#F2A93B", "#F15B70", "#6E7F95"]
        color_map = {label: palette[index % len(palette)] for index, label in enumerate(labels)}
        figure = px.pie(
            self.data,
            names=self.names,
            values=self.values,
            hole=0.55,
            color=self.names,
            color_discrete_map=color_map,
        )
        figure.update_traces(textinfo="none")
        figure.update_layout(
            height=self.height,
            margin=dict(t=10, b=10, l=10, r=10),
            showlegend=False,
        )
        return figure

    def render(self) -> None:
        super().render()
        if not self.show_legend:
            return

        palette = self.colors or ["#2589FF", "#16C79A", "#F2A93B", "#F15B70", "#6E7F95"]
        total = max(float(self.data[self.values].sum()), 1.0)
        legend = []
        for index, row in self.data.reset_index(drop=True).iterrows():
            label = str(row[self.names])
            count = int(row[self.values])
            color = palette[index % len(palette)]
            legend.append(
                f"<div style='display:flex;justify-content:space-between;gap:8px;line-height:1.7'>"
                f"<span><span style='display:inline-block;width:10px;height:10px;background:{color};"
                f"border-radius:2px;margin-right:6px'></span>{html.escape(label)}</span>"
                f"<span>{count:,}명({count / total * 100:.1f}%)</span></div>"
            )
        st.markdown("<div style='font-size:.78rem'>" + "".join(legend) + "</div>", unsafe_allow_html=True)


class RadarChartWidget(PlotlyWidget):
    """항목별 점수/충족률을 스파이더 차트로 보여주는 공통 위젯."""

    def __init__(
        self,
        labels: list[str],
        values: list[float],
        title: str | None = None,
        name: str = "현재 조건",
        line_color: str = "#2589FF",
        fill_color: str = "rgba(37, 137, 255, 0.25)",
        height: int = 360,
    ) -> None:
        super().__init__(title=title, height=height)
        self.labels = labels
        self.values = values
        self.name = name
        self.line_color = line_color
        self.fill_color = fill_color

    def build_figure(self):
        labels = self.labels + [self.labels[0]] if self.labels else []
        values = self.values + [self.values[0]] if self.values else []
        figure = go.Figure(go.Scatterpolar(
            r=values,
            theta=labels,
            fill="toself",
            line=dict(color=self.line_color, width=2),
            fillcolor=self.fill_color,
            name=self.name,
        ))
        figure.update_layout(
            height=self.height,
            margin=dict(t=25, b=20, l=35, r=35),
            showlegend=False,
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%"),
                angularaxis=dict(direction="clockwise"),
            ),
        )
        return figure


def reset_soldier_detail_dismissal() -> None:
    """새 장병 행을 선택하면 상세정보 모달을 다시 열 수 있게 합니다."""
    st.session_state["soldier_detail_dismissed_id"] = None


def dismiss_soldier_detail_dialog() -> None:
    """모달을 닫으면 현재 장병을 기록해 재실행 시 자동으로 다시 열리지 않게 합니다."""
    st.session_state["soldier_detail_dismissed_id"] = st.session_state.get("selected_soldier_id")


def render_soldier_details(
    soldier: pd.Series,
    history: pd.DataFrame | None = None,
    injuries: pd.DataFrame | None = None,
) -> None:
    """선택 장병의 기본 정보·회차별 변화·부상 이력을 표시합니다."""
    st.markdown(f"### {soldier['SOLDIER_NAME']} · {soldier['RANK_NAME']}")
    st.caption(f"{soldier['SOLDIER_ID']} · {soldier['REGION_NAME']} · {soldier['UNIT_NAME']}")

    identity = st.columns(3)
    identity[0].metric("군번", str(soldier["SOLDIER_ID"]))
    identity[1].metric("계급", str(soldier["RANK_NAME"]))
    identity[2].metric("나이", f"{soldier['AGE']:.0f}세")

    measurement = st.columns(3)
    measurement[0].metric("측정일", soldier["MESURE_DE"].strftime("%Y-%m-%d"))
    measurement[1].metric("키", f"{soldier['HEIGHT']:.1f} cm")
    measurement[2].metric("체중", f"{soldier['WEIGHT']:.1f} kg")

    fitness = st.columns(3)
    fitness[0].metric("BMI", f"{soldier['BMI']:.1f}")
    fitness[1].metric("체지방률", f"{soldier['BODY_FAT_PERCENTAGE']:.1f}%")
    fitness[2].metric("BMI 구간", str(soldier["BMI구간"]))

    if history is not None:
        soldier_history = add_deficiency_flags(
            history.loc[history["SOLDIER_ID"].eq(soldier["SOLDIER_ID"])].sort_values("MESURE_DE")
        )
        if not soldier_history.empty:
            st.markdown("#### 회차별 체력 측정 변화")
            table = soldier_history[[
                "MESURE_DE", "STRENGTH", "ENDURANCE", "CARDIO", "FLEXIBILITY",
                "등급_STRENGTH", "등급_ENDURANCE", "등급_CARDIO", "등급_FLEXIBILITY", "체력미달",
            ]].rename(columns={
                "MESURE_DE": "측정일", "STRENGTH": "근력", "ENDURANCE": "근지구력",
                "CARDIO": "심폐지구력", "FLEXIBILITY": "유연성", "등급_STRENGTH": "근력 등급",
                "등급_ENDURANCE": "근지구력 등급", "등급_CARDIO": "심폐지구력 등급",
                "등급_FLEXIBILITY": "유연성 등급", "체력미달": "미달 여부",
            })
            st.dataframe(
                table,
                hide_index=True,
                width="stretch",
                column_config={
                    "측정일": st.column_config.DateColumn(format="YYYY-MM-DD"),
                    "근력": st.column_config.NumberColumn(format="%.1f"),
                    "근지구력": st.column_config.NumberColumn(format="%.1f"),
                    "심폐지구력": st.column_config.NumberColumn(format="%.1f"),
                    "유연성": st.column_config.NumberColumn(format="%.1f"),
                },
            )
            latest_flags = soldier_history.iloc[-1]
            deficient = [label for column, label in FITNESS_ITEM_LABELS.items() if bool(latest_flags[f"미달_{column}"])]
            st.caption("현재 미달 종목: " + (", ".join(deficient) if deficient else "없음"))

    if injuries is not None:
        soldier_injuries = injuries.loc[injuries["SOLDIER_ID"].eq(soldier["SOLDIER_ID"])].copy()
        st.markdown(f"#### 개인 부상 이력 · {len(soldier_injuries):,}건")
        if soldier_injuries.empty:
            st.info("등록된 부상 이력이 없습니다.")
        else:
            st.dataframe(
                soldier_injuries[["INJURY_ID", "INJURY_CATEGORY", "INJURY_LOCATION", "SEVERITY", "PREVENTABILITY"]].rename(columns={
                    "INJURY_ID": "부상 ID", "INJURY_CATEGORY": "부상 분류", "INJURY_LOCATION": "부위",
                    "SEVERITY": "심각도", "PREVENTABILITY": "예방 가능",
                }),
                hide_index=True,
                width="stretch",
            )


@st.dialog("장병 상세정보", width="large", on_dismiss=dismiss_soldier_detail_dialog)
def show_soldier_detail_dialog(soldier: pd.Series, history: pd.DataFrame, injuries: pd.DataFrame) -> None:
    render_soldier_details(soldier, history, injuries)
