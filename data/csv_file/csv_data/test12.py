# ============================================================
# 국민체력100
# 체력유형 × 운동유형 관련성 분석 (카이제곱검정)
# ============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path
from scipy.stats import chi2_contingency


# ============================================================
# 1. 결과 CSV 로드
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

file_path = (
    BASE_DIR /
    "fitness_type_exercise_result.csv"
)

cluster_df = pd.read_csv(file_path)

print("데이터 로드 완료")
print("크기 :", cluster_df.shape)
print("\n컬럼")
print(cluster_df.columns.tolist())


# ============================================================
# 2. 운동유형 컬럼 처리
# ============================================================

# 운동유형이 문자열로 저장되어 있을 수 있으므로 처리
# 예: "['근력', '근지구력']" 형태로 저장되어 있을 경우

def parse_exercise_type(text):
    """
    문자열 형태의 리스트를 실제 리스트로 변환
    """
    if pd.isna(text):
        return []
    
    text = str(text).strip()
    
    # 이미 리스트 형태인 경우
    if isinstance(text, list):
        return text
    
    # 문자열 형태의 리스트 파싱
    if text.startswith("[") and text.endswith("]"):
        try:
            import ast
            return ast.literal_eval(text)
        except:
            return []
    
    return []


# 필요시 운동유형 처리
if cluster_df["운동유형"].dtype == 'object':
    # 체크: 몇 개 샘플 확인
    print("\n운동유형 샘플")
    print(cluster_df["운동유형"].head())


# ============================================================
# 3. 운동유형을 행으로 펼치기
# ============================================================

exercise_df = (
    cluster_df
    .explode("운동유형")
    .reset_index(drop=True)
)

# 결측값 제거
exercise_df = exercise_df[
    exercise_df["운동유형"].notna()
].copy()

# 빈 문자열 제거
exercise_df = exercise_df[
    exercise_df["운동유형"] != ""
].copy()

exercise_df.reset_index(drop=True, inplace=True)

print("\n펼친 데이터 크기 :", exercise_df.shape)
print("\n체력유형 × 운동유형 샘플")
print(
    exercise_df[
        ["체력유형", "본운동", "운동유형"]
    ].head(20)
)


# ============================================================
# 4. 체력유형 × 운동유형 빈도 교차표
# ============================================================

cross_count = pd.crosstab(
    exercise_df["체력유형"],
    exercise_df["운동유형"]
)

print("\n===================================")
print("체력유형 × 운동유형 빈도")
print("===================================\n")
print(cross_count)


# ============================================================
# 5. 체력유형별 운동유형 비율
# ============================================================

cross_ratio = pd.crosstab(
    exercise_df["체력유형"],
    exercise_df["운동유형"],
    normalize="index"
) * 100

print("\n===================================")
print("체력유형별 운동유형 비율(%)")
print("===================================\n")
print(cross_ratio.round(2))


# ============================================================
# 6. 체력유형별 운동처방 시각화
# ============================================================

cross_ratio.plot(
    kind="bar",
    figsize=(11, 6)
)

plt.xlabel("체력유형")
plt.ylabel("비율(%)")
plt.title("체력유형별 운동처방")
plt.xticks(rotation=0)

plt.legend(
    title="운동유형",
    loc="upper left",
    bbox_to_anchor=(1.05, 1)
)

plt.tight_layout()
plt.show()


# ============================================================
# 7. 카이제곱검정 (Chi-Square Test of Independence)
# ============================================================

print("\n===================================")
print("체력유형 × 운동유형 카이제곱검정")
print("===================================\n")

chi2, p, dof, expected = chi2_contingency(cross_count)

print("카이제곱 통계량 :", round(chi2, 4))
print("p-value        :", round(p, 6))
print("자유도         :", dof)


# ============================================================
# 8. 기대도수 (Expected Frequency)
# ============================================================

print("\n===================================")
print("기대도수 (Expected Frequency)")
print("===================================\n")

expected_df = pd.DataFrame(
    expected,
    index=cross_count.index,
    columns=cross_count.columns
)

print(expected_df.round(2))


# ============================================================
# 9. 검정 결과 해석
# ============================================================

print("\n===================================")
print("검정 결과 해석")
print("===================================\n")

alpha = 0.05  # 유의수준

print(f"유의수준(α) : {alpha}")
print(f"p-value : {p:.6f}\n")

if p < alpha:
    print("✓ 귀무가설 기각 (H0 rejected)")
    print("\n체력유형과 운동유형은")
    print("통계적으로 유의한 관련이 있습니다.")
    print(f"(p < {alpha})")
else:
    print("✗ 귀무가설 채택 (H0 not rejected)")
    print("\n체력유형과 운동유형은")
    print("통계적으로 유의한 관련이 있다고")
    print(f"보기 어렵습니다. (p >= {alpha})")


# ============================================================
# 10. 효과크기 (Cramér's V)
# ============================================================

print("\n===================================")
print("효과크기 (Cramér's V)")
print("===================================\n")

n = cross_count.sum().sum()
min_dim = min(cross_count.shape[0] - 1, cross_count.shape[1] - 1)

cramers_v = np.sqrt(chi2 / (n * min_dim))

print(f"Cramér's V : {cramers_v:.4f}")

if cramers_v < 0.1:
    effect = "무시할 수 있는 수준"
elif cramers_v < 0.3:
    effect = "약한 관련성"
elif cramers_v < 0.5:
    effect = "중간 관련성"
else:
    effect = "강한 관련성"

print(f"효과크기 해석: {effect}")


# ============================================================
# 11. 표준화 잔차 (Standardized Residuals)
# ============================================================

print("\n===================================")
print("표준화 잔차 (Standardized Residuals)")
print("===================================\n")

observed = cross_count.values
standardized_residuals = (observed - expected) / np.sqrt(expected)

residuals_df = pd.DataFrame(
    standardized_residuals,
    index=cross_count.index,
    columns=cross_count.columns
)

print("(실제도수 - 기대도수) / √기대도수\n")
print(residuals_df.round(2))

print("\n해석: |표준화잔차| > 1.96 이면 셀이 기대도수에서 현저히 벗어남")


# ============================================================
# 12. 결과 저장
# ============================================================

output_dir = BASE_DIR

# 교차표 저장
cross_count.to_csv(
    output_dir / "cross_count.csv",
    encoding="utf-8-sig"
)

cross_ratio.to_csv(
    output_dir / "cross_ratio.csv",
    encoding="utf-8-sig"
)

# 기대도수 저장
expected_df.to_csv(
    output_dir / "expected_frequency.csv",
    encoding="utf-8-sig"
)

# 표준화 잔차 저장
residuals_df.to_csv(
    output_dir / "standardized_residuals.csv",
    encoding="utf-8-sig"
)

print("\n===================================")
print("저장 완료")
print("===================================")
print(f"{output_dir / 'cross_count.csv'}")
print(f"{output_dir / 'cross_ratio.csv'}")
print(f"{output_dir / 'expected_frequency.csv'}")
print(f"{output_dir / 'standardized_residuals.csv'}")