
"""KNN: 6개 항목 값이 가장 비슷한 K명의 처방 빈도를 집계해 상위 3개를 추천.
 
- K는 CV 적중률 기준으로 선택
"""
from collections import Counter
 
from sklearn.neighbors import NearestNeighbors
 
from recommend_common import count_items, main, top_k
 
NAME = "KNN"
GRID = [{"k": k} for k in (10, 30, 50, 100, 200)]
 
 
class KNNModel:
    def __init__(self, k=50):
        self.k = k
 
    def fit(self, X, items):
        self.items = items
        self.global_counts = count_items(items)
        self.nn = NearestNeighbors(n_neighbors=min(self.k, len(X))).fit(X)
        return self
 
    def recommend(self, X):
        neighbors = self.nn.kneighbors(X, return_distance=False)
        recs = []
        for row in neighbors:
            c = Counter()
            for j in row:
                c.update(self.items[j])
            recs.append(top_k(c, fallback=self.global_counts))
        return recs
 
 
if __name__ == "__main__":
    main(NAME, KNNModel, GRID)
