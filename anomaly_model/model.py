"""Unsupervised anomaly detection over embedded agent traces.

Combines two complementary unsupervised signals, trained purely on
unlabeled embeddings:
  - IsolationForest: a continuous "how isolated is this point" score
  - HDBSCAN: characterizes the dense manifold of normal behavior; traces
    that fall far from any dense cluster of prior runs are flagged too

Labels (when available, e.g. from synthetic data) are used only for
evaluation -- never for fitting either model.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.ensemble import IsolationForest


@dataclass
class AnomalyScore:
    isolation_score: float  # 0-1, higher = more anomalous
    is_cluster_outlier: bool
    combined_score: float  # 0-1, higher = more anomalous
    is_anomalous: bool


class AnomalyDetector:
    def __init__(self, contamination: float = 0.15, threshold: float = 0.3, random_state: int = 42):
        self.contamination = contamination
        self.threshold = threshold
        self._iforest = IsolationForest(
            contamination=contamination, random_state=random_state, n_estimators=200
        )
        self._hdbscan = HDBSCAN(min_cluster_size=5, min_samples=3)
        self._train_embeddings: Optional[np.ndarray] = None
        self._train_labels: Optional[np.ndarray] = None
        self._score_lo: float = 0.0
        self._score_hi: float = 1.0
        self._fitted = False

    def fit(self, embeddings: np.ndarray) -> "AnomalyDetector":
        self._iforest.fit(embeddings)
        self._hdbscan.fit(embeddings)
        self._train_embeddings = embeddings
        self._train_labels = self._hdbscan.labels_

        # Normalization range is fixed from TRAINING data only. Scoring a single
        # trace at inference time must be comparable against this fixed range --
        # min/max-ing over a batch of size 1 would trivially map everything to 0.
        raw_train_scores = -self._iforest.score_samples(embeddings)
        self._score_lo = float(raw_train_scores.min())
        self._score_hi = float(raw_train_scores.max())

        self._fitted = True
        return self

    def _normalize_iforest_score(self, raw_scores: np.ndarray) -> np.ndarray:
        # sklearn's score_samples: higher = more normal. Flip and min-max scale to
        # [0, 1] using the FIXED training-set range so single-point inference works.
        inverted = -raw_scores
        span = self._score_hi - self._score_lo
        if span < 1e-9:
            return np.zeros_like(inverted)
        normalized = (inverted - self._score_lo) / span
        return np.clip(normalized, 0.0, 1.0)

    def _cluster_outlier_flags(self, embeddings: np.ndarray) -> np.ndarray:
        """Flag points far from every dense training cluster's centroid.

        HDBSCAN doesn't cleanly support predicting on new points without the
        (separately packaged) approximate_predict helper, so we use a robust
        nearest-centroid-distance fallback against the fitted clusters.
        """
        assert self._train_embeddings is not None and self._train_labels is not None
        valid_mask = self._train_labels != -1
        if not valid_mask.any():
            return np.zeros(len(embeddings), dtype=bool)

        centroids = np.stack(
            [
                self._train_embeddings[self._train_labels == cid].mean(axis=0)
                for cid in sorted(set(self._train_labels[valid_mask]))
            ]
        )

        dists = np.linalg.norm(embeddings[:, None, :] - centroids[None, :, :], axis=2)
        min_dists = dists.min(axis=1)

        ref_dists = np.linalg.norm(
            self._train_embeddings[:, None, :] - centroids[None, :, :], axis=2
        ).min(axis=1)
        p90 = np.percentile(ref_dists, 90) if len(ref_dists) > 1 else ref_dists[0]
        return min_dists > p90

    def score(self, embeddings: np.ndarray) -> List[AnomalyScore]:
        if not self._fitted:
            raise RuntimeError("AnomalyDetector must be fit() before score().")

        raw_iforest = self._iforest.score_samples(embeddings)
        normalized = self._normalize_iforest_score(raw_iforest)
        cluster_outlier_flags = self._cluster_outlier_flags(embeddings)

        results = []
        for i in range(len(embeddings)):
            combined = 0.7 * float(normalized[i]) + 0.3 * float(cluster_outlier_flags[i])
            results.append(
                AnomalyScore(
                    isolation_score=float(normalized[i]),
                    is_cluster_outlier=bool(cluster_outlier_flags[i]),
                    combined_score=combined,
                    is_anomalous=combined >= self.threshold,
                )
            )
        return results

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str) -> "AnomalyDetector":
        with open(path, "rb") as f:
            return pickle.load(f)
