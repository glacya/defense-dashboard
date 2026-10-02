"""  ==========================================
위 코드는 아래와 같습니다.
1. app에서 사용할 DB(현재는 csv)를 dataloader 함수 csv_loader를 사용해 검증하여 가져온뒤 규격에 맞게 사용할 수 있도록 각 데이터를 불러옵니다.
위 코드는 다음을 위해 작성되었습니다.  
1. 정의된 CSV(DB)파일을 검증한뒤 실제로 KPI화면에서 쓰기 좋은 딕셔너리 형태로 변환하여 가져옵니다.
================== """
from pathlib import Path
import pandas as pd
from dashboard.py.loader import _load_csv


# ============================================================================
# 데이터 로딩 함수들
# ============================================================================

def get_kpi_data(data_dir: Path) -> dict:
    """
    KPI 데이터를 로드합니다.
    
    Returns:
        KPI 데이터 딕셔너리
    """
    sample = pd.DataFrame([
        {"key": "diagnosis_time", "label": "취약 체력요소 진단 소요시간", "value": 1, "unit": "분/인", "weight": 35, "delta": "▼ 기존 대비 -46분"},
        {"key": "matching_rate", "label": "부족 유형별 맞춤 운동처방", "value": 100, "unit": "%", "weight": 25, "delta": "전 유형 프로그램 연결 완료"},
        {"key": "risk_identification", "label": "불합격 위험 인원 식별률", "value": 100, "unit": "%", "weight": 20, "delta": "종목별 기준 미달량 기반"},
        {"key": "injury_registration_rate", "label": "불합격 위험 인원 식별률", "value": 100, "unit": "%", "weight": 20, "delta": "종목별 기준 미달량 기반"}
    ])
    df, _ = _load_csv("kpi_data.csv", ["key", "label", "value", "unit", "weight", "delta"], sample, data_dir)
    return {row["key"]: row.to_dict() for _, row in df.iterrows()}


def get_risk_distribution() -> pd.DataFrame:
    """
    종목별 위험군 분포 데이터를 반환합니다. (누적 막대그래프용)
    
    Returns:
        위험군 분포 데이터프레임
    """
    return pd.DataFrame({
        "event": ["종목 1: BMI", "종목 2: 심폐지구력", "종목 3: 근력", "종목 4: 근지구력", "종목 5: 유연성", "종목 6: 민첩성"],
        "high_risk": [18, 25, 10, 32, 5, 8],
        "mid_risk": [12, 15, 20, 18, 15, 10],
        "normal": [70, 60, 70, 50, 80, 82]
    })


def get_high_risk_personnel() -> pd.DataFrame:
    """
    특정 종목 고위험군 인원 명단을 반환합니다.
    
    Returns:
        고위험군 인원 정보 데이프레임
    """
    return pd.DataFrame([
        {"이름": "김민준", "계급": "하사", "소속": "본부소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"},
        {"이름": "박도윤", "계급": "상병", "소속": "1소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"},
        {"이름": "최시우", "계급": "이병", "소속": "본부소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"},
        {"이름": "홍유준", "계급": "이병", "소속": "3소대", "측정값": "35.0회", "추천 처방": "고강도 인터벌 러닝, 지속주 러닝"}
    ])


def get_persons(data_dir: Path) -> pd.DataFrame:
    """
    인원 정보를 로드합니다.
    
    Returns:
        인원 정보 데이터프레임
    """
    sample = pd.DataFrame([{
        "id": "P001", "name": "김민준", "rank": "하사", "unit_detail": "본부소대", "age": 23,
        "bmi": 27.4, "prior_fitness": "중", "injury_history": "무릎(경)", "type": "심폐지구력 부족형",
    }])
    df, _ = _load_csv(
        "persons.csv",
        ["id", "name", "rank", "unit_detail", "age", "bmi", "prior_fitness", "injury_history", "type"],
        sample,
        data_dir
    )
    return df


def get_individual_scores(person_id: str) -> pd.DataFrame:
    """
    개인별 방사형 차트를 위한 데이터를 반환합니다. (개인, 부대, 전체 평가)
    
    Args:
        person_id: 인원 ID
        
    Returns:
        개인별 점수 데이터프레임
    """
    return pd.DataFrame({
        "event": ["BMI", "근지구력", "유연성", "근력", "심폐지구력"],
        "personal": [8.0, 7.5, 6.0, 7.0, 4.0],
        "unit_avg": [6.5, 6.0, 5.0, 5.5, 5.5],
        "total_avg": [7.0, 6.5, 5.5, 6.0, 6.0]
    })