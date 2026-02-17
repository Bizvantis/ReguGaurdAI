from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


class RAGEngine:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
        )
        self.regulation_texts = []
        self.regulation_data = []
        self.tfidf_matrix = None

    def index_regulations(self, regulations):
        self.regulation_data = regulations
        self.regulation_texts = [
            f"{r.get('title', '')} {r.get('text', '')} {r.get('category', '')}"
            for r in regulations
        ]
        if self.regulation_texts:
            self.tfidf_matrix = self.vectorizer.fit_transform(self.regulation_texts)

    def retrieve_relevant_regulations(self, clause_text, top_k=5):
        if not self.regulation_texts or self.tfidf_matrix is None:
            return []

        query_vec = self.vectorizer.transform([clause_text])
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if similarities[idx] > 0.05:
                results.append({
                    "regulation": self.regulation_data[idx],
                    "similarity_score": float(similarities[idx]),
                })
        return results

    def match_all_clauses(self, clauses, top_k=5):
        matches = {}
        for clause in clauses:
            clause_query = f"{clause.get('title', '')} {clause.get('text', '')} {clause.get('category', '')}"
            relevant = self.retrieve_relevant_regulations(clause_query, top_k=top_k)
            matches[clause["id"]] = relevant
        return matches
