"""최종 측정 데이터(KS_NFA_PROCESSED.csv)의 프로파일링 보고서를 HTML로 만들고 한국어로 바꿉니다.

변수별 분포, 결측, 상관관계를 한눈에 확인하기 위한 분석 스크립트이며 데이터는 바꾸지 않습니다.
현재 파이프라인에서 쓰지 않습니다.
"""

import logging
import re
from pathlib import Path

import pandas as pd
from data_profiling import ProfileReport

from data.scripts.logging_setup import caller_name, display_path, setup_logging
from data.scripts.paths import INTERMEDIATE_FITNESS_PROFILE, PROCESSED_FITNESS_PATH

logger = logging.getLogger(__name__)

# output_dir 안에 저장하는 보고서 파일 이름
REPORT_FILENAME = "KS_NFA_PROCESSED_profile.html"
REPORT_TITLE = "체력 측정 데이터 프로파일링 보고서"
# 숫자처럼 보이지만 값의 크기가 의미 없는 컬럼. 문자열로 읽어야 평균·히스토그램 같은 숫자 통계가 붙지 않는다.
IDENTIFIER_COLUMNS = ["MESURE_ID", "M_SEQ_NO", "M_CODE", "MESURE_DE"]

# 보고서의 영어 문구와 한국어 번역. 긴 문구부터 바꿔야 짧은 문구가 긴 문구 일부를 먼저 바꾸지 않는다.
_TRANSLATIONS = {
    "My Data Profiling Report": REPORT_TITLE,
    "Overview": "개요",
    "Variables": "변수",
    "Interactions": "변수 간 관계",
    "Correlations": "상관관계",
    "Missing values": "결측값",
    "Sample": "표본",
    "Alerts": "주요 알림",
    "Reproduction": "분석 정보",
    "Dataset statistics": "데이터셋 통계",
    "Number of variables": "변수 개수",
    "Number of observations": "관측치 수",
    "Missing cells (%)": "결측 셀 비율",
    "Missing cells": "결측 셀 수",
    "Duplicate rows (%)": "중복 행 비율",
    "Duplicate rows": "중복 행 수",
    "Total size in memory": "메모리 사용량 합계",
    "Average record size in memory": "레코드당 평균 메모리",
    "Variable types": "변수 유형",
    "Numeric": "숫자형",
    "Categorical": "범주형",
    "High correlation": "높은 상관관계",
    "Constant": "상수값",
    "Unique": "고유값",
    "Analysis started": "분석 시작",
    "Analysis finished": "분석 완료",
    "Software version": "라이브러리 버전",
    "Download configuration": "설정 파일 다운로드",
    "Select Columns": "변수 선택",
    "Distinct (%)": "고유값 비율",
    "Distinct": "고유값",
    "Missing (%)": "결측 비율",
    "Missing": "결측값",
    "Infinite (%)": "무한대 비율",
    "Infinite": "무한대",
    "Mean": "평균",
    "Minimum": "최솟값",
    "Maximum": "최댓값",
    "Zeros (%)": "0 값 비율",
    "Zeros": "0 값",
    "Negative (%)": "음수 비율",
    "Negative": "음수",
    "Memory size": "메모리 크기",
    "Statistics": "통계",
    "Histogram": "히스토그램",
    "Common values": "자주 나오는 값",
    "Extreme values": "극단값",
    "Quantile statistics": "분위수 통계",
    "5-th percentile": "5백분위수",
    "95-th percentile": "95백분위수",
    "Interquartile range (IQR)": "사분위 범위(IQR)",
    "Descriptive statistics": "기술 통계",
    "Standard deviation": "표준편차",
    "Coefficient of variation (CV)": "변동계수(CV)",
    "Median Absolute Deviation (MAD)": "중앙 절대 편차(MAD)",
    "Kurtosis": "첨도",
    "Skewness": "왜도",
    "Variance": "분산",
    "Monotonicity": "단조성",
    "Not monotonic": "단조성 없음",
    "Frequency (%)": "빈도(%)",
    "Frequency": "빈도",
    "Count": "개수",
    "Value": "값",
    "Words": "단어",
    "Characters": "문자",
    "Length": "길이",
    "Max length": "최대 길이",
    "Median length": "중앙 길이",
    "Mean length": "평균 길이",
    "Min length": "최소 길이",
    "Categories": "범주",
    "Scripts": "문자 체계",
    "Blocks": "블록",
    "Q1": "제1사분위수",
    "Q3": "제3사분위수",
    "median": "중앙값",
    "Duration": "분석 소요 시간",
    "Minimum 10 values": "최솟값 10개",
    "Maximum 10 values": "최댓값 10개",
    "Common Values": "자주 등장하는 값",
    "Characters and Unicode": "문자 및 유니코드",
    "Total characters": "전체 문자 수",
    "Distinct characters": "고유 문자 수",
    "Distinct categories": "고유 범주 수",
    "Distinct scripts": "고유 문자 체계 수",
    "Distinct blocks": "고유 유니코드 블록 수",
    "Unique (%)": "고유값 비율",
    "Most occurring characters": "가장 많이 나온 문자",
    "Most occurring categories": "가장 많이 나온 범주",
    "Most frequent character per category": "범주별 최빈 문자",
    "Most occurring scripts": "가장 많이 나온 문자 체계",
    "Most frequent character per script": "문자 체계별 최빈 문자",
    "Most occurring blocks": "가장 많이 나온 블록",
    "Most frequent character per block": "블록별 최빈 문자",
    "More details": "자세히 보기",
    "Toggle navigation": "탐색 메뉴 열기/닫기",
    "and": "및",
    "has constant value": "의 값이 다음으로 고정됨:",
    "is highly overall correlated with": "은 다음 항목과 높은 상관관계가 있음:",
    "has unique values": "고유값으로 구성됨",
    "(Missing)": "(결측값)",
    "(unknown)": "(알 수 없음)",
}
_TRANSLATION_PATTERNS = [
    (re.compile(rf"(?<!\w){re.escape(english)}(?!\w)"), korean)
    for english, korean in sorted(_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True)
]
# 결측 알림 문구는 숫자가 끼어 있어 사전으로 바꿀 수 없다. 예: "has 1,967 (1.6%) missing values"
_MISSING_ALERT_PATTERN = re.compile(r"has\s+([\d,]+)\s+\(([\d.]+%)\)\s+missing values")
# 스크립트·스타일 블록 안의 글자를 바꾸면 보고서 동작이 깨지므로 이 블록은 건너뛴다.
_PROTECTED_BLOCK_PATTERN = re.compile(r"(<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>)", re.IGNORECASE | re.DOTALL)
_TEXT_NODE_PATTERN = re.compile(r"(?<=>)([^<>]+)(?=<)")
_ATTRIBUTE_PATTERN = re.compile(r'(?P<prefix>\b(?:title|aria-label|alt)=["\'])(?P<value>.*?)(?P<quote>["\'])')


