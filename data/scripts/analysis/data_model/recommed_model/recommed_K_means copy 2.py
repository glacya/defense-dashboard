
"""K-MEANS: 6개 항목 값으로 군집화하고, 군집별 처방 빈도 상위 3개를 추천.
 
- K는 CV 적중률 기준으로 선택하고, 실루엣 계수는 평가 지표로 함께 보고
"""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
 
from recommend_common import FEATURES, SEED, count_items, main, top_k
 
NAME = "K_means"
GRID = [{"n_clusters": k} for k in (3, 5, 8, 10, 15, 20)]
 
 
class KMeansModel:
    def __init__(self, n_clusters=8):
        self.n_clusters = n_clusters
 
    def fit(self, X, items):
        self.km = KMeans(n_clusters=self.n_clusters, n_init=10, random_state=SEED).fit(X)
        self.global_counts = count_items(items)
        labels = self.km.labels_
        self.cluster_counts = {
            c: count_items([items[i] for i in np.where(labels == c)[0]])
            for c in range(self.n_clusters)
        }
        self.cluster_n = {c: int((labels == c).sum()) for c in range(self.n_clusters)}
        self.centers = self.km.cluster_centers_
        return self
 
    def recommend(self, X):
        return [
            top_k(self.cluster_counts[c], fallback=self.global_counts)
            for c in self.km.predict(X)
        ]
 
    def extra_metrics(self, X):
        labels = self.km.predict(X)
        if len(set(labels)) < 2:
            return {"silhouette": np.nan}
        s = silhouette_score(X, labels, sample_size=min(3000, len(X)), random_state=SEED)
        return {"silhouette": float(s)}
 
    def describe(self):
        """군집 프로필(항목별 평균 백분위) + 군집별 추천 -> 체력 유형 시각화/해석용."""
        rows = []
        for c in range(self.n_clusters):
            row = {"CLUSTER": c, "N": self.cluster_n[c]}
            row.update({f: round(v, 2) for f, v in zip(FEATURES, self.centers[c])})
            row["RECOMMEND"] = ",".join(
                top_k(self.cluster_counts[c], fallback=self.global_counts)
            )
            rows.append(row)
        return {"clusters": pd.DataFrame(rows)}
 
 
if __name__ == "__main__":
    main(NAME, KMeansModel, GRID)
 
