#!/usr/bin/env python3
"""Create C14F figures and LaTeX tables from locked C14C/C14E results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COLORS = {
    "blue": "#1f5a99",
    "orange": "#d97706",
    "green": "#2a7f62",
    "red": "#b33b3b",
    "purple": "#6f4c9b",
    "gray": "#5f6b73",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def esc(value: object) -> str:
    return str(value).replace("_", r"\_\allowbreak{}").replace("/", r"/\allowbreak{}").replace("%", r"\%")


def pp(value: float, digits: int = 2) -> str:
    return f"{100 * value:+.{digits}f}"


def interval(row: pd.Series, familywise: bool = True) -> str:
    prefix = "familywise_bonferroni" if familywise else "pointwise_ci95"
    return f"[{pp(float(row[prefix + '_low']))}, {pp(float(row[prefix + '_high']))}]"


def short_outcome(value: str) -> str:
    return {
        "future_fail_or_withdrawn": "Fail/withdraw",
        "withdrawal_or_fail": "Fail/withdraw",
        "dropout_vs_graduate": "Dropout vs graduate",
        "dropout_vs_all_other": "Dropout vs all other",
        "fail_g3_lt_10": r"$G3<10$",
    }.get(value, value)


def context_label(dataset: str, subject: str = "all") -> str:
    if dataset == "oulad":
        return "OULAD"
    if dataset == "uci697":
        return "UCI 697"
    if dataset == "uci320":
        return "UCI 320 Math." if subject == "mathematics" else "UCI 320 Port."
    return dataset


def short_contrast(value: str) -> str:
    return {
        "minimized": "minimized",
        "partial_gender_disability": "gender/disability",
        "no_demographic_family": "no demographic/family",
        "no_sensitive_wellbeing": "no sensitive/wellbeing",
        "school_observable_only": "school observable",
        "targeted_no_sex": "no sex",
        "legacy_operational": "legacy operational",
        "no_direct_personal": "no direct personal",
        "no_family_financial": "no family/financial",
        "targeted_gender_special_needs": "no gender/special needs",
        "sex_gender": "sex/gender",
        "socioeconomic_family": "socioeconomic/family",
    }.get(value, value.replace("_", " "))


def short_stage(value: str) -> str:
    return {"enrollment": "enroll.", "semester1": "semester 1"}.get(value, value)


def make_tables(stats: pd.DataFrame, families: pd.DataFrame, proxy: pd.DataFrame, output: Path) -> None:
    precision = stats[(stats["tier"] == "primary") & (stats["metric"] == "precision_difference")]
    budget = precision[
        (precision["analysis_source"] == "C14B_frozen")
        & (
            ((precision["dataset"] == "oulad") & (precision["contrast_name"] == "minimized"))
            | ((precision["dataset"] == "uci697") & (precision["contrast_name"] == "legacy_operational"))
        )
    ]
    lines = []
    for keys, frame in budget.groupby(["dataset", "subject", "outcome", "stage"], sort=False):
        dataset, subject, outcome, stage = keys
        if dataset == "oulad":
            label = f"OULAD {stage}, minimized"
        else:
            label = f"UCI 697 {stage}, legacy"
        cells = []
        for b in [0.05, 0.10, 0.20, 0.30]:
            row = frame[np.isclose(frame["budget_fraction"], b)].iloc[0]
            marker = r"$^{*}$" if bool(row["familywise_excludes_zero"]) else ""
            cells.append(pp(float(row["estimate"])) + marker)
        lines.append(esc(label) + " & " + " & ".join(cells) + r" \\")
    atomic_text(output / "tables/main_c14_budget.tex", "\n".join(lines) + "\n\\bottomrule\n")

    harmonized = families[families["analysis_source"] == "C14D_harmonized"].copy()
    lines = []
    for row in harmonized.itertuples(index=False):
        context = context_label(str(row.dataset), str(row.subject))
        if row.dataset == "uci697":
            context += "/" + short_outcome(str(row.outcome))
        lines.append(
            f"{esc(context)} & {esc(short_contrast(str(row.contrast_name)))} & {row.cells} & "
            f"[{pp(row.minimum_estimate)}, {pp(row.maximum_estimate)}] & "
            f"{row.familywise_negative_cells} & {row.familywise_positive_cells} \\\\"
        )
    atomic_text(output / "tables/main_c14_harmonized.tex", "\n".join(lines) + "\n\\bottomrule\n")

    ranges = proxy.groupby(["dataset", "subject", "target_field"], sort=False).agg(
        stages=("stage", "nunique"),
        positives_min=("positive_cases", "min"),
        positives_max=("positive_cases", "max"),
        prevalence_min=("prevalence", "min"),
        prevalence_max=("prevalence", "max"),
        auroc_min=("auroc", "min"),
        auroc_max=("auroc", "max"),
        lift_min=("ap_lift_over_prevalence", "min"),
        lift_max=("ap_lift_over_prevalence", "max"),
    ).reset_index()
    lines = []
    for row in ranges.itertuples(index=False):
        context = context_label(str(row.dataset), str(row.subject))
        positives = str(row.positives_min) if row.positives_min == row.positives_max else f"{row.positives_min}--{row.positives_max}"
        lines.append(
            f"{esc(context)} & {esc(row.target_field)} & {row.stages} & {positives} & "
            f"{row.auroc_min:.3f}--{row.auroc_max:.3f} & {row.lift_min:.2f}--{row.lift_max:.2f} \\\\"
        )
    atomic_text(output / "tables/main_c14_proxy.tex", "\n".join(lines) + "\n\\bottomrule\n")

    lines = []
    for row in families.itertuples(index=False):
        context = context_label(str(row.dataset), str(row.subject))
        lines.append(
            f"{esc('C14B' if row.analysis_source == 'C14B_frozen' else 'C14D')} & {esc(context)} & {esc(short_outcome(str(row.outcome)))} & "
            f"{esc(short_contrast(str(row.contrast_name)))} & {row.cells} & [{pp(row.minimum_estimate)}, {pp(row.maximum_estimate)}] & "
            f"{row.familywise_negative_cells} & {row.familywise_positive_cells} \\\\"
        )
    atomic_text(output / "tables/supp_c14_primary_families.tex", "\n".join(lines) + "\n\\bottomrule\n")

    h10 = precision[(precision["analysis_source"] == "C14D_harmonized") & np.isclose(precision["budget_fraction"], 0.10)]
    lines = []
    for row in h10.itertuples(index=False):
        context = context_label(str(row.dataset), str(row.subject))
        flag = "Yes" if row.familywise_excludes_zero else "No"
        lines.append(
            f"{esc(context)} & {esc(short_outcome(str(row.outcome)))} & {esc(short_stage(str(row.stage)))} & {esc(short_contrast(str(row.contrast_name)))} & "
            f"{pp(row.estimate)} & [{pp(row.pointwise_ci95_low)}, {pp(row.pointwise_ci95_high)}] & "
            f"[{pp(row.familywise_bonferroni_low)}, {pp(row.familywise_bonferroni_high)}] & {flag} \\\\"
        )
    atomic_text(output / "tables/supp_c14_harmonized_at10.tex", "\n".join(lines) + "\n\\bottomrule\n")

    lines = []
    for row in proxy.itertuples(index=False):
        context = context_label(str(row.dataset), str(row.subject))
        lines.append(
            f"{esc(context)} & {esc(short_stage(str(row.stage)))} & {esc(row.target_field)} & {row.n} & {row.positive_cases} & "
            f"{row.prevalence:.3f} & {row.auroc:.3f} & {row.average_precision:.3f} & "
            f"{row.ap_lift_over_prevalence:.2f} & {row.balanced_accuracy:.3f} \\\\"
        )
    atomic_text(output / "tables/supp_c14_proxy_full.tex", "\n".join(lines) + "\n\\bottomrule\n")


def make_budget_figure(stats: pd.DataFrame, output: Path) -> None:
    data = stats[
        (stats["analysis_source"] == "C14D_harmonized")
        & (stats["tier"] == "primary")
        & (stats["metric"] == "precision_difference")
        & (stats["contrast_name"] == "socioeconomic_family")
    ].copy()
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.3), constrained_layout=True)
    oulad = data[data["dataset"] == "oulad"]
    for index, (stage, frame) in enumerate(oulad.groupby("stage", sort=False)):
        frame = frame.sort_values("budget_fraction")
        axes[0].plot(100 * frame["budget_fraction"], 100 * frame["estimate"], marker="o", linewidth=1.6, label=stage)
        sig = frame[frame["familywise_excludes_zero"]]
        axes[0].scatter(100 * sig["budget_fraction"], 100 * sig["estimate"], s=70, facecolors="none", edgecolors="black", linewidths=1.2)
    axes[0].axhline(0, color="#333333", linewidth=0.9)
    axes[0].set_title("A. OULAD socioeconomic-family exclusion")
    axes[0].set_xlabel("Review budget (%)")
    axes[0].set_ylabel("Precision difference (percentage points)")
    axes[0].set_xticks([5, 10, 20, 30])
    axes[0].legend(ncol=2, fontsize=8, frameon=False)

    uci = data[data["dataset"] == "uci697"]
    style = [COLORS["blue"], COLORS["orange"], COLORS["green"], COLORS["purple"]]
    for color, (key, frame) in zip(style, uci.groupby(["outcome", "stage"], sort=False)):
        outcome, stage = key
        frame = frame.sort_values("budget_fraction")
        label = ("terminal" if outcome == "dropout_vs_graduate" else "all-other") + f"/{stage}"
        axes[1].plot(100 * frame["budget_fraction"], 100 * frame["estimate"], marker="o", linewidth=1.8, color=color, label=label)
        sig = frame[frame["familywise_excludes_zero"]]
        axes[1].scatter(100 * sig["budget_fraction"], 100 * sig["estimate"], s=70, facecolors="none", edgecolors="black", linewidths=1.2)
    axes[1].axhline(0, color="#333333", linewidth=0.9)
    axes[1].set_title("B. UCI 697 socioeconomic-family exclusion")
    axes[1].set_xlabel("Review budget (%)")
    axes[1].set_xticks([5, 10, 20, 30])
    axes[1].legend(fontsize=8, frameon=False)
    for ax in axes:
        ax.grid(axis="y", color="#d9dde2", linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(output / "figures/fig3_c14_budget_harmonized.png", dpi=220)
    fig.savefig(output / "figures/fig3_c14_budget_harmonized.pdf")
    plt.close(fig)


def make_proxy_figure(proxy: pd.DataFrame, output: Path) -> None:
    ranges = proxy.groupby(["dataset", "subject", "target_field"], sort=False).agg(
        low=("auroc", "min"), high=("auroc", "max"), middle=("auroc", "mean")
    ).reset_index()
    labels = []
    for row in ranges.itertuples(index=False):
        context = row.dataset.upper()
        if row.dataset == "uci320":
            context += f" {row.subject[:4]}."
        labels.append(f"{context}: {row.target_field}")
    y = np.arange(len(ranges))[::-1]
    fig, ax = plt.subplots(figsize=(8.4, 4.2), constrained_layout=True)
    low = ranges["low"].to_numpy(); high = ranges["high"].to_numpy(); middle = ranges["middle"].to_numpy()
    ax.hlines(y, low, high, color=COLORS["blue"], linewidth=3)
    ax.scatter(middle, y, color=COLORS["orange"], s=45, zorder=3)
    ax.axvline(0.5, color="#333333", linestyle="--", linewidth=1)
    ax.set_yticks(y, labels)
    ax.set_xlim(0.48, 0.84)
    ax.set_xlabel("Held-out AUROC (range across frozen stages)")
    ax.set_title("Fixed logistic probes after direct field exclusion")
    ax.grid(axis="x", color="#d9dde2", linewidth=0.6)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.savefig(output / "figures/fig4_c14_proxy_persistence.png", dpi=220)
    fig.savefig(output / "figures/fig4_c14_proxy_persistence.pdf")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c14c", type=Path, required=True)
    parser.add_argument("--c14e", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stats_path = args.c14e / "paired_statistics.csv.gz"
    family_path = args.c14e / "primary_family_summary.csv"
    proxy_path = args.c14c / "proxy_primary_metrics.csv"
    stats = pd.read_csv(stats_path, low_memory=False)
    families = pd.read_csv(family_path)
    proxy = pd.read_csv(proxy_path)
    make_tables(stats, families, proxy, args.output)
    make_budget_figure(stats, args.output)
    make_proxy_figure(proxy, args.output)
    provenance = {
        "phase": "C14F",
        "status": "ASSETS_FROM_LOCKED_C14C_C14E_ONLY",
        "inputs": {
            "paired_statistics.csv.gz": sha256(stats_path),
            "primary_family_summary.csv": sha256(family_path),
            "proxy_primary_metrics.csv": sha256(proxy_path),
        },
        "outputs": {
            path.relative_to(args.output).as_posix(): sha256(path)
            for path in sorted((args.output / "figures").glob("fig[34]_c14_*"))
        },
    }
    atomic_text(args.output / "figures/C14F_FIGURE_PROVENANCE.json", json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(json.dumps(provenance, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
