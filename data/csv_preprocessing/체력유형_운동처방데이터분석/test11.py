# %%
# ============================================================
# 국민체력100
# 체력유형 KMeans + 운동처방 분석
# ============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


# ============================================================
# 1. 데이터 불러오기
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

file_path = BASE_DIR / \
    "KS_NFA_FTNESS_MESURE_MVN_PRSCRPTN_GNRLZ_INFO_202607.csv"

df = pd.read_csv(file_path)

print("원본 크기 :", df.shape)


# ============================================================
# 2. 필요한 컬럼
# ============================================================

use_cols = [

    "MESURE_AGE_CO",
    "SEXDSTN_FLAG_CD",

    "MESURE_IEM_001_VALUE",    # 신장
    "MESURE_IEM_002_VALUE",    # 체중
    "MESURE_IEM_003_VALUE",    # 체지방률

    "MESURE_IEM_035_VALUE",    # 트레드밀
    "MESURE_IEM_037_VALUE",    # YMCA
    "MESURE_IEM_020_VALUE",    # 20m 왕복오래달리기

    "MESURE_IEM_028_VALUE",    # 상대악력
    "MESURE_IEM_019_VALUE",    # 교차윗몸일으키기
    "MESURE_IEM_012_VALUE",    # 앉아윗몸앞으로굽히기

    "MVM_PRSCRPTN_CN"          # 운동처방
]

df = df[use_cols].copy()


# ============================================================
# 3. 컬럼 이름 변경
# ============================================================

df.rename(columns={

    "MESURE_AGE_CO": "나이",
    "SEXDSTN_FLAG_CD": "성별",

    "MESURE_IEM_001_VALUE": "신장",
    "MESURE_IEM_002_VALUE": "체중",
    "MESURE_IEM_003_VALUE": "체지방률",

    "MESURE_IEM_035_VALUE": "트레드밀검사",
    "MESURE_IEM_037_VALUE": "YMCA스텝검사",
    "MESURE_IEM_020_VALUE": "20m왕복오래달리기",

    "MESURE_IEM_028_VALUE": "상대악력",
    "MESURE_IEM_019_VALUE": "교차윗몸일으키기",
    "MESURE_IEM_012_VALUE": "유연성",

    "MVM_PRSCRPTN_CN": "운동처방"

}, inplace=True)


print(df.columns)


# ============================================================
# 4. 숫자형으로 변환
# ============================================================

numeric_cols = [

    "나이",
    "신장",
    "체중",
    "체지방률",

    "트레드밀검사",
    "YMCA스텝검사",
    "20m왕복오래달리기",

    "상대악력",
    "교차윗몸일으키기",
    "유연성"
]


for col in numeric_cols:

    df[col] = pd.to_numeric(
        df[col],
        errors="coerce"
    )


# ============================================================
# 5. 성별 확인
# ============================================================

print("\n성별 값")
print(df["성별"].value_counts(dropna=False))


# ============================================================
# 6. 20대 추출
# ============================================================

df = df[
    df["나이"].between(20, 29)
].copy()


# ★ 중요
# 남성 코드 확인 후 아래 중 맞는 것을 사용
#
# df = df[df["성별"] == "M"].copy()
# df = df[df["성별"] == "남"].copy()
# df = df[df["성별"] == 1].copy()


# ★ 인덱스 완전히 새로 생성
df = df.reset_index(drop=True)

print("\n20대 데이터 :", df.shape)
print("인덱스 중복 :", df.index.duplicated().sum())


# ============================================================
# 7. BMI 계산
# ============================================================

df["BMI"] = (
    df["체중"]
    /
    ((df["신장"] / 100) ** 2)
)


print(
    df[
        ["신장", "체중", "BMI", "체지방률"]
    ].head()
)


# ============================================================
# 8. 결측치 확인
# ============================================================

check_cols = [

    "상대악력",
    "교차윗몸일으키기",
    "유연성",

    "20m왕복오래달리기",
    "트레드밀검사",
    "YMCA스텝검사",

    "BMI",
    "체지방률"
]


print("\n결측치")

print(
    df[check_cols]
    .isna()
    .sum()
)


# ============================================================
# 9. Z-score 함수
# ============================================================

def make_zscore(series):

    mean = series.mean()
    std = series.std(ddof=0)

    if pd.isna(std) or std == 0:

        return pd.Series(
            np.nan,
            index=series.index
        )

    return (series - mean) / std


