
"""로지스틱: 종목별 독립 로지스틱 회귀(입력 = 6개 값 / 10)로 처방 확률을 구하고 상위 3개 추천.
 
- 빈도 상위 TOP_N 종목(최소 MIN_POS건 이상)만 후보로 학습
- 계수 표를 저장해 항목별 기여도를 해석할 수 있음
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
 
from recommend_common import FEATURES, TOP_K, count_items, main
 
NAME = "Logistic"
TOP_N = 30
MIN_POS = 50
GRID = [{"C": c} for c in (0.1, 1.0, 10.0)]
 
 
class LogisticModel:
    def __init__(self, C=1.0):
        self.C = C
 
    def fit(self, X, items):
        counts = count_items(items)
        self.names = [i for i, n in counts.most_common(TOP_N) if n >= MIN_POS]
        Z = X / 10
        sets = [set(lst) for lst in items]
        self.models = {}
        for name in self.names:
            y = np.array([name in s for s in sets], dtype=int)
            if y.min() == y.max():
                continue
            self.models[name] = LogisticRegression(C=self.C, max_iter=1000).fit(Z, y)
        self.names = list(self.models)
        return self
 
    def recommend(self, X):
        Z = X / 10
        P = np.column_stack([self.models[n].predict_proba(Z)[:, 1] for n in self.names])
        top = np.argsort(-P, axis=1)[:, :TOP_K]
        return [[self.names[j] for j in row] for row in top]
 
    def describe(self):
        rows = []
        for n in self.names:
            m = self.models[n]
            row = {"ITEM": n, "INTERCEPT": m.intercept_[0]}
            row.update({f: c for f, c in zip(FEATURES, m.coef_[0])})
            rows.append(row)
        return {"coefficients": pd.DataFrame(rows).round(4)}
 
 
if __name__ == "__main__":
    main(NAME, LogisticModel, GRID)
 

