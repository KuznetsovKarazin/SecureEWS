#!/usr/bin/env python3
"""Unit tests for C14C proxy utilities."""

import numpy as np

from c14c_proxy_persistence import metrics, select_threshold


def test_threshold_is_finite_and_data_supported() -> None:
    y = np.asarray([0, 0, 1, 1])
    p = np.asarray([0.1, 0.2, 0.8, 0.9])
    threshold = select_threshold(y, p)
    assert np.isfinite(threshold)
    assert threshold in p


def test_metrics_perfect() -> None:
    y = np.asarray([0, 0, 1, 1])
    p = np.asarray([0.1, 0.2, 0.8, 0.9])
    predicted = (p >= 0.5).astype(int)
    result = metrics(y, p, predicted)
    assert result["auroc"] == 1.0
    assert result["average_precision"] == 1.0
    assert result["balanced_accuracy"] == 1.0


def main() -> int:
    test_threshold_is_finite_and_data_supported()
    test_metrics_perfect()
    print("C14C unit contracts: 2/2 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
