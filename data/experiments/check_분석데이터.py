import pandas as pd

from pathlib import Path

df = pd.read_csv(Path(__file__).resolve().parents[2] / "data/processed/KS_NFA_PROCESSED.csv", dtype={"SOLDIER_ID": "string"})
print( df.shape)

 
# SOLDIER_ID별 측정 횟수
counts = df.groupby("SOLDIER_ID").size()

print("전체 장병 수:", counts.size)
print("전체 측정 기록 수:", len(df))


print( counts)
# 측정 횟수별 장병 수 
# 동일한 측정 횟수를 가진 장병이 몇 명인지 빈도 계산
print(counts.value_counts().sort_index())

# 모든 장병이 정확히 3회 측정했는지
print("모두 3회 측정:", counts.eq(3).all())
print(counts.eq(3).sum())




# SOLDIER_ID별 데이터 개수
counts = df.groupby("SOLDIER_ID").size()

# 3개 이상인 SOLDIER_ID
# codes = counts[counts >= 3].index

# # 해당 SOLDIER_ID의 전체 데이터 추출
# df_3 = df[df["SOLDIER_ID"].isin(codes)]

# print("3개 이상인 SOLDIER_ID 수:", len(codes))
# print("3개 이상인 데이터 행 수:", len(df_3))
# print("추출 데이터 크기:", df_3.shape)





# 체력종목별 결측 여부
missing = pd.DataFrame({
    "근력": df["STRENGTH"].isna(),
    "근지구력": df["ENDURANCE"].isna(),
    "심폐지구력": df["CARDIO"].isna(),
    "유연성": df["FLEXIBILITY"].isna()
})

print("체력종목별 판정불가 행 수")
print(missing.sum())

print("\n하나 이상의 체력종목이 결측인 행 수")
print(missing.any(axis=1).sum())