# ============================================================
# 10. 심폐지구력 각각 표준화
# ============================================================
#
# 논문에서는 서로 단위가 다른 심폐검사를
# Z-score로 표준화하여 하나의 척도로 통합
# ============================================================

df["z_왕복"] = make_zscore(
    df["20m왕복오래달리기"]
)

df["z_트레드밀"] = make_zscore(
    df["트레드밀검사"]
)

df["z_YMCA"] = make_zscore(
    df["YMCA스텝검사"]
)


# ============================================================
# 11. 심폐지구력 통합
# ============================================================

cardio_cols = [
    "z_왕복",
    "z_트레드밀",
    "z_YMCA"
]


df["심폐지구력"] = (
    df[cardio_cols]
    .mean(axis=1, skipna=True)
)


print("\n심폐지구력 확인")

print(
    df[
        [
            "20m왕복오래달리기",
            "트레드밀검사",
            "YMCA스텝검사",
            "심폐지구력"
        ]
    ].head(20)
)


# ============================================================
# 12. 논문 기준 6개 변수
# ============================================================
#
# 근력       = 상대악력
# 근지구력   = 교차윗몸일으키기
# 심폐지구력 = 심폐검사 통합값
# 유연성     = 앉아윗몸앞으로굽히기
# BMI
# 체지방률
# ============================================================

df["근력"] = df["상대악력"]

df["근지구력"] = df["교차윗몸일으키기"]


fitness_cols = [

    "근력",
    "근지구력",
    "심폐지구력",
    "유연성",
    "BMI",
    "체지방률"
]


print("\n6개 변수")

print(
    df[fitness_cols].head()
)


print("\n6개 변수 결측치")

print(
    df[fitness_cols]
    .isna()
    .sum()
)


# ============================================================
# 13. KMeans용 데이터 생성
# ============================================================

cluster_df = (
    df
    .dropna(subset=fitness_cols)
    .copy()
    .reset_index(drop=True)
)


print("\n전체 :", len(df))

print(
    "군집분석 사용 :",
    len(cluster_df)
)


# ============================================================
# 14. 백분위 점수
# ============================================================
#
# rank(pct=True)
#
# 작은 값 → 낮은 백분위
# 큰 값   → 높은 백분위
#
# 0~1 값을 ×100
# ============================================================


# 근력
cluster_df["근력_P"] = (
    cluster_df["근력"]
    .rank(pct=True)
    * 100
)


# 근지구력
cluster_df["근지구력_P"] = (
    cluster_df["근지구력"]
    .rank(pct=True)
    * 100
)


# 심폐지구력
cluster_df["심폐지구력_P"] = (
    cluster_df["심폐지구력"]
    .rank(pct=True)
    * 100
)


# 유연성
cluster_df["유연성_P"] = (
    cluster_df["유연성"]
    .rank(pct=True)
    * 100
)


# ============================================================
# 15. BMI / 체지방률
# ============================================================
#
# 논문에서는 방향을 반대로 맞춰
# 점수가 높을수록 양호하도록 처리
# ============================================================

cluster_df["BMI_P"] = (
    100
    -
    cluster_df["BMI"]
    .rank(pct=True)
    * 100
)


cluster_df["체지방률_P"] = (
    100
    -
    cluster_df["체지방률"]
    .rank(pct=True)
    * 100
)


# ============================================================
# 16. 최종 백분위 변수
# ============================================================

p_cols = [

    "근력_P",
    "근지구력_P",
    "심폐지구력_P",
    "유연성_P",
    "BMI_P",
    "체지방률_P"
]


print("\n백분위 점수")

print(
    cluster_df[p_cols]
    .head()
)


print("\n백분위 통계")

print(
    cluster_df[p_cols]
    .describe()
    .T
)


# ============================================================
# 17. KMeans 직전 Z-score 표준화
# ============================================================
#
# StandardScaler
#
# 평균 = 0
# 표준편차 = 1
# ============================================================

scaler = StandardScaler()

X = scaler.fit_transform(
    cluster_df[p_cols]
)


print("\n표준화 결과 shape :", X.shape)


# ============================================================
# 18. K=2~9 비교
# ============================================================

k_result = []


for k in range(2, 10):

    model = KMeans(
        n_clusters=k,
        random_state=42,
        n_init=10
    )

    labels = model.fit_predict(X)

    sil = silhouette_score(
        X,
        labels
    )

    k_result.append(
        [
            k,
            model.inertia_,
            sil
        ]
    )


k_result = pd.DataFrame(

    k_result,

    columns=[
        "K",
        "Inertia",
        "Silhouette"
    ]
)


print("\nK 비교")

