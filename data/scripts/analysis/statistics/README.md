# data/scripts/analysis/statistics

최종 측정 데이터(`data/processed/KS_NFA_PROCESSED.csv`)를 기술통계·추론통계로 분석하는 스크립트입니다. 데이터 파이프라인(`data/scripts/main.py`)에는 들어 있지 않고, 필요할 때 하나씩 직접 실행합니다. 대부분 Streamlit 화면으로 결과를 보여 주고, 일부는 결과 CSV·HTML을 `results/`에 저장합니다.

분석용 스크립트이므로 [모듈 작성 요령](../../../../docs/모듈-작성-요령.md)의 형식(모듈 구성 순서, 최상위 실행 코드 금지 등)을 모두 지키지는 않습니다. 경로는 `config`·`data.scripts.paths`의 상수(`PROCESSED_FITNESS_PATH`, `STATISTICS_RESULTS_DIR`, `STATISTICS_REPORTS_DIR` 등)를 쓰고, 스크립트끼리는 `from data.scripts.analysis.statistics.e01_age_descriptive import analyze_age`처럼 패키지 경로로 import합니다(`pip install -e .` 필요).

```powershell
python -m streamlit run data/scripts/analysis/statistics/<파일명>.py   # 화면이 있는 스크립트
python data/scripts/analysis/statistics/<파일명>.py                    # 결과 파일만 만드는 스크립트
```

## 파일 이름

`e{분석 번호}_{내용}.py`. 한 분석에 스크립트가 여러 개면 `e10_01_`, `e10_02_`처럼 하위 번호를 붙입니다. 분석 번호는 아래 분석 목록의 번호입니다. 분석이 아닌 도우미는 번호 없이 이름만 씁니다.

공통 기준: 장병별 날짜순 첫 측정(또는 첫 3회), 남성 19~24세 3등급 기준(`fitness_standards.grade3_standards()`), 기준값 미만이면 미달, BMI 그룹은 낮음(<18.5)·보통(18.5~25 미만)·높음(25 이상).

## 분석 목록

| 번호 | 분석 | 파일 | 방법·화면 |
|---|---|---|---|
| 1 | 연령별 체력·신체 현황 | `e01_age_descriptive.py` | 연령별 인원·평균·표준편차. `analyze_age()`(첫 측정 추출)는 다른 스크립트 대부분이 가져다 씁니다. |
| 2 | BMI 그룹별 체력·신체 현황 | `e02_bmi_descriptive.py` | BMI 그룹별 인원·평균·표준편차. `analyze_bmi()`는 4·6·13번이 씁니다. |
| 3 | 연령별 체력 평균 차이 | `e03_age_anova.py` | 등분산 여부에 따라 일반 또는 Welch 분산분석, Tukey 또는 Games–Howell 사후검정 |
| 4 | BMI 그룹별 체력 평균 차이 | `e04_bmi_anova.py` | 3번과 같은 방법을 BMI 그룹에 적용 |
| 5 | 연령과 체력 미달의 관련성 | `e05_age_failure_chi_square.py` | 카이제곱 독립성 검정, Holm 보정, Cramér's V |
| 6 | BMI 그룹과 체력 미달의 관련성 | `e06_bmi_failure_chi_square.py` | 카이제곱 독립성 검정, Holm 보정. 선택한 종목의 그룹별 조정표준화잔차(Holm 보정)도 보여 줍니다. |
| 7 | 회차별 측정값 상관 | `e07_round_correlation.py` | 1↔2·2↔3·1↔3차 피어슨·스피어먼 상관. 10-1번 결과(`results/e10_01_soldier_failure_status/fitness_risk_by_round.csv`)를 읽어 `results/e07_round_correlation/`에 저장 |
| 8 | 종목별 미달 규모 변화 | `e08_event_failure_change.py` | 종목별 1·2·3차 미달 인원·비율·변동률. 보기 방식(종목 중심·회차 중심·누적 막대)을 화면에서 고르고, 누적 막대에서는 막대를 눌러 미달 장병을 조회합니다. `analyze()`(첫 3회 추출·등급 판정)는 5·6·9·16번이 씁니다. `--export`로 `results/e08_event_failure_change/`에 저장 |
| 9 | 여러 종목 미달 장병 규모 | `e09_multi_event_failure.py` | 정확히 2·3·4개 미달과 2개 이상 미달 인원, 그룹별 인원 변동률. 그래프는 묶은 막대(인원)와 누적 막대(판정 가능 인원 대비 비율) 중 고릅니다. |
| 10 | 개인별 체력 상태 변화 | `e10_01_soldier_failure_status.py`, `e10_02_failure_status_dashboard.py` | 10-1: 장병별 첫 3회의 종목 미달·취약(미달 1개 이상)과 1차 대비 개선·악화·유지를 `results/e10_01_soldier_failure_status/fitness_risk_*.csv`로 저장. 10-2: 그 결과를 보는 화면 |
| 11 | 동일 종목 지속 미달 | `e11_persistent_failure.py` | 같은 종목에서 세 회차 모두 미달한 장병. 10-1번 결과를 읽습니다. |
| 12 | 심폐 평균 vs 기준값 44.8 | `e12_cardio_one_sample_ttest.py` | 단일표본 t검정 |
| 13 | BMI 낮음·높음 상대악력 차이 | `e13_bmi_strength_ttest.py` | 독립표본 t검정(Student 또는 Welch) |
| 14 | 체력·신체 6개 항목 분포 | `e14_measurement_distribution.py` | 기술통계, 히스토그램·박스플롯 |
| 15 | BMI와 체력의 비선형성 | `e15_bmi_nonlinearity.py` | 탭 3개: 항목별 산점도·구간별 평균·LOWESS, 5개 항목 산점도 한눈에 보기, 체력 4종목 Z-score 평균(체력 종합점수)과 BMI 구간. `--export`로 `results/e15_bmi_nonlinearity/by_metric/`·`results/e15_bmi_nonlinearity/composite_score/`에 저장 |
| 16 | 3차 측정 통과확률 예측 | `e16_01` ~ `e16_06` | 아래 "3차 통과확률" 참고 |
| 17 | 운동처방 추천 모형 | `e17_01` ~ `e17_07` | 아래 "운동처방 관련성 탐색" 참고 |
| 18 | 운동유형별 K-means 분류 | (이 폴더에 없음) | `data/scripts/analysis/clustering/` |

