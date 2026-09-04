#!/usr/bin/env python3
"""Exact weighted-vs-materialized resampling tests for C14E."""

from __future__ import annotations

import numpy as np

from c14e_paired_statistics import (
    BUDGETS, materialized_metrics, probability_preparation, ranking_preparation,
    weighted_probability_metrics, weighted_workload_metrics,
)


def main() -> int:
    y = np.asarray([0, 1, 1, 0, 1, 0, 1, 0], dtype=np.int8)
    p = np.asarray([0.2, 0.9, 0.7, 0.6, 0.7, 0.1, 0.8, 0.3])
    groups = np.asarray(["A", "A", "A", "A", "B", "B", "B", "B"])
    ties = np.asarray([f"t{i}" for i in range(len(y))])
    weights = np.asarray([2, 0, 1, 3, 0, 2, 1, 1], dtype=np.int32)
    indices = np.repeat(np.arange(len(y)), weights)

    direct_prob, direct_work = materialized_metrics(y, p, groups, ties, indices)
    weighted_prob = weighted_probability_metrics(weights, probability_preparation(y, p))
    weighted_work = weighted_workload_metrics(y, weights, ranking_preparation(p, groups, ties))
    assert np.allclose(direct_prob, weighted_prob, atol=1e-15)
    for budget in BUDGETS:
        assert np.allclose(direct_work[budget][:2], weighted_work[budget][:2], atol=1e-15)
        direct_counts = np.bincount(indices, minlength=len(y))
        assert (weighted_work[budget][2] <= direct_counts).all()
        assert int(weighted_work[budget][2].sum()) == int(direct_work[budget][2].sum())
    assert sum(int(weighted_work[b][2].sum()) for b in BUDGETS) > 0
    print("C14E weighted bootstrap contracts: 10/10 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
