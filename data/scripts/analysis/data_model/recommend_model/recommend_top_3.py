from recommend_common import count_items, main, top_k
 
NAME = "Top_3"
GRID = [{}]
 
 
class Top3Model:
    def fit(self, X, items):
        self.counts = count_items(items)
        self.rec = top_k(self.counts)
        return self
 
    def recommend(self, X):
        return [list(self.rec) for _ in range(len(X))]
 
 
if __name__ == "__main__":
    main(NAME, Top3Model, GRID)