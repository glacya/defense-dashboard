import pandas as pd

df = pd.read_csv("data/processed/KS_NFA_PROCESSED.csv")
print( df.shape)

 
# M_CODE별 측정 횟수
counts = df.groupby("M_CODE").size()

print("전체 장병 수:", counts.size)
print("전체 측정 기록 수:", len(df))

# 측정 횟수별 장병 수
print(counts.value_counts().sort_index())

# 모든 장병이 정확히 3회 측정했는지
print("모두 3회 측정:", counts.eq(3).all())




# M_CODE별 데이터 개수
counts = df.groupby("M_CODE").size()

# 3개 이상인 M_CODE
codes = counts[counts >= 3].index

# 해당 M_CODE의 전체 데이터 추출
df_3 = df[df["M_CODE"].isin(codes)]

print("3개 이상인 M_CODE 수:", len(codes))
print("3개 이상인 데이터 행 수:", len(df_3))
print("추출 데이터 크기:", df_3.shape)





# 체력종목별 결측 여부
missing = pd.DataFrame({
    "근력": df["REL_GRIP"].isna(),
    "근지구력": df["CROSS_UP"].isna(),
    "심폐지구력": df[["TRAD", "STEP", "20M_RUN"]].isna().all(axis=1),
    "유연성": df["SIT_REACH"].isna()
})

print("체력종목별 판정불가 행 수")
print(missing.sum())

print("\n하나 이상의 체력종목이 결측인 행 수")
print(missing.any(axis=1).sum())