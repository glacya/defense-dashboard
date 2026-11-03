# failure_prediction/experiments

다음 회차 미달 예측 모델을 정하고 검증할 때 해 본 실험입니다. 데이터 파이프라인(`data/scripts/main.py`)에는 들어 있지 않습니다. 지금 쓰는 코드는 한 단계 위 `failure_prediction/`에 있고, 모델은 `failure_prediction/models/fail_probability_model.joblib`(`paths.FAILURE_MODEL_PATH`)입니다.

| 파일 | 내용 |
|---|---|
| `build_fail_rate_by_round.py` | 3회 측정 장병의 회차별 "N개 이상 종목 미달" 비율표와 3차 미달 인원표. 정답 기준(3차에서 2개 종목 이상 미달)을 정할 때 썼습니다. 출력은 `data/intermediate/experiments/fail_rate_by_round/`(Git 제외). |
| `build_failure_probability_model.py` | 1·2차로 3차 미달 확률을 예측하는 모형 비교와 검증(기준선, 규칙, 로지스틱 회귀 2종, 확률 4등급 관리·위험·경계·안전, 재현율·정밀도) Streamlit 화면. 지금 모델(`train_failure_probability_model.py`)은 여기서 채택한 BMI 파생변수 로지스틱 회귀를 학습만 합니다. `python -m streamlit run`으로 실행합니다. |
| `build_human_vs_model_quiz.py`, `human_vs_model_quiz_template.html` | 사람과 모델이 같은 1·2차 측정값으로 3차 미달을 맞히는 실험 페이지를 만듭니다. 출력은 `data/intermediate/human_vs_model/`(측정값이 들어 있어 Git 제외). |
| `human_vs_model_experiment.md` | 위 실험의 계획: 문항 뽑기, 정답 규칙, 시간 측정 방법, 한계 |
