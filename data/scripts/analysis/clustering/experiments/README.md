# clustering/experiments

체력 유형 분류(등급 + K-means 군집)와 추천 운동을 정할 때 해 본 실험입니다. 데이터 파이프라인(`data/scripts/main.py`)에는 들어 있지 않습니다. 지금 쓰는 코드는 한 단계 위 `clustering/`에 있고, 모델은 `clustering/models/`에 있습니다.

실험 기록으로 남긴 코드라 대부분 예전 중간 데이터(`data/intermediate/enlistment_filter/passed.csv`)와 예전 컬럼 이름(`M_CODE`, `REL_GRIP`, `CROSS_UP`, `SIT_REACH`)을 입력으로 씁니다. 지금 데이터로 바로 다시 돌아가지는 않을 수 있습니다. 출력은 Git에서 제외되는 `data/intermediate/experiments/`(`paths.INTERMEDIATE_EXPERIMENTS`)에 씁니다.

## grading/: 등급 나누기

| 파일 | 내용 | 지금 코드 |
|---|---|---|
| `percentile_grade.py` | 종목별 백분위의 평균으로 1~4등급(평균 70·50·30 이상)을 나누고 등급별 CSV와 인원 비율표를 저장 | `classify_measurements_by_percentile.py` |
| `zscore_grades.py` | 백분위 대신 z-score 평균으로 등급을 나누는 대안(경계 +0.524·0·−0.524)과 군집 수별 실루엣 계수 | — |

## clustering/: 등급별 군집

| 파일 | 내용 | 지금 코드 |
|---|---|---|
| `percentile_gap_k.py` | 종목 간 백분위 편차(어느 쪽이 상대적으로 강하고 약한가)로 K-means·계층적 군집, 실루엣 계수로 k 비교. `grading/percentile_grade.py`의 함수를 씁니다. | `train_cluster_model.py` |
| `grade_cluster_figures.py` | 등급별 편차 기반 K-means(k=4)의 PCA 산점도, 군집별 편차 히트맵, 군집별 체력수준 분포 그림 | `train_cluster_model.py`, `assign_grade_and_cluster.py`의 편차 표 |

## recommendation/: 받은 운동 처방으로 추천하는 모델

국민체력100에서 실제로 받은 운동 처방을 맞히는 방식으로 추천 모델을 만들어 비교한 실험입니다. 이 방식으로는 쓸 만한 추천이 나오지 않아, 지금은 사람이 분류한 처방 규칙으로 고릅니다(`build_exercise_recommendations.py`).

| 파일 | 내용 |
|---|---|
| `select_data_all.py`, `select_data_personal.py`, `processed_select_data.py` | 입력 준비: 1·2등급 제외·개인별 첫 측정·처방 있는 데이터를 고르고 백분위 특성과 처방 라벨로 바꿈 |
| `recommend_common.py` | 추천 모델 공통 모듈: 데이터 읽기, 80/20 분할, 5-fold 교차검증, 적중률(추천 3개 중 실제 처방 1개 이상)·정밀도 |
| `recommend_top_3.py`, `recommend_cross.py`, `recommend_knn.py`, `recommend_logistic.py`, `recommend_k_means.py` | 추천 모델 5종: 전체 빈도 상위 3개, 6항목 상/하 교차 그룹, KNN, 종목별 로지스틱 회귀, K-means 군집 |
| `compare_result.py` | 5개 모델의 결과 비교표·차트·요약 보고서 |
| `recommend_k_means_report.py`, `kmeans4_6.py` | 논문 방식의 K-means 체력유형 분석 보고서(상관·VIF·실루엣, K=4와 6 비교) |
| `groupbybin.py`, `cross_group_counts.py` | 집단(교차 그룹·K-means 군집·전체)별 처방 빈도·처방률과 연관성 검정, 교차 그룹 인원 |

모델 5종은 `recommend_common`을 함께 쓰므로 `python -m data.scripts.analysis.clustering.experiments.recommendation.recommend_knn`처럼 모듈로 실행합니다.
