"""교차분석: 6개 항목을 상/하위로 나눈 2^6=64개 조합 그룹별 처방 빈도 상위 3개를 추천.
 
- 상/하위 기준: 백분위 THRESHOLD(기본 50) 이상이면 상위
- 그룹 인원이 min_group 미만(데이터 희소)이면 전체 빈도 TOP3로 대체
"""
import numpy as np
import pandas as pd
 
from recommend_common import FEATURES, count_items, main, top_k
 
NAME = "Cross"
THRESHOLD = 50
GRID = [{"min_group": m} for m in (10, 30, 50)]
 
 
class CrossModel:
    def __init__(self, min_group=30):
        self.min_group = min_group
        self.weights = 2 ** np.arange(len(FEATURES))
 
    def _codes(self, X):
        return ((X >= THRESHOLD).astype(int) * self.weights).sum(axis=1)
 
    def fit(self, X, items):
        self.global_counts = count_items(items)
        codes = self._codes(X)
        self.group_counts, self.group_n = {}, {}
        for code in np.unique(codes):
            members = [items[i] for i in np.where(codes == code)[0]]
            self.group_counts[code] = count_items(members)
            self.group_n[code] = len(members)
        return self
 
    def _rec_for(self, code):
        if self.group_n.get(code, 0) >= self.min_group:
            return top_k(self.group_counts[code], fallback=self.global_counts)
        return top_k(self.global_counts)
 
    def recommend(self, X):
        return [self._rec_for(c) for c in self._codes(X)]
 
    def describe(self):
        """그룹별 인원/추천 표 (1=상위, 0=하위, 항목 순서는 FEATURES)."""
        rows = []
        for code in sorted(self.group_n):
            pattern = "".join(str((code >> i) & 1) for i in range(len(FEATURES)))
            rows.append({
                "GROUP": pattern, "N": self.group_n[code],
                "USED_GROUP_RULE": self.group_n[code] >= self.min_group,
                "RECOMMEND": ",".join(self._rec_for(code)),
            })
        return {"groups": pd.DataFrame(rows)}
 
 
if __name__ == "__main__":
    main(NAME, CrossModel, GRID)
