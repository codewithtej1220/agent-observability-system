"""Learned models.

BehaviorAnomalyModel (unsupervised)
    Learns what *normal* behavior looks like from unlabeled traffic.
    - IsolationForest: how easy a run is to isolate from the bulk.
    - k-NN distance: how far a run is from its nearest normal neighbors.
    Both are converted to percentiles of the training distribution, so a
    score means "more unusual than X% of normal traffic" and is stable for
    single-run, real-time scoring.
    - HDBSCAN discovers behavioral archetypes (clusters) in normal traffic;
    new runs are assigned to an archetype via their nearest neighbors, or
    marked as novel when they are far from all of them.
    - PCA gives a 2-D projection for the behavior map in the dashboard.

FailureClassifier (supervised)
    Gradient-boosted trees predicting the failure type (or healthy). Trained
    on run *prefixes*, so it recognizes failures a few steps after they
    start, and retrained as humans label runs through the review queue.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler

from . import CLASSES


def _percentile(sorted_ref: np.ndarray, values: np.ndarray) -> np.ndarray:
    return np.searchsorted(sorted_ref, values, side="right") / max(1, len(sorted_ref))


class BehaviorAnomalyModel:
    def __init__(self, k: int = 10, random_state: int = 42):
        self.k = k
        self.random_state = random_state
        self.scaler = RobustScaler()
        self.iforest = IsolationForest(n_estimators=200, contamination="auto", random_state=random_state)
        self.nn = NearestNeighbors(n_neighbors=k)
        self.pca_cluster = PCA(n_components=8, random_state=random_state)
        self.pca_map = PCA(n_components=2, random_state=random_state)
        self.cluster_labels: Optional[np.ndarray] = None
        self.clusters: List[Dict] = []

    def fit(self, X: np.ndarray, feature_names: List[str]) -> "BehaviorAnomalyModel":
        Xs = self.scaler.fit_transform(X)
        self.iforest.fit(Xs)
        self._if_ref = np.sort(-self.iforest.score_samples(Xs))

        self.nn.fit(Xs)
        dist, _ = self.nn.kneighbors(Xs, n_neighbors=self.k + 1)
        self._knn_ref = np.sort(dist[:, 1:].mean(axis=1))  # exclude self

        Z = self.pca_cluster.fit_transform(Xs)
        self.pca_map.fit(Xs)
        min_size = max(15, len(X) // 40)
        hdb = HDBSCAN(min_cluster_size=min_size, min_samples=5)
        self.cluster_labels = hdb.fit_predict(Z)

        self.clusters = []
        for cid in sorted(set(self.cluster_labels) - {-1}):
            mask = self.cluster_labels == cid
            centroid = X[mask].mean(axis=0)
            self.clusters.append({
                "cluster_id": int(cid),
                "size": int(mask.sum()),
                "profile": {n: round(float(v), 3) for n, v in zip(feature_names, centroid)},
            })
        return self

    def score(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        Xs = self.scaler.transform(X)
        if_pct = _percentile(self._if_ref, -self.iforest.score_samples(Xs))
        dist, idx = self.nn.kneighbors(Xs)
        knn_pct = _percentile(self._knn_ref, dist.mean(axis=1))
        pct = 0.6 * if_pct + 0.4 * knn_pct
        novelty = np.clip((pct - 0.7) / 0.3, 0.0, 1.0)

        assert self.cluster_labels is not None
        neigh = self.cluster_labels[idx]
        clusters = np.full(len(X), -1)
        for i, row in enumerate(neigh):
            valid = row[row >= 0]
            if len(valid) and knn_pct[i] < 0.97:
                clusters[i] = np.bincount(valid).argmax()
        coords = self.pca_map.transform(Xs)
        return {
            "isolation_pct": if_pct,
            "knn_pct": knn_pct,
            "novelty": novelty,
            "cluster": clusters,
            "coords": coords,
        }


class FailureClassifier:
    def __init__(self, random_state: int = 42):
        self.model = HistGradientBoostingClassifier(
            max_iter=250,
            learning_rate=0.08,
            max_leaf_nodes=31,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.1,
            random_state=random_state,
        )
        self.classes = list(CLASSES)

    def fit(self, X: np.ndarray, y: List[str], sample_weight: Optional[np.ndarray] = None) -> "FailureClassifier":
        y_idx = np.array([self.classes.index(c) for c in y])
        self.model.fit(X, y_idx, sample_weight=sample_weight)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Probabilities in CLASSES order, even if a class was missing in training."""
        raw = self.model.predict_proba(X)
        out = np.zeros((len(X), len(self.classes)))
        for j, cls_idx in enumerate(self.model.classes_):
            out[:, int(cls_idx)] = raw[:, j]
        return out
