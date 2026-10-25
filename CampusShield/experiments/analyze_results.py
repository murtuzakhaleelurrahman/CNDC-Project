#!/usr/bin/env python3
"""Summarize completed CampusShield core experiments without altering data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results"
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.congestion_design import SCENARIOS  # noqa: E402
from experiments.statistics_utils import (  # noqa: E402
    DescriptiveStatistics,
    describe_95,
)


SCENARIO_LABELS = {
    "ANRE_OFF": "Basic static",
    "STATIC_TUNED": "Tuned static",
    "ANRE_ON": "Adaptive ANRE",
}


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
        help="three-arm congestion CSV (default: latest comparison)",
    )
    parser.add_argument(
        "--failure-csv",
        type=Path,
        default=None,
        help="failure-recovery CSV (default: latest result)",
    )
    parser.add_argument(
        "--minimum-repetitions",
        type=int,
        default=10,
        help="minimum complete repetitions required for formal analysis (default: 10)",
    )
    return parser.parse_args()


def _scenario_stats(
    frame: pd.DataFrame, scenario: str, metric: str
) -> DescriptiveStatistics:
    values = frame.loc[frame["scenario"] == scenario, metric].dropna().tolist()
    return describe_95(values)


def _format_estimate(item: DescriptiveStatistics, unit: str) -> str:
    return (
        f"{item.mean:.3f} +/- {item.standard_deviation:.3f} {unit} "
        f"[95% CI {item.ci95_low:.3f} to {item.ci95_high:.3f}]"
    )


def _validate_repetitions(
    congestion: pd.DataFrame, minimum_repetitions: int
) -> tuple[str, ...]:
    available = tuple(
        scenario
        for scenario in SCENARIOS
        if scenario in set(congestion["scenario"].astype(str))
    )
    required = (
        SCENARIOS
        if "STATIC_TUNED" in available
        else ("ANRE_OFF", "ANRE_ON")
    )
    repetition_sets = {
        scenario: set(
            congestion.loc[congestion["scenario"] == scenario, "repetition"]
        )
        for scenario in required
    }
    common = set.intersection(*repetition_sets.values()) if repetition_sets else set()
    if any(values != common for values in repetition_sets.values()):
        raise ValueError("Congestion input has incomplete matched scenario repetitions")
    if len(common) < minimum_repetitions:
        raise ValueError(
            f"Congestion input has {len(common)} complete repetition(s); "
            f"at least {minimum_repetitions} are required"
        )
    return required


def main() -> int:
    args = parse_args()
    if args.minimum_repetitions < 2:
        raise ValueError("Minimum repetitions must be at least 2 for confidence intervals")
    congestion_path = args.congestion_csv or _latest("congestion_comparison_*.csv")
    failure_path = args.failure_csv or _latest("failure_recovery_*.csv")
    congestion = pd.read_csv(congestion_path)
    failure = pd.read_csv(failure_path)

    scenarios = _validate_repetitions(congestion, args.minimum_repetitions)
    if len(failure) < args.minimum_repetitions:
        raise ValueError(
            f"Failure input has {len(failure)} repetition(s); at least "
            f"{args.minimum_repetitions} are required"
        )

    metric_definitions = [
        ("emergency_throughput_mbps", "Emergency throughput", "Mbps"),
        ("emergency_udp_loss_percent", "Emergency UDP loss", "percent"),
        ("emergency_udp_jitter_ms", "Emergency UDP jitter", "ms"),
        ("mean_rtt_ms", "EF probe RTT", "ms"),
        ("mean_nhs", "Congestion NHS", "score"),
        ("bulk_throughput_mbps", "Bulk throughput", "Mbps"),
        ("academic_throughput_mbps", "Academic throughput", "Mbps"),
    ]
    optional_metrics = [
        ("recovery_mean_nhs", "Recovery NHS", "score"),
        ("recovery_nhs_change", "NHS recovery change", "score"),
        ("emergency_queue_drops_congestion", "Emergency queue drops", "packets"),
        ("peak_emergency_backlog_bytes", "Peak emergency backlog", "bytes"),
    ]
    metric_definitions.extend(
        item for item in optional_metrics if item[0] in congestion.columns
    )

    rows: list[dict[str, object]] = []
    statistics: dict[str, dict[str, DescriptiveStatistics]] = {}
    for metric, label, unit in metric_definitions:
        statistics[metric] = {}
        for scenario in scenarios:
            item = _scenario_stats(congestion, scenario, metric)
            statistics[metric][scenario] = item
            rows.append(
                {
                    "experiment": "THREE_ARM_CONGESTION",
                    "scenario": scenario,
                    "metric": metric,
                    "label": label,
                    "unit": unit,
                    "n": item.count,
                    "mean": item.mean,
                    "std": item.standard_deviation,
                    "ci95_low": item.ci95_low,
                    "ci95_high": item.ci95_high,
                    "minimum": item.minimum,
                    "maximum": item.maximum,
                }
            )

    comparisons: dict[str, dict[str, float]] = {}
    for metric, _, _ in metric_definitions:
        basic = statistics[metric]["ANRE_OFF"].mean
        adaptive = statistics[metric]["ANRE_ON"].mean
        comparisons[metric] = {
            "adaptive_minus_basic": adaptive - basic,
            "adaptive_vs_basic_percent": (
                ((adaptive - basic) / basic) * 100 if basic else float("nan")
            ),
        }
        if "STATIC_TUNED" in scenarios:
            tuned = statistics[metric]["STATIC_TUNED"].mean
            comparisons[metric].update(
                {
                    "adaptive_minus_tuned": adaptive - tuned,
                    "adaptive_vs_tuned_percent": (
                        ((adaptive - tuned) / tuned) * 100
                        if tuned
                        else float("nan")
                    ),
                }
            )

    failure_metrics = (
        ("packets_lost_during_convergence", "Packets lost", "packets"),
        ("service_interruption_ms", "Service interruption", "ms"),
        ("route_convergence_ms", "Backup route convergence", "ms"),
        ("primary_restoration_ms", "Primary route restoration", "ms"),
    )
    failure_statistics: dict[str, DescriptiveStatistics] = {}
    for metric, label, unit in failure_metrics:
        item = describe_95(failure[metric].dropna().tolist())
        failure_statistics[metric] = item
        rows.append(
            {
                "experiment": "LINK_FAILURE",
                "scenario": "FAILURE_RECOVERY",
                "metric": metric,
                "label": label,
                "unit": unit,
                "n": item.count,
                "mean": item.mean,
                "std": item.standard_deviation,
                "ci95_low": item.ci95_low,
                "ci95_high": item.ci95_high,
                "minimum": item.minimum,
                "maximum": item.maximum,
            }
        )

    controller_timings = (
        ("controller_response_seconds", "ANRE response time"),
        ("recovery_to_normal_seconds", "ANRE recovery-to-NORMAL time"),
    )
    for metric, label in controller_timings:
        if metric not in congestion.columns:
            continue
        values = congestion.loc[
            congestion["scenario"] == "ANRE_ON", metric
        ].dropna()
        if values.empty:
            continue
        item = describe_95(values.tolist())
        rows.append(
            {
                "experiment": "THREE_ARM_CONGESTION",
                "scenario": "ANRE_ON",
                "metric": metric,
                "label": label,
                "unit": "seconds",
                "n": item.count,
                "mean": item.mean,
                "std": item.standard_deviation,
                "ci95_low": item.ci95_low,
                "ci95_high": item.ci95_high,
                "minimum": item.minimum,
                "maximum": item.maximum,
            }
        )

    summary_csv = RESULTS_ROOT / "core_experiment_summary.csv"
    analysis_md = RESULTS_ROOT / "core_experiment_analysis.md"
    graph_path = RESULTS_ROOT / "core_experiment_summary.png"
    pd.DataFrame(rows).to_csv(summary_csv, index=False)

    hypotheses = [
        (
            "H1 - RTT",
            statistics["mean_rtt_ms"]["ANRE_ON"].mean
            < statistics["mean_rtt_ms"]["ANRE_OFF"].mean,
            "Mean EF-marked probe RTT with ANRE is lower than basic static QoS.",
        ),
        (
            "H2 - Packet loss",
            statistics["emergency_udp_loss_percent"]["ANRE_ON"].mean
            < statistics["emergency_udp_loss_percent"]["ANRE_OFF"].mean,
            "Emergency UDP loss with ANRE is lower than basic static QoS.",
        ),
        (
            "H3 - Jitter",
            statistics["emergency_udp_jitter_ms"]["ANRE_ON"].mean
            < statistics["emergency_udp_jitter_ms"]["ANRE_OFF"].mean,
            "Emergency UDP jitter with ANRE is lower than basic static QoS.",
        ),
        (
            "H4 - Network recovery",
            "recovery_nhs_change" in statistics
            and statistics["recovery_nhs_change"]["ANRE_ON"].mean > 0,
            "ANRE mean NHS increases from congestion to the recovery phase.",
        ),
        (
            "H5 - Bulk trade-off",
            statistics["bulk_throughput_mbps"]["ANRE_ON"].mean
            < statistics["bulk_throughput_mbps"]["ANRE_OFF"].mean
            and statistics["emergency_throughput_mbps"]["ANRE_ON"].mean
            > statistics["emergency_throughput_mbps"]["ANRE_OFF"].mean,
            "ANRE increases emergency throughput while restricting bulk traffic.",
        ),
        (
            "H6 - Routing recovery",
            len(failure) >= 3
            and failure["route_after_failure"].str.contains("10.10.255.6").all()
            and failure["route_after_restoration"].str.contains("10.10.255.2").all(),
            "Every failure repetition uses the backup route and restores the primary.",
        ),
    ]

    lines = [
        "# CampusShield Core Experimental Analysis",
        "",
        f"Congestion source: `{congestion_path.name}`",
        f"Failure source: `{failure_path.name}`",
        "",
        f"The congestion analysis uses {len(set(congestion['repetition']))} matched "
        f"repetitions across {len(scenarios)} scenario(s). Values report sample "
        "standard deviation and two-sided 95% Student-t confidence intervals.",
        "",
        "## Congestion comparison",
        "",
        "| Metric | "
        + " | ".join(SCENARIO_LABELS[item] for item in scenarios)
        + " |",
        "|---|" + "---:|" * len(scenarios),
    ]
    for metric, label, unit in metric_definitions:
        lines.append(
            f"| {label} | "
            + " | ".join(
                _format_estimate(statistics[metric][scenario], unit)
                for scenario in scenarios
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Adaptive comparisons",
            "",
            "| Metric | ANRE vs basic static | ANRE vs tuned static |",
            "|---|---:|---:|",
        ]
    )
    for metric, label, _ in metric_definitions:
        item = comparisons[metric]
        tuned_text = (
            f"{item['adaptive_vs_tuned_percent']:+.2f}%"
            if "adaptive_vs_tuned_percent" in item
            else "Not available"
        )
        lines.append(
            f"| {label} | {item['adaptive_vs_basic_percent']:+.2f}% | "
            f"{tuned_text} |"
        )

    lines.extend(
        [
            "",
            "## Physical link failure",
            "",
            "| Metric | Mean, SD and 95% CI | Range |",
            "|---|---:|---:|",
        ]
    )
    for metric, label, unit in failure_metrics:
        item = failure_statistics[metric]
        lines.append(
            f"| {label} | {_format_estimate(item, unit)} | "
            f"{item.minimum:.3f} to {item.maximum:.3f} {unit} |"
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
            "| H7 - Tuned OSPF | Not tested | This remains a Phase 3 routing experiment. |",
            "",
            "## Interpretation",
            "",
            "The three-arm design compares ANRE with both the original basic static "
            "allocation and a stronger fixed emergency-priority allocation. The "
            "healthy, congestion, and recovery phases also expose controller response "
            "and recovery behavior instead of measuring only a constant overload. "
            "Hypotheses are reported directly from the measured directions above; "
            "confidence intervals show the uncertainty between repetitions.",
            "",
        ]
    )
    analysis_md.write_text("\n".join(lines), encoding="utf-8")

    figure, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    figure.suptitle("CampusShield Phase 2 Experimental Summary")
    scenario_positions = [SCENARIO_LABELS[item] for item in scenarios]
    paired = (
        (axes[0, 0], "emergency_throughput_mbps", "Emergency throughput", "Mbps"),
        (axes[0, 1], "emergency_udp_loss_percent", "Emergency UDP loss", "Percent"),
    )
    pivot = pd.DataFrame()
    for axis, metric, title, unit in paired:
        pivot = congestion.pivot(
            index="repetition", columns="scenario", values=metric
        )
        for repetition, values in pivot.iterrows():
            axis.plot(
                scenario_positions,
                [values[scenario] for scenario in scenarios],
                marker="o",
                alpha=0.7,
                label=f"Rep {repetition}",
            )
        axis.set(title=title, ylabel=unit)
        axis.grid(axis="y", alpha=0.25)
    if len(pivot) <= 10:
        axes[0, 1].legend(ncol=2, fontsize=8)

    axes[1, 0].bar(
        failure["repetition"].astype(str),
        failure["service_interruption_ms"],
        color="#0f766e",
    )
    axes[1, 0].set(
        title="Failure service interruption",
        xlabel="Repetition",
        ylabel="Milliseconds",
    )
    axes[1, 1].bar(
        failure["repetition"].astype(str),
        failure["packets_lost_during_convergence"],
        color="#b45309",
    )
    axes[1, 1].set(
        title="Packets lost during convergence",
        xlabel="Repetition",
        ylabel="Packets",
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
