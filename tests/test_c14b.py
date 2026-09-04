#!/usr/bin/env python3
"""Unit tests for C14B deterministic budget calculations."""

import numpy as np

from c14b_budget_sensitivity import overlap_metrics, queue_metrics, select_at_budget, uci_tie_key


def test_groupwise_ceil_and_tie_order() -> None:
    probabilities = np.asarray([0.9, 0.8, 0.7, 0.9, 0.8])
    groups = np.asarray(["a", "a", "a", "b", "b"])
    keys = np.asarray(["b", "a", "c", "b", "a"])
    selected = select_at_budget(probabilities, groups, keys, 0.30)
    assert selected.tolist() == [True, False, False, True, False]


def test_exact_tie_uses_ascending_key() -> None:
    probabilities = np.asarray([0.5, 0.5, 0.5])
    groups = np.asarray(["a", "a", "a"])
    keys = np.asarray(["c", "a", "b"])
    selected = select_at_budget(probabilities, groups, keys, 0.34)
    assert selected.tolist() == [False, True, True]


def test_queue_and_overlap() -> None:
    y = np.asarray([1, 0, 1, 0])
    restricted = np.asarray([True, True, False, False])
    full = np.asarray([True, False, True, False])
    queue = queue_metrics(y, restricted)
    overlap = overlap_metrics(restricted, full)
    assert queue["alerts"] == 2
    assert queue["true_alerts"] == 1
    assert queue["precision"] == 0.5
    assert overlap["alert_intersection"] == 1
    assert overlap["alert_jaccard_vs_full"] == 1 / 3


def test_uci_tie_key_stable() -> None:
    assert uci_tie_key("uci697", 12, 20260830) == uci_tie_key("uci697", 12, 20260830)
    assert uci_tie_key("uci697", 12, 20260830) != uci_tie_key("uci697", 13, 20260830)


def main() -> int:
    test_groupwise_ceil_and_tie_order()
    test_exact_tie_uses_ascending_key()
    test_queue_and_overlap()
    test_uci_tie_key_stable()
    print("C14B unit contracts: 4/4 PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
