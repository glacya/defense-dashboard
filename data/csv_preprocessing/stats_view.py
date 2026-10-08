#pip install "setuptools<81"
#pip install fg-data-profiling 이 필요함

from pathlib import Path

from config import (
    CSV_DATA_DIR,
)
from dashboard.py.error_handlers import safe_execution
from dashboard.py.loader import (
    load_csv_data,
)

from data_profiling import ProfileReport
import re
DATA_DIR = CSV_DATA_DIR
data_path = DATA_DIR / "FIT.csv"

translations = {
		"My Data Profiling Report": "체력 측정 데이터 프로파일링 보고서",
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

@safe_execution(error_message="프로파일 데이터 로드 실패", error_type="error", reraise=True)
def load_profile_data(path: Path):
	return load_csv_data(path)


df = load_profile_data(data_path)
@safe_execution(error_message="프로파일 보고서 분석 실패", error_type="error", reraise=True)
def create_profile(data):
	return ProfileReport(data, title="체력 측정 데이터 프로파일링 보고서", explorative=True)


@safe_execution(error_message="프로파일 보고서 저장 실패", error_type="error", reraise=True)
def save_profile_report(report: ProfileReport, path: Path) -> None:
	report.to_file(str(path))

def translate_text(value):
	for english, korean in sorted(translations.items(), key=lambda item: len(item[0]), reverse=True):
		value = re.sub(rf"(?<!\w){re.escape(english)}(?!\w)", korean, value)
	return re.sub(
		r"has\s+([\d,]+)\s+\(([\d.]+%)\)\s+missing values",
		r"\1개 (\2) 결측값",
		value,
	)
def main():
	profile = create_profile(df)
	report_path = DATA_DIR / "FIT_profile.html"
	save_profile_report(profile, report_path)
	report_html = report_path.read_text(encoding="utf-8")
	attribute_pattern = re.compile(r'(?P<prefix>\b(?:title|aria-label|alt)=["\'])(?P<value>.*?)(?P<quote>["\'])')
	protected_pattern = re.compile(r"(<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>)", re.IGNORECASE | re.DOTALL)
	text_node_pattern = re.compile(r"(?<=>)([^<>]+)(?=<)")
	parts = protected_pattern.split(report_html)
	for index in range(0, len(parts), 2):
		parts[index] = text_node_pattern.sub(lambda match: translate_text(match.group(1)), parts[index])
	report_html = "".join(parts)
	report_html = attribute_pattern.sub(
		lambda match: f'{match.group("prefix")}{translate_text(match.group("value"))}{match.group("quote")}',
		report_html,
	)
	report_path.write_text(report_html, encoding="utf-8")
if __name__ == '__main__':
    main()