print(k_result)


# ============================================================
# 19. Elbow
# ============================================================

plt.figure(figsize=(7, 4))

plt.plot(
    k_result["K"],
    k_result["Inertia"],
    marker="o"
)

plt.xlabel("K")
plt.ylabel("Inertia")
plt.title("Elbow Method")

plt.show()


# ============================================================
# 20. Silhouette
# ============================================================

plt.figure(figsize=(7, 4))

plt.plot(
    k_result["K"],
    k_result["Silhouette"],
    marker="o"
)

plt.xlabel("K")
plt.ylabel("Silhouette Score")
plt.title("Silhouette Score")

plt.show()


# ============================================================
# 21. K=4 최종 군집
# ============================================================

kmeans = KMeans(
    n_clusters=4,
    random_state=42,
    n_init=10
)


cluster_df["cluster"] = (
    kmeans.fit_predict(X)
)


print("\n군집별 인원")

print(
    cluster_df["cluster"]
    .value_counts()
    .sort_index()
)


# ============================================================
# 22. 군집별 백분위 평균
# ============================================================

profile = (
    cluster_df
    .groupby("cluster")[p_cols]
    .mean()
)


# 보기 좋게 이름 변경

profile.columns = [

    "근력",
    "근지구력",
    "심폐지구력",
    "유연성",
    "BMI",
    "체지방률"
]


print("\n===================================")
print("군집별 프로파일")
print("===================================")

print(
    profile.round(2)
)


# ============================================================
# 23. 논문 기준 군집 이름 결정
# ============================================================
#
# 여기서는 단순하고 안정적인 방식으로 결정
#
# ① 전체 평균이 가장 낮은 군집
#       → 고위험군
#
# ② 남은 군집 중 전체 평균이 가장 높은 군집
#       → 개선가능군
#
# ③ 남은 2개 중 근력+근지구력이 높은 군집
#       → 근력편중군
#
# ④ 마지막
#       → 유연성편중군
#
# 주의:
# 최종적으로 profile을 반드시 확인해야 함.
# ============================================================


# 각 군집 전체 평균
profile["전체평균"] = (
    profile.mean(axis=1)
)


# ------------------------------------------------------------
# 고위험군
# ------------------------------------------------------------

high_risk = (
    profile["전체평균"]
    .idxmin()
)


# ------------------------------------------------------------
# 고위험군 제외
# ------------------------------------------------------------

remain = (
    profile
    .drop(index=high_risk)
)


# ------------------------------------------------------------
# 개선가능군
# ------------------------------------------------------------

improvable = (
    remain["전체평균"]
    .idxmax()
)


# ------------------------------------------------------------
# 두 군집 남기기
# ------------------------------------------------------------

remain2 = (
    remain
    .drop(index=improvable)
    .copy()
)


# ------------------------------------------------------------
# 근력편중 점수
# ------------------------------------------------------------

remain2["근력점수"] = (
    remain2["근력"]
    +
    remain2["근지구력"]
)


strength_cluster = (
    remain2["근력점수"]
    .idxmax()
)


# ------------------------------------------------------------
# 마지막 군집
# ------------------------------------------------------------

flex_cluster = [

    x for x in remain2.index

    if x != strength_cluster

][0]


# ============================================================
# 24. 군집명 딕셔너리
# ============================================================

cluster_name = {

    high_risk:
        "고위험군",

    improvable:
        "개선가능군",

    strength_cluster:
        "근력편중군",

    flex_cluster:
        "유연성편중군"
}


print("\n군집 이름")

print(cluster_name)


cluster_df["체력유형"] = (
    cluster_df["cluster"]
    .map(cluster_name)
)


print("\n체력유형 인원")

print(
    cluster_df["체력유형"]
    .value_counts()
)


# ============================================================
# 25. 군집명 포함 프로파일
# ============================================================

profile_result = (
    profile
    .drop(columns="전체평균")
    .copy()
)


profile_result["체력유형"] = (
    profile_result.index
    .map(cluster_name)
)


print("\n===================================")
print("최종 군집 프로파일")
print("===================================")

print(
    profile_result.round(2)
)


# ============================================================
# 26. 운동처방에서 본운동 추출
# ============================================================

def get_main_exercise(text):

    if pd.isna(text):
        return np.nan

    text = str(text)


    # / 기준 분리
    parts = text.split("/")


    for part in parts:

        if "본운동" in part:

            # 본운동: 제거
            result = (
                part
                .replace("본운동:", "")
                .replace("본운동 :", "")
                .strip()
            )

            return result


    return np.nan