### 3차 통과확률 (16)

| 파일 | 내용 |
|---|---|
| `e16_01_pass_rate_by_status.py` | 첫 3회 측정에서 1·2차 충족/미달(미달 종목 0~1개 / 2개 이상) 조합별 실제 3차 통과율. `calculate()`는 나머지 16번 스크립트가 씁니다. |
| `e16_02_pass_rate_by_subgroup.py` | 위 4개 그룹을 1·2차 미달 종목 수(0~4개)로 세분화한 통과율과 장병별 소속 세부그룹 통과율 |
| `e16_03_pass_rate_by_subgroup_weighted.py` | 하위그룹의 인원 가중 기여도를 더해 상위그룹 3차 통과율을 계산 |
| `e16_04_logistic_regression.py` | 1·2차 미달 종목 수로 로지스틱 회귀를 학습해 개인별 3차 통과 확률 예측(`--first`, `--second`로 개인 예측) |
| `e16_05_method_comparison.py` | 하위그룹 통과율 방식과 로지스틱 회귀 방식의 장병별 예측·교차검증 성능 비교 |
| `e16_06_saved_result_comparison.py` | 저장된 장병별 그룹 통과율과 로지스틱 예측 결과 파일 비교 |

대시보드가 쓰는 미달 확률 모델은 이 폴더가 아니라 `data/scripts/analysis/failure_prediction/`에 있습니다.

### 운동처방 관련성 탐색 (17)

받은 운동 처방과 체력 미달 여부의 관련성(카이제곱·피셔 검정, φ, Holm 보정)을 본 분석입니다. 관련성만으로는 운동을 추천할 수 없어, 실제 추천 운동은 사람이 분류한 처방 규칙으로 고릅니다(`data/scripts/analysis/clustering/build_exercise_recommendations.py`). 이 스크립트들은 그 이전에 시도한 방법으로 남겨 둔 것입니다.

| 파일 | 내용 |
|---|---|
| `e17_01_prescription_overview.py` | 처방 운동별 포함 측정 수·포함률·순위. `load_catalog()`는 다른 17번 스크립트가 씁니다. |
| `e17_02_first_measure_failure_info.py` | 장병별 첫 측정의 종목별 미달 정보를 CSV로 저장 |
| `e17_03_failure_prescription_association.py` | 첫 측정 미달 여부와 운동 처방의 관련성 |
| `e17_04_third_failure_prescription_correlation.py` | 3차 측정 미달 여부와 당시 처방의 φ·Holm 보정(`--export`) |
| `e17_05_third_failure_prescription_heatmap.py` | 운동×체력종목 미달자 내 처방률 히트맵(`--export`) |
| `e17_06_third_prescription_dashboard.py` | 17-4번 계산을 쓰는 운동별 막대·히트맵 화면 |
| `e17_07_failure_prescription_explorer.py` | 17-4번 계산을 쓰는 종목별 관련 운동 탐색 화면 |

## 도우미

| 파일 | 내용 |
|---|---|
| `statistics_compat.py` | Python 3.10·SciPy 1.15에서 쓸 수 있는 Welch 분산분석과 Games–Howell 사후검정(3·4번이 사용) |
| `check_measurement_counts.py` | 최종 측정 데이터의 장병별 측정 횟수·결측 확인 |
| `update_summary_report.py` | 1~15번의 정량 결과를 다시 계산해 `results/summary_report/`에 저장하고 `reports/summary_results.md`의 수치를 갱신 |

## 결과 다시 만들기

스크립트가 서로의 결과를 읽으므로 이 순서로 실행합니다.

1. `e10_01_soldier_failure_status.py`
2. `e08_event_failure_change.py --export`
3. `e16_01` → `e16_02` → `e16_03` → `e16_04` → `e16_05` → `e16_06`
4. `e17_02_first_measure_failure_info.py`
5. `e07_round_correlation.py` → `e11_persistent_failure.py`

나머지 화면은 위 결과가 있으면 순서와 관계없이 실행됩니다. `e15_bmi_nonlinearity.py --export`, `e17_04`·`e17_05`의 `--export`, `update_summary_report.py`는 따로 실행합니다.

## 폴더

| 폴더 | 내용 |
|---|---|
| `results/` | 스크립트가 저장한 결과(CSV·HTML·JSON·TXT). 스크립트마다 이름이 같은 하위 폴더(예: `results/e16_04_logistic_regression/`)에 저장하고, `update_summary_report.py`는 `results/summary_report/`에 저장합니다. 만드는 스크립트가 없는 파일: `results/legacy_validation_results.json`(예전 스크립트 실행 점검 기록), `results/e07_round_correlation/soldier_round_correlation_visualization.html`, `results/fourth_submission/`(분석 결과 정리·개선안 문서) |
| `reports/` | 분석 계획표(`analysis_plan.md`, `analysis_plan_simple.md`), 결과 요약(`summary_results.md`), 코드 점검 메모(`code_review/`) |
