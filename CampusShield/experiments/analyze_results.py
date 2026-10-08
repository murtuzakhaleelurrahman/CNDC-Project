#!/usr/bin/env python3
"""Summarize completed CampusShield core experiments without altering data."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results"


def _latest(pattern: str) -> Path:
    matches = sorted(RESULTS_ROOT.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No result file matches {pattern}")
    return matches[-1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--congestion-csv",
        type=Path,
        default=None,
        help="paired congestion CSV (default: latest comparison)",
    )
    parser.add_argument(
        "--failure-csv",
        type=Path,
        default=None,
        help="failure-recovery CSV (default: latest result)",
    )
    return parser.parse_args()


def _mean_std(frame: pd.DataFrame, scenario: str, metric: str) -> tuple[float, float]:
    values = frame.loc[frame["scenario"] == scenario, metric]
    return float(values.mean()), float(values.std(ddof=1))


def main() -> int:
    args = parse_args()
    congestion_path = args.congestion_csv or _latest("congestion_comparison_*.csv")
    failure_path = args.failure_csv or _latest("failure_recovery_*.csv")
    congestion = pd.read_csv(congestion_path)
    failure = pd.read_csv(failure_path)

    off_repetitions = set(
        congestion.loc[congestion["scenario"] == "ANRE_OFF", "repetition"]
    )
    on_repetitions = set(
        congestion.loc[congestion["scenario"] == "ANRE_ON", "repetition"]
    )
    if off_repetitions != on_repetitions or len(off_repetitions) < 3:
        raise ValueError("Congestion input must contain at least three complete OFF/ON pairs")
    if len(failure) < 3:
        raise ValueError("Failure input must contain at least three repetitions")

    metric_definitions = (
        ("emergency_throughput_mbps", "Emergency throughput", "Mbps"),
        ("emergency_udp_loss_percent", "Emergency UDP loss", "percent"),
        ("emergency_udp_jitter_ms", "Emergency UDP jitter", "ms"),
        ("mean_rtt_ms", "Probe RTT", "ms"),
        ("mean_nhs", "Network Health Score", "score"),
        ("bulk_throughput_mbps", "Bulk throughput", "Mbps"),
        ("academic_throughput_mbps", "Academic throughput", "Mbps"),
    )
    rows: list[dict[str, object]] = []
    comparison: dict[str, dict[str, float]] = {}
    for metric, label, unit in metric_definitions:
        off_mean, off_std = _mean_std(congestion, "ANRE_OFF", metric)
        on_mean, on_std = _mean_std(congestion, "ANRE_ON", metric)
        delta = on_mean - off_mean
        percent_change = (delta / off_mean) * 100 if off_mean else float("nan")
        comparison[metric] = {
            "off_mean": off_mean,
            "off_std": off_std,
            "on_mean": on_mean,
            "on_std": on_std,
            "delta": delta,
            "percent_change": percent_change,
        }
        rows.append(
            {
                "experiment": "ANRE_OFF_VS_ON",
                "metric": metric,
                "label": label,
                "unit": unit,
                "off_mean": off_mean,
                "off_std": off_std,
                "on_mean": on_mean,
                "on_std": on_std,
                "delta_on_minus_off": delta,
                "percent_change": percent_change,
            }
        )

    failure_metrics = (
        ("packets_lost_during_convergence", "Packets lost", "packets"),
        ("service_interruption_ms", "Service interruption", "ms"),
        ("route_convergence_ms", "Backup route convergence", "ms"),
        ("primary_restoration_ms", "Primary route restoration", "ms"),
    )
    failure_summary: dict[str, dict[str, float]] = {}
    for metric, label, unit in failure_metrics:
        values = failure[metric]
        failure_summary[metric] = {
            "mean": float(values.mean()),
            "std": float(values.std(ddof=1)),
            "minimum": float(values.min()),
            "maximum": float(values.max()),
        }
        rows.append(
            {
                "experiment": "LINK_FAILURE",
                "metric": metric,
                "label": label,
                "unit": unit,
                "mean": values.mean(),
                "std": values.std(ddof=1),
                "minimum": values.min(),
                "maximum": values.max(),
            }
        )

    response = congestion.loc[
        congestion["scenario"] == "ANRE_ON", "controller_response_seconds"
    ]
    rows.append(
        {
            "experiment": "ANRE_OFF_VS_ON",
            "metric": "controller_response_seconds",
            "label": "ANRE response time",
            "unit": "seconds",
            "on_mean": response.mean(),
            "on_std": response.std(ddof=1),
            "minimum": response.min(),
            "maximum": response.max(),
        }
    )

    summary_csv = RESULTS_ROOT / "core_experiment_summary.csv"
    analysis_md = RESULTS_ROOT / "core_experiment_analysis.md"
    graph_path = RESULTS_ROOT / "core_experiment_summary.png"
    pd.DataFrame(rows).to_csv(summary_csv, index=False)

    hypotheses = [
        (
            "H1 - RTT",
            comparison["mean_rtt_ms"]["on_mean"]
            < comparison["mean_rtt_ms"]["off_mean"],
            "Mean probe RTT with ANRE is lower than without ANRE.",
        ),
        (
            "H2 - Packet loss",
            comparison["emergency_udp_loss_percent"]["on_mean"]
            < comparison["emergency_udp_loss_percent"]["off_mean"],
            "Emergency UDP loss with ANRE is lower than without ANRE.",
        ),
        (
            "H3 - Jitter",
            comparison["emergency_udp_jitter_ms"]["on_mean"]
            < comparison["emergency_udp_jitter_ms"]["off_mean"],
            "Emergency UDP jitter with ANRE is lower than without ANRE.",
        ),
        (
            "H4 - Network recovery",
            comparison["mean_nhs"]["on_mean"] > comparison["mean_nhs"]["off_mean"],
            "Mean NHS with ANRE is higher than without ANRE.",
        ),
        (
            "H5 - Bulk trade-off",
            comparison["bulk_throughput_mbps"]["on_mean"]
            < comparison["bulk_throughput_mbps"]["off_mean"]
            and comparison["emergency_throughput_mbps"]["on_mean"]
            > comparison["emergency_throughput_mbps"]["off_mean"],
            "ANRE reduces bulk throughput while increasing emergency throughput.",
        ),
        (
            "H6 - Routing recovery",
            len(failure) >= 3
            and failure["route_after_failure"].str.contains("10.10.255.6").all()
            and failure["route_after_restoration"].str.contains("10.10.255.2").all(),
            "Every repetition used the backup route and restored the primary route.",
        ),
    ]

    lines = [
        "# CampusShield Core Experimental Analysis",
        "",
        f"Congestion source: `{congestion_path.name}`",
        f"Failure source: `{failure_path.name}`",
        "",
        "This analysis uses three paired ANRE OFF/ON repetitions and three "
        "physical-link-failure repetitions. Values are descriptive means and "
        "sample standard deviations; n=3 is too small for strong inferential claims.",
        "",
        "## Congestion comparison",
        "",
        "| Metric | ANRE OFF mean +/- SD | ANRE ON mean +/- SD | Change |",
        "|---|---:|---:|---:|",
    ]
    for metric, label, unit in metric_definitions:
        item = comparison[metric]
        lines.append(
            f"| {label} | {item['off_mean']:.3f} +/- {item['off_std']:.3f} {unit} "
            f"| {item['on_mean']:.3f} +/- {item['on_std']:.3f} {unit} "
            f"| {item['percent_change']:+.2f}% |"
        )
    lines.extend(
        [
            "",
            f"Mean ANRE response time: {response.mean():.3f} +/- "
            f"{response.std(ddof=1):.3f} seconds.",
            "",
            "## Physical link failure",
            "",
            "| Metric | Mean +/- SD | Range |",
            "|---|---:|---:|",
        ]
    )
    for metric, label, unit in failure_metrics:
        item = failure_summary[metric]
        lines.append(
            f"| {label} | {item['mean']:.3f} +/- {item['std']:.3f} {unit} "
            f"| {item['minimum']:.3f} to {item['maximum']:.3f} {unit} |"
        )
    lines.extend(
        [
            "",
            "## Hypothesis evaluation",
            "",
            "| Hypothesis | Outcome | Evidence rule |",
            "|---|---|---|",
        ]
    )
    for name, supported, evidence in hypotheses:
        lines.append(
            f"| {name} | {'Supported' if supported else 'Not supported'} | {evidence} |"
        )
    lines.extend(
        [
            "| H7 - Tuned OSPF | Not tested | This remains a secondary experiment. |",
            "",
            "## Interpretation",
            "",
            "ANRE produced the intended service trade-off: it increased emergency "
            "throughput and reduced emergency packet loss by restricting bulk traffic. "
            "The repeated measurements did not show lower mean RTT, lower mean jitter, "
            "or a higher mean NHS, so those hypotheses are not supported by this dataset. "
            "All physical-failure repetitions automatically converged to R1-R3-R2 and "
            "later restored the direct R1-R2 route, supporting the routing-recovery claim.",
            "",
        ]
    )
    analysis_md.write_text("\n".join(lines), encoding="utf-8")

    off = congestion[congestion["scenario"] == "ANRE_OFF"].sort_values("repetition")
    on = congestion[congestion["scenario"] == "ANRE_ON"].sort_values("repetition")
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    figure.suptitle("CampusShield Core Experimental Summary")
    paired = (
        (axes[0, 0], "emergency_throughput_mbps", "Emergency throughput", "Mbps"),
        (axes[0, 1], "emergency_udp_loss_percent", "Emergency UDP loss", "Percent"),
    )
    for axis, metric, title, unit in paired:
        for repetition, off_value, on_value in zip(
            off["repetition"], off[metric], on[metric]
        ):
            axis.plot(["ANRE OFF", "ANRE ON"], [off_value, on_value], marker="o", label=f"Rep {repetition}")
        axis.set(title=title, ylabel=unit)
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
    axes[1, 0].bar(
        failure["repetition"].astype(str), failure["service_interruption_ms"],
        color="#0f766e",
    )
    axes[1, 0].set(
        title="Failure service interruption", xlabel="Repetition", ylabel="Milliseconds"
    )
    axes[1, 1].bar(
        failure["repetition"].astype(str),
        failure["packets_lost_during_convergence"],
        color="#b45309",
    )
    axes[1, 1].set(
        title="Packets lost during convergence", xlabel="Repetition", ylabel="Packets"
    )
    for axis in axes[1]:
        axis.grid(axis="y", alpha=0.25)
    figure.savefig(graph_path, dpi=160)
    plt.close(figure)

    print(f"Congestion group: {congestion['group_id'].iloc[0]}")
    print(f"Failure group: {failure['group_id'].iloc[0]}")
    for name, supported, _ in hypotheses:
        print(f"{'SUPPORTED' if supported else 'NOT SUPPORTED'}: {name}")
    print("NOT TESTED: H7 - Tuned OSPF")
    print(f"Summary CSV: {summary_csv}")
    print(f"Analysis: {analysis_md}")
    print(f"Graph: {graph_path}")
    print("CORE EXPERIMENT ANALYSIS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