def read_fitness_data(path: Path) -> pd.DataFrame:
    """최종 측정 CSV를 읽습니다. 식별자 컬럼은 문자열, 나머지는 숫자로 읽어 빈칸은 결측으로 둡니다."""
    # 다른 단계는 모든 값을 문자열로 읽지만, 프로파일링은 숫자 통계가 목적이라 숫자 컬럼을 숫자로 읽는다.
    return pd.read_csv(path, encoding="utf-8-sig", dtype={column: str for column in IDENTIFIER_COLUMNS})


def create_profile(data: pd.DataFrame) -> ProfileReport:
    """탐색용(explorative) 설정으로 프로파일링 보고서를 만듭니다."""
    return ProfileReport(data, title=REPORT_TITLE, explorative=True)


def translate_text(value: str) -> str:
    """보고서 문구 하나에 들어 있는 영어 문구를 한국어로 바꿉니다."""
    for pattern, korean in _TRANSLATION_PATTERNS:
        value = pattern.sub(korean, value)
    return _MISSING_ALERT_PATTERN.sub(r"\1개 (\2) 결측값", value)


def translate_report_html(html: str) -> str:
    """보고서 HTML의 화면 글자와 title·aria-label·alt 속성을 한국어로 바꿉니다. 스크립트와 스타일 블록은 그대로 둡니다."""
    # split 결과에서 짝수 번째는 일반 HTML, 홀수 번째는 보호할 블록이다.
    parts = _PROTECTED_BLOCK_PATTERN.split(html)
    for index in range(0, len(parts), 2):
        parts[index] = _TEXT_NODE_PATTERN.sub(lambda match: translate_text(match.group(1)), parts[index])
    html = "".join(parts)
    return _ATTRIBUTE_PATTERN.sub(
        lambda match: f'{match.group("prefix")}{translate_text(match.group("value"))}{match.group("quote")}',
        html,
    )


def run(input_path: Path, output_dir: Path) -> None:
    """input_path의 측정 데이터로 프로파일링 보고서를 만들어 한국어로 바꾼 뒤 output_dir에 저장합니다."""
    # 1. 출력 경로 준비
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_FILENAME
    # 2. 입력 로드 후 보고서 생성
    data = read_fitness_data(input_path)
    create_profile(data).to_file(str(report_path))
    # 3. 저장된 HTML을 다시 읽어 한국어로 바꿔 덮어쓴다.
    report_html = report_path.read_text(encoding="utf-8")
    report_path.write_text(translate_report_html(report_html), encoding="utf-8")

    # 4. 요약 로그
    logger.info("입력 %s: %s행, %d개 컬럼", display_path(input_path), f"{len(data):,}", len(data.columns))
    logger.info("저장(프로파일링 보고서): %s", display_path(report_path))


def main() -> None:
    """data/scripts/paths.py의 기본 경로로 실행합니다."""
    setup_logging(caller_name(__file__))
    run(PROCESSED_FITNESS_PATH, INTERMEDIATE_FITNESS_PROFILE)


if __name__ == "__main__":
    main()