cluster_df["본운동"] = (
    cluster_df["운동처방"]
    .apply(get_main_exercise)
)


print("\n본운동 추출")

print(
    cluster_df[
        ["운동처방", "본운동"]
    ].head(10)
)


# ============================================================
# 27. 운동 분류표
# ============================================================

exercise_map = {

    # 심폐지구력
    "달리기": "심폐지구력",
    "자전거타기": "심폐지구력",
    "실내 자전거타기": "심폐지구력",
    "계단 올라갔다 내려오기": "심폐지구력",
    "계단 오르기": "심폐지구력",
    "줄넘기": "심폐지구력",
    "수영": "심폐지구력",
    "트레드밀": "심폐지구력",
    "걷기": "심폐지구력",

    # 근지구력
    "윗몸올리기": "근지구력",
    "윗몸일으키기": "근지구력",
    "누워서 배가로근 수축": "근지구력",
    "버피": "근지구력",

    # 근력
    "웨이트 트레이닝": "근력",
    "웨이트트레이닝": "근력",
    "스쿼트": "근력",
    "팔굽혀펴기": "근력",
    "다리 밀기": "근력",
    "레그 프레스": "근력",
    "덤벨": "근력",
    "바벨": "근력",

    # 유연성
    "스트레칭": "유연성",
    "몸통 비틀기": "유연성",
    "앞으로 굽히기": "유연성"
}


# ============================================================
# 28. 운동유형 찾기
# ============================================================

def classify_exercise(text):

    if pd.isna(text):
        return []


    result = []


    for exercise, category in exercise_map.items():

        if exercise in text:

            result.append(category)


    # 중복 제거
    result = list(
        dict.fromkeys(result)
    )


    return result


cluster_df["운동유형"] = (
    cluster_df["본운동"]
    .apply(classify_exercise)
)


print("\n운동유형")

print(
    cluster_df[
        [
            "체력유형",
            "본운동",
            "운동유형"
        ]
    ].head(20)
)


# ============================================================
# 29. 운동유형을 행으로 펼치기
# ============================================================

exercise_df = (
    cluster_df
    .explode("운동유형")
    .reset_index(drop=True)
)


# 빈 값 제거
exercise_df = exercise_df[
    exercise_df["운동유형"].notna()
].copy()


exercise_df = exercise_df[
    exercise_df["운동유형"] != ""
].copy()


# 다시 인덱스 초기화
exercise_df.reset_index(
    drop=True,
    inplace=True
)


# ============================================================
# 30. 체력유형 × 운동유형 빈도표
# ============================================================

cross_count = pd.crosstab(

    exercise_df["체력유형"],

    exercise_df["운동유형"]
)


print("\n===================================")
print("체력유형 × 운동유형")
print("===================================")

print(cross_count)


# ============================================================
# 31. 체력유형별 운동유형 비율
# ============================================================

cross_ratio = pd.crosstab(

    exercise_df["체력유형"],

    exercise_df["운동유형"],

    normalize="index"

) * 100


print("\n===================================")
print("체력유형별 운동유형 비율(%)")
print("===================================")

print(
    cross_ratio.round(2)
)


# ============================================================
# 32. 시각화
# ============================================================

cross_ratio.plot(
    kind="bar",
    figsize=(11, 6)
)

plt.xlabel("체력유형")
plt.ylabel("비율(%)")

plt.title(
    "체력유형별 운동처방"
)

plt.xticks(
    rotation=0
)

plt.legend(
    title="운동유형",
    loc="upper left",
    bbox_to_anchor=(1.05, 1)
)

plt.tight_layout()

plt.show()


# ============================================================
# 33. 최종 저장
# ============================================================

output_path = (
    BASE_DIR /
    "fitness_type_exercise_result.csv"
)


cluster_df.to_csv(
    output_path,
    index=False,
    encoding="utf-8-sig"
)


print("\n저장 완료")
print(output_path)


# ============================================================
# 34. 군집 프로파일 저장
# ============================================================

profile_path = (
    BASE_DIR /
    "fitness_cluster_profile.csv"
)


profile_result.to_csv(
    profile_path,
    encoding="utf-8-sig"
)


# ============================================================
# 35. 운동처방 교차표 저장
# ============================================================

cross_count.to_csv(
    BASE_DIR / "exercise_count.csv",
    encoding="utf-8-sig"
)


cross_ratio.to_csv(
    BASE_DIR / "exercise_ratio.csv",
    encoding="utf-8-sig"
)


print("모든 분석 완료")
# %%
