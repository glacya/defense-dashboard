"""여러 페이지에서 쓰는 장병 상세 패널입니다."""

import pandas as pd
import streamlit as st

from dashboard.common.formatting import FITNESS_ITEM_LABELS, add_deficiency_flags


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