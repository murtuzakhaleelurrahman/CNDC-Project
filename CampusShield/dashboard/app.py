#!/usr/bin/env python3
"""CampusShield read-only Network Operations Center dashboard."""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "results"
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.queries import (  # noqa: E402
    load_latest_telemetry,
    load_qos_class_history,
    load_recent_events,
    load_results,
    load_runs,
    load_telemetry_history,
)
from dashboard.theme import NOC_CSS  # noqa: E402


DEFAULT_DATABASE_PATH = PROJECT_ROOT / "database" / "campusshield.db"
DATABASE_PATH = Path(os.environ.get("CAMPUSSHIELD_DB_PATH", str(DEFAULT_DATABASE_PATH)))

COLORS = {
    "bg": "#07111f", "panel": "#0c1d2d", "line": "#24384a",
    "text": "#f4f7fa", "muted": "#9db0c0", "dim": "#6f8496",
    "cyan": "#38bdf8", "green": "#32d583", "amber": "#f5b942",
    "red": "#f97066", "blue": "#7aa2f7",
}

NAVIGATION = (
    "Overview", "Topology", "Telemetry", "Routing", "QoS", "ANRE",
    "Experiments", "Events", "System",
)

RUN_TYPE_LABELS = {
    "BASELINE": "Baseline",
    "CONGESTION_ANRE_OFF": "ANRE off",
    "CONGESTION_STATIC_TUNED": "Tuned static",
    "CONGESTION_ANRE_ON": "ANRE on",
    "FAILURE_RECOVERY": "Recovery",
    "OSPF_DEFAULT": "OSPF default",
    "OSPF_TUNED": "OSPF tuned",
    "ADAPTIVE_ROUTING": "Adaptive routing",
    "VALIDATION": "Validation",
}


def sidebar_run_label(run: dict[str, Any]) -> str:
    label = RUN_TYPE_LABELS.get(str(run.get("run_type")), str(run.get("run_type", "Run")).replace("_", " ").title())
    name = str(run.get("name") or "")
    repetition = name.lower().rsplit("repetition ", 1)[-1] if "repetition " in name.lower() else ""
    suffix = f" · R{repetition}" if repetition.isdigit() else ""
    if str(run.get("status", "")).upper() != "COMPLETED":
        suffix += f" · {str(run.get('status') or 'Unknown').title()}"
    return f"#{run['id']} · {label}{suffix}"

QOS_POLICIES = {
    "NORMAL": {"Emergency / Real-Time": 20, "Academic / Administrative": 50, "Hostel / Bulk": 30},
    "DEGRADED": {"Emergency / Real-Time": 40, "Academic / Administrative": 45, "Hostel / Bulk": 15},
    "CRITICAL": {"Emergency / Real-Time": 55, "Academic / Administrative": 35, "Hostel / Bulk": 10},
    "NO_CONGESTION": {"Emergency / Real-Time": 20, "Academic / Administrative": 50, "Hostel / Bulk": 30},
}

CORE_LINKS = [
    {"name": "R1–R2", "network": "10.10.255.0/30", "cost": 10, "capacity": 100, "delay": "5 ms", "interfaces": "r1-eth0 ↔ r2-eth0"},
    {"name": "R1–R3", "network": "10.10.255.4/30", "cost": 15, "capacity": 100, "delay": "5 ms", "interfaces": "r1-eth1 ↔ r3-eth0"},
    {"name": "R2–R3", "network": "10.10.255.8/30", "cost": 15, "capacity": 100, "delay": "5 ms", "interfaces": "r2-eth1 ↔ r3-eth1"},
]

SEGMENTS = [
    {"segment": "Emergency", "subnet": "10.10.10.0/26", "gateway": "10.10.10.1", "router": "R1", "host": "emergency1 · 10.10.10.10"},
    {"segment": "Admin", "subnet": "10.10.20.0/24", "gateway": "10.10.20.1", "router": "R2", "host": "admin1 · 10.10.20.10"},
    {"segment": "Academic", "subnet": "10.10.30.0/23", "gateway": "10.10.30.1", "router": "R2", "host": "academic1 · 10.10.30.10"},
    {"segment": "Hostel", "subnet": "10.10.40.0/22", "gateway": "10.10.40.1", "router": "R3", "host": "hostel1 · 10.10.40.10"},
    {"segment": "IoT/CCTV", "subnet": "10.10.50.0/25", "gateway": "10.10.50.1", "router": "R3", "host": "iot1 · 10.10.50.10"},
]


st.set_page_config(
    page_title="CampusShield NOC", layout="wide",
    initial_sidebar_state="auto",
)
st.markdown(NOC_CSS, unsafe_allow_html=True)


def esc(value: Any) -> str:
    return html.escape("—" if value is None else str(value))


def display_value(value: Any, suffix: str = "", decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Unavailable"
    if isinstance(value, (int, float)):
        return f"{value:.{decimals}f}{suffix}"
    return f"{value}{suffix}"


def state_class(state: str | None) -> str:
    return {
        "NORMAL": "cs-normal", "DEGRADED": "cs-degraded",
        "CRITICAL": "cs-critical", "DISABLED": "cs-disabled",
    }.get(str(state or "UNKNOWN").upper(), "cs-unknown")


def format_timestamp(value: Any) -> str:
    if not value:
        return "No timestamp"
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(timestamp):
        return str(value)
    return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")


def latest_result(pattern: str) -> Path | None:
    files = sorted(RESULTS_ROOT.glob(pattern))
    return files[-1] if files else None


def read_result(pattern: str) -> tuple[pd.DataFrame | None, Path | None]:
    path = latest_result(pattern)
    if path is None:
        return None, None
    try:
        return pd.read_csv(path), path
    except (OSError, pd.errors.ParserError):
        return None, path


def style_figure(figure: go.Figure, height: int = 330) -> go.Figure:
    figure.update_layout(
        height=height, margin=dict(l=28, r=20, t=46, b=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=COLORS["panel"],
        font=dict(family="Segoe UI, Arial, sans-serif", color=COLORS["muted"], size=11),
        title_font=dict(color=COLORS["text"], size=14),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.12, x=0),
        hoverlabel=dict(bgcolor="#102436", bordercolor=COLORS["line"], font_color=COLORS["text"]),
        hovermode="x unified",
    )
    figure.update_xaxes(gridcolor=COLORS["line"], zeroline=False, linecolor=COLORS["line"])
    figure.update_yaxes(gridcolor=COLORS["line"], zeroline=False, linecolor=COLORS["line"])
    return figure


def section_header(title: str, note: str = "") -> None:
    st.markdown(
        f'<div class="cs-section"><h2>{esc(title)}</h2><p>{esc(note)}</p></div>',
        unsafe_allow_html=True,
    )


def empty_state(message: str) -> None:
    st.markdown(f'<div class="cs-empty">{esc(message)}</div>', unsafe_allow_html=True)


def render_header(page: str) -> None:
    st.markdown(
        f"""
        <div class="cs-topbar">
          <div><h1 class="cs-title">{esc(page)}</h1>
          <p class="cs-subtitle">CampusShield Network Operations Center</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_state_line(latest: dict[str, Any] | None) -> None:
    if latest is None:
        empty_state("No telemetry is stored for this run. Select another run or inspect its Events and System pages.")
        return
    state = str(latest.get("anre_state") or "UNKNOWN").upper()
    score = display_value(latest.get("nhs"), "/100", 1)
    st.markdown(
        f"""
        <div class="cs-state-line">
          <div class="cs-state-primary"><strong>Network health</strong>
          <span class="cs-score">{esc(score)}</span>
          <span class="cs-pill {state_class(state)}">{esc(state)}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_measurements(latest: dict[str, Any] | None) -> None:
    if latest is None:
        return
    measurements = [
        ("RTT", display_value(latest.get("rtt_ms"), " ms")),
        ("Packet loss", display_value(latest.get("packet_loss_percent"), "%")),
        ("Jitter", display_value(latest.get("jitter_ms"), " ms")),
        ("Utilization", display_value(latest.get("utilization_percent"), "%")),
    ]
    content = "".join(
        f'<div class="cs-measure"><div class="cs-measure-label">{esc(label)}</div>'
        f'<div class="cs-measure-value">{esc(value)}</div></div>'
        for label, value in measurements
    )
    st.markdown(f'<div class="cs-measurements">{content}</div>', unsafe_allow_html=True)


def panel_html(title: str, rows: list[tuple[str, Any]], note: str = "") -> str:
    body = "".join(
        f'<div class="cs-kv"><div class="cs-k">{esc(key)}</div><div class="cs-v">{esc(value)}</div></div>'
        for key, value in rows
    )
    return (
        '<div class="cs-panel">'
        f'<div class="cs-panel-head"><div class="cs-panel-title">{esc(title)}</div>'
        f'<span class="cs-panel-note">{esc(note)}</span></div>{body}</div>'
    )


def event_category(event: dict[str, Any]) -> str:
    source = f"{event.get('component', '')} {event.get('event_type', '')}".lower()
    for needle, category in (
        ("anre", "ANRE"), ("qos", "QoS"), ("ospf", "OSPF"),
        ("route", "Routing"), ("fail", "Failure"), ("recover", "Recovery"),
    ):
        if needle in source:
            return category
    return "System"


def render_event_stream(events: list[dict[str, Any]], limit: int = 8) -> None:
    if not events:
        empty_state("No controller or routing events were recorded for this run.")
        return
    rows = []
    for event in events[:limit]:
        time_text = format_timestamp(event.get("timestamp_utc")).replace(" UTC", "")
        rows.append(
            '<div class="cs-event">'
            f'<div class="cs-event-time">{esc(time_text)}</div>'
            f'<div class="cs-event-cat">{esc(event_category(event))}</div>'
            f'<div class="cs-event-msg">{esc(event.get("message") or event.get("event_type"))}</div>'
            '</div>'
        )
    st.markdown('<div class="cs-panel">' + "".join(rows) + '</div>', unsafe_allow_html=True)


def topology_figure(latest: dict[str, Any] | None, inspected_link: str | None = None) -> go.Figure:
    active_interface = str((latest or {}).get("route_interface") or "")
    active_links = {"R1–R2"} if active_interface == "r1-eth0" else ({"R1–R3", "R2–R3"} if active_interface == "r1-eth1" else set())
    positions = {
        "R1": (0.0, 1.0), "R2": (2.0, 1.0), "R3": (1.0, 0.0),
        "Emergency": (-0.65, 1.55), "Admin": (2.65, 1.5), "Academic": (2.7, .55),
        "Hostel": (.35, -.7), "IoT/CCTV": (1.7, -.7),
    }
    core_pairs = {"R1–R2": ("R1", "R2"), "R1–R3": ("R1", "R3"), "R2–R3": ("R2", "R3")}
    figure = go.Figure()
    for link in CORE_LINKS:
        name = link["name"]
        start, end = core_pairs[name]
        x0, y0 = positions[start]
        x1, y1 = positions[end]
        active = name in active_links
        inspected = name == inspected_link
        color = COLORS["cyan"] if active else (COLORS["blue"] if inspected else COLORS["line"])
        figure.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode="lines",
            line=dict(color=color, width=5 if active else (4 if inspected else 2), dash=None if active else "dot"),
            hovertemplate=(f"<b>{name}</b><br>{link['network']}<br>Configured cost {link['cost']}"
                           f"<br>{link['capacity']} Mbps · {link['delay']}<extra></extra>"),
            showlegend=False,
        ))
    for segment, router in (("Emergency", "R1"), ("Admin", "R2"), ("Academic", "R2"), ("Hostel", "R3"), ("IoT/CCTV", "R3")):
        sx, sy = positions[segment]
        rx, ry = positions[router]
        figure.add_trace(go.Scatter(
            x=[sx, rx], y=[sy, ry], mode="lines",
            line=dict(color="#274154", width=1.5), hoverinfo="skip", showlegend=False,
        ))
    routers = ["R1", "R2", "R3"]
    figure.add_trace(go.Scatter(
        x=[positions[n][0] for n in routers], y=[positions[n][1] for n in routers],
        mode="markers+text", text=routers, textposition="middle center",
        textfont=dict(color=COLORS["text"], size=13, family="Segoe UI, Arial"),
        marker=dict(symbol="square", size=54, color="#12314a", line=dict(color=COLORS["cyan"], width=1.5)),
        customdata=[["OSPF router"] for _ in routers],
        hovertemplate="<b>%{text}</b><br>%{customdata[0]}<extra></extra>", showlegend=False,
    ))
    segment_names = ["Emergency", "Admin", "Academic", "Hostel", "IoT/CCTV"]
    subnet_by_name = {item["segment"]: item["subnet"] for item in SEGMENTS}
    figure.add_trace(go.Scatter(
        x=[positions[n][0] for n in segment_names], y=[positions[n][1] for n in segment_names],
        mode="markers+text", text=segment_names, textposition="bottom center",
        textfont=dict(color=COLORS["muted"], size=10),
        marker=dict(size=20, color="#0f2537", line=dict(color="#4b6579", width=1)),
        customdata=[[subnet_by_name[n]] for n in segment_names],
        hovertemplate="<b>%{text}</b><br>%{customdata[0]}<extra></extra>", showlegend=False,
    ))
    figure.update_layout(
        height=430, margin=dict(l=20, r=20, t=25, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=COLORS["panel"],
        xaxis=dict(visible=False, range=[-1.0, 3.0]), yaxis=dict(visible=False, range=[-1.0, 1.9]),
        hoverlabel=dict(bgcolor="#102436", bordercolor=COLORS["line"], font_color=COLORS["text"]),
    )
    return figure


def latest_decision(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        if event_category(event) in {"ANRE", "QoS", "Routing", "Failure", "Recovery"}:
            return event
    return events[0] if events else None


def render_overview(run: dict[str, Any], latest: dict[str, Any] | None, events: list[dict[str, Any]]) -> None:
    render_state_line(latest)
    render_measurements(latest)
    decision = latest_decision(events)
    left, right = st.columns([1.65, .75], gap="small")
    with left:
        section_header("Campus topology", "Active path is taken from the selected telemetry sample")
        st.plotly_chart(topology_figure(latest), width="stretch", config={"displayModeBar": False})
    with right:
        section_header("Current decision", "Latest recorded controller evidence")
        if latest is None:
            empty_state("No decision context is available without telemetry.")
        else:
            route_label = "Primary R1–R2" if latest.get("route_interface") == "r1-eth0" else "Alternate R1–R3–R2"
            rows = [
                ("ANRE state", latest.get("anre_state") or "Not recorded"),
                ("QoS policy", latest.get("qos_policy") or "Not recorded"),
                ("Observed route", route_label),
                ("Next hop", latest.get("route_next_hop") or "Not recorded"),
                ("Interface", latest.get("route_interface") or "Not recorded"),
                ("Last action", (decision or {}).get("action") or "No action recorded"),
                ("Evidence note", (decision or {}).get("message") or "No decision reason recorded"),
            ]
            st.markdown(panel_html("Control plane", rows), unsafe_allow_html=True)
    section_header("Recent operational events", "Newest first")
    render_event_stream(events, limit=6)


def render_topology(latest: dict[str, Any] | None) -> None:
    inspected = st.selectbox("Inspect core link", [link["name"] for link in CORE_LINKS], index=0)
    st.plotly_chart(topology_figure(latest, inspected), width="stretch", config={"displayModeBar": False})
    link = next(item for item in CORE_LINKS if item["name"] == inspected)
    active_interface = str((latest or {}).get("route_interface") or "")
    observed = (
        "Active in selected sample" if (inspected == "R1–R2" and active_interface == "r1-eth0")
        or (inspected in {"R1–R3", "R2–R3"} and active_interface == "r1-eth1")
        else "Configured path; not observed active in selected sample"
    )
    st.markdown(panel_html(
        inspected,
        [("Link state", observed), ("Transit network", link["network"]), ("Interfaces", link["interfaces"]),
         ("Capacity", f"{link['capacity']} Mbps"), ("Configured delay", link["delay"]),
         ("Baseline OSPF cost", link["cost"])],
        "Configuration plus selected-run observation",
    ), unsafe_allow_html=True)
    section_header("Campus segments", "Addressing defined by the topology")
    st.dataframe(pd.DataFrame(SEGMENTS), width="stretch", hide_index=True)


def render_telemetry(latest: dict[str, Any] | None, history: list[dict[str, Any]]) -> None:
    render_measurements(latest)
    if not history:
        empty_state("No telemetry history is stored for this run.")
        return
    frame = pd.DataFrame(history)
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    quality = make_subplots(specs=[[{"secondary_y": True}]])
    quality.add_trace(go.Scatter(x=frame["timestamp_utc"], y=frame["rtt_ms"], name="RTT", line=dict(color=COLORS["cyan"], width=2)), secondary_y=False)
    quality.add_trace(go.Scatter(x=frame["timestamp_utc"], y=frame["jitter_ms"], name="Jitter", line=dict(color=COLORS["blue"], width=1.5)), secondary_y=False)
    quality.add_trace(go.Scatter(x=frame["timestamp_utc"], y=frame["packet_loss_percent"], name="Packet loss", line=dict(color=COLORS["red"], width=1.5)), secondary_y=True)
    quality.update_yaxes(title_text="Milliseconds", secondary_y=False)
    quality.update_yaxes(title_text="Loss (%)", secondary_y=True)
    style_figure(quality, 360).update_layout(title="Latency, jitter, and packet loss")
    st.plotly_chart(quality, width="stretch", config={"displaylogo": False})
    traffic = px.line(
        frame, x="timestamp_utc", y=["tx_mbps", "rx_mbps", "utilization_percent"],
        labels={"timestamp_utc": "Time (UTC)", "value": "Measured value", "variable": "Series"},
        color_discrete_sequence=[COLORS["cyan"], COLORS["blue"], COLORS["amber"]],
        title="Throughput and bandwidth utilization",
    )
    st.plotly_chart(style_figure(traffic, 350), width="stretch", config={"displaylogo": False})
    with st.expander("Telemetry records and accessible chart data"):
        st.dataframe(frame, width="stretch", hide_index=True)


def render_routing(latest: dict[str, Any] | None, events: list[dict[str, Any]]) -> None:
    if latest:
        current_path = "R1 → R2 (preferred)" if latest.get("route_interface") == "r1-eth0" else "R1 → R3 → R2 (alternate)"
        st.markdown(panel_html(
            "Observed forwarding decision",
            [("Current route", current_path), ("Next hop", latest.get("route_next_hop") or "Not recorded"),
             ("Egress interface", latest.get("route_interface") or "Not recorded"),
             ("Interface state", latest.get("route_state") or "Not recorded"),
             ("Link health", display_value(latest.get("link_health"), "/100", 1))],
            "Selected telemetry sample",
        ), unsafe_allow_html=True)
    else:
        empty_state("No route observation is stored for this run.")
    section_header("Redundant core", "Configured baseline costs; adaptive changes appear in recorded events")
    st.plotly_chart(topology_figure(latest), width="stretch", config={"displayModeBar": False})
    st.dataframe(pd.DataFrame(CORE_LINKS), width="stretch", hide_index=True)
    route_events = [event for event in events if event_category(event) in {"Routing", "OSPF", "Failure", "Recovery"}]
    section_header("Routing and convergence events", "Only events stored for the selected run")
    render_event_stream(route_events, limit=20)


def render_qos(
    latest: dict[str, Any] | None,
    queue_history: list[dict[str, Any]],
) -> None:
    policy_name = str((latest or {}).get("qos_policy") or (latest or {}).get("anre_state") or "").upper()
    rates = QOS_POLICIES.get(policy_name)
    if rates is None:
        empty_state("This run does not record a recognized QoS policy. Configured policies are shown below for reference.")
        policy_name = "NORMAL"
        rates = QOS_POLICIES[policy_name]
        observed_label = "Configured reference only"
    else:
        observed_label = "Observed in selected sample"
    st.markdown(panel_html(
        "QoS policy",
        [("Policy", policy_name), ("Evidence", observed_label), ("Scheduler", "HTB + FQ-CoDel"),
         ("Classification", "DSCP EF / AF21 / CS1"),
         ("Service probe", (
             f"EF (DSCP {latest['probe_dscp_value']})"
             if latest and latest.get("probe_dscp_value") == 46
             else "Not recorded for this run"
         )),
         ("Core capacity", "100 Mbps")],
    ), unsafe_allow_html=True)
    frame = pd.DataFrame({"Traffic class": list(rates), "Allocation (Mbps)": list(rates.values())})
    figure = px.bar(
        frame, x="Allocation (Mbps)", y="Traffic class", orientation="h", text="Allocation (Mbps)",
        color="Traffic class", color_discrete_map={
            "Emergency / Real-Time": COLORS["red"],
            "Academic / Administrative": COLORS["cyan"],
            "Hostel / Bulk": COLORS["blue"],
        }, title=f"{policy_name} bandwidth allocation",
    )
    figure.update_traces(texttemplate="%{text} Mbps", textposition="outside", cliponaxis=False)
    figure.update_layout(showlegend=False)
    st.plotly_chart(style_figure(figure, 320), width="stretch", config={"displaylogo": False})
    section_header("Policy matrix", "Controller-defined allocations; values are not synthesized")
    matrix = pd.DataFrame(QOS_POLICIES).T.reset_index(names="Policy")
    st.dataframe(matrix, width="stretch", hide_index=True)
    section_header(
        "Kernel queue evidence",
        "Cumulative tc counters and instantaneous backlog from the selected run",
    )
    if not queue_history:
        empty_state(
            "This run predates per-class queue telemetry or did not use the QoS hierarchy."
        )
        return
    queues = pd.DataFrame(queue_history)
    queues["timestamp_utc"] = pd.to_datetime(queues["timestamp_utc"], utc=True)
    latest_queues = (
        queues.sort_values("timestamp_utc")
        .groupby("class_name", as_index=False)
        .tail(1)
        .copy()
    )
    labels = {
        "emergency": "Emergency (EF)",
        "academic": "Academic (AF21)",
        "bulk": "Bulk (CS1)",
    }
    latest_queues["Traffic class"] = latest_queues["class_name"].map(labels)
    evidence = latest_queues.rename(columns={
        "sent_packets": "Packets sent",
        "dropped_packets": "Packets dropped",
        "overlimits": "Overlimits",
        "backlog_bytes": "Backlog (bytes)",
        "backlog_packets": "Backlog (packets)",
    })
    st.dataframe(
        evidence[[
            "Traffic class", "dscp_value", "Packets sent", "Packets dropped",
            "Overlimits", "Backlog (bytes)", "Backlog (packets)",
        ]].rename(columns={"dscp_value": "DSCP"}),
        width="stretch",
        hide_index=True,
    )
    drop_chart = px.bar(
        evidence,
        x="Traffic class",
        y="Packets dropped",
        color="Traffic class",
        color_discrete_map={
            "Emergency (EF)": COLORS["red"],
            "Academic (AF21)": COLORS["cyan"],
            "Bulk (CS1)": COLORS["blue"],
        },
        title="Cumulative queue drops by traffic class",
    )
    drop_chart.update_layout(showlegend=False)
    st.plotly_chart(
        style_figure(drop_chart, 300),
        width="stretch",
        config={"displaylogo": False},
    )
    backlog = px.line(
        queues,
        x="timestamp_utc",
        y="backlog_bytes",
        color="class_name",
        labels={
            "timestamp_utc": "Time (UTC)",
            "backlog_bytes": "Backlog (bytes)",
            "class_name": "Traffic class",
        },
        color_discrete_map={
            "emergency": COLORS["red"],
            "academic": COLORS["cyan"],
            "bulk": COLORS["blue"],
        },
        title="Queue backlog over time",
    )
    st.plotly_chart(
        style_figure(backlog, 320),
        width="stretch",
        config={"displaylogo": False},
    )


def render_anre(run: dict[str, Any], latest: dict[str, Any] | None, events: list[dict[str, Any]]) -> None:
    render_state_line(latest)
    st.markdown(
        """
        <div class="cs-loop">
          <div class="cs-loop-step"><b>MONITOR</b><span>Collect link and probe telemetry</span></div>
          <div class="cs-loop-step"><b>ANALYZE</b><span>Calculate NHS and thresholds</span></div>
          <div class="cs-loop-step"><b>DECIDE</b><span>Apply hysteresis and hold-down</span></div>
          <div class="cs-loop-step"><b>ACT</b><span>Change QoS or OSPF cost</span></div>
          <div class="cs-loop-step"><b>MEASURE AGAIN</b><span>Verify the network response</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    anre_events = [event for event in events if event_category(event) in {"ANRE", "QoS", "Routing", "Failure", "Recovery"}]
    decision = latest_decision(anre_events)
    section_header("Decision context", "Latest evidence recorded by the controller")
    if latest:
        st.markdown(panel_html(
            "ANRE decision",
            [("Current state", latest.get("anre_state") or "Not recorded"),
             ("Current NHS", display_value(latest.get("nhs"), "/100", 1)),
             ("Current action", (decision or {}).get("action") or "No action recorded"),
             ("Previous state", (decision or {}).get("previous_state") or "Not recorded"),
             ("QoS policy", latest.get("qos_policy") or "Not recorded"),
             ("Reason", (decision or {}).get("message") or "No reason recorded")],
        ), unsafe_allow_html=True)
    else:
        empty_state("ANRE context is unavailable because the selected run has no telemetry.")
    section_header("Recent adaptive decisions", "State changes, QoS actions, routing actions, and recovery")
    render_event_stream(anre_events, limit=25)


def hypothesis_table(
    congestion: pd.DataFrame,
    failure: pd.DataFrame,
    ospf: pd.DataFrame | None = None,
) -> pd.DataFrame:
    off = congestion[congestion["scenario"] == "ANRE_OFF"]
    on = congestion[congestion["scenario"] == "ANRE_ON"]
    recovery_supported = (
        on["recovery_nhs_change"].mean() > 0
        if "recovery_nhs_change" in congestion.columns
        else on["mean_nhs"].mean() > off["mean_nhs"].mean()
    )
    recovery_criterion = (
        "ANRE NHS increases from congestion to the recovery phase"
        if "recovery_nhs_change" in congestion.columns
        else "Mean NHS increases with ANRE"
    )
    checks = [
        ("H1 · RTT", on["mean_rtt_ms"].mean() < off["mean_rtt_ms"].mean(), "Mean RTT decreases with ANRE"),
        ("H2 · Packet loss", on["emergency_udp_loss_percent"].mean() < off["emergency_udp_loss_percent"].mean(), "Emergency UDP loss decreases"),
        ("H3 · Jitter", on["emergency_udp_jitter_ms"].mean() < off["emergency_udp_jitter_ms"].mean(), "Emergency UDP jitter decreases"),
        ("H4 · Recovery", recovery_supported, recovery_criterion),
        ("H5 · QoS trade-off", on["emergency_throughput_mbps"].mean() > off["emergency_throughput_mbps"].mean() and on["bulk_throughput_mbps"].mean() < off["bulk_throughput_mbps"].mean(), "Emergency gains capacity while bulk is restricted"),
        ("H6 · Routing recovery", failure["route_after_failure"].str.contains("r1-eth1", na=False).all() and failure["route_after_restoration"].str.contains("r1-eth0", na=False).all(), "Every repetition uses backup and restores primary"),
    ]
    rows = [{"Hypothesis": name, "Outcome": "SUPPORTED" if result else "NOT SUPPORTED", "Measured criterion": criterion} for name, result, criterion in checks]
    if ospf is None or ospf.empty:
        rows.append({"Hypothesis": "H7 · Tuned OSPF", "Outcome": "NOT TESTED", "Measured criterion": "Phase 3 evidence is not available"})
    else:
        default_ms = ospf.loc[
            ospf["scenario"] == "OSPF_DEFAULT", "service_interruption_ms"
        ].mean()
        tuned_ms = ospf.loc[
            ospf["scenario"] == "OSPF_TUNED", "service_interruption_ms"
        ].mean()
        supported = tuned_ms < default_ms
        improvement = ((default_ms - tuned_ms) / default_ms) * 100 if default_ms else 0
        rows.append({
            "Hypothesis": "H7 · Tuned OSPF",
            "Outcome": "SUPPORTED" if supported else "NOT SUPPORTED",
            "Measured criterion": (
                f"Tuned {tuned_ms:.1f} ms vs default {default_ms:.1f} ms "
                f"({improvement:+.1f}% improvement)"
            ),
        })
    return pd.DataFrame(rows)


def render_experiments() -> None:
    baseline, baseline_path = read_result("baseline_run_*.csv")
    congestion, congestion_path = read_result("congestion_comparison_*.csv")
    failure, failure_path = read_result("failure_recovery_*.csv")
    ospf, ospf_path = read_result("ospf_optimization_*.csv")
    adaptive_routing, adaptive_routing_path = read_result("adaptive_routing_*.csv")
    section_header("Experiment 1 · Baseline calibration", baseline_path.name if baseline_path else "No result file")
    if baseline is None or baseline.empty:
        empty_state("No baseline CSV is available.")
    else:
        baseline_summary = [
            ("Samples", len(baseline)), ("Mean NHS", display_value(baseline["nhs"].mean(), "/100", 2)),
            ("Mean RTT", display_value(baseline["rtt_ms"].mean(), " ms", 3)),
            ("Mean loss", display_value(baseline["packet_loss_percent"].mean(), "%", 3)),
            ("Mean jitter", display_value(baseline["jitter_ms"].mean(), " ms", 3)),
            ("Mean utilization", display_value(baseline["utilization_percent"].mean(), "%", 3)),
        ]
        st.markdown(panel_html("Healthy-network reference", baseline_summary), unsafe_allow_html=True)
        base = baseline.copy()
        base["timestamp_utc"] = pd.to_datetime(base["timestamp_utc"], utc=True)
        figure = px.line(base, x="timestamp_utc", y="nhs", labels={"timestamp_utc": "Time (UTC)", "nhs": "NHS"}, title="Baseline Network Health Score")
        figure.update_traces(line_color=COLORS["green"], line_width=2)
        st.plotly_chart(style_figure(figure, 300), width="stretch", config={"displaylogo": False})

    section_header("Experiment 2 · Three-arm adaptive comparison", congestion_path.name if congestion_path else "No result file")
    if congestion is None or congestion.empty:
        empty_state("No complete ANRE comparison CSV is available.")
    else:
        comparison_metrics = [
            ("Emergency throughput", "emergency_throughput_mbps", "Mbps"),
            ("Emergency UDP loss", "emergency_udp_loss_percent", "%"),
            ("Emergency jitter", "emergency_udp_jitter_ms", "ms"),
            ("Mean NHS", "mean_nhs", "/100"), ("Bulk throughput", "bulk_throughput_mbps", "Mbps"),
        ]
        optional_metrics = [
            ("Recovery NHS change", "recovery_nhs_change", "points"),
            ("Emergency queue drops", "emergency_queue_drops_congestion", "packets"),
            ("Peak emergency backlog", "peak_emergency_backlog_bytes", "bytes"),
        ]
        comparison_metrics.extend(
            item for item in optional_metrics if item[1] in congestion.columns
        )
        scenario_labels = {
            "ANRE_OFF": "Basic static",
            "STATIC_TUNED": "Tuned static",
            "ANRE_ON": "Adaptive ANRE",
        }
        long_rows = []
        for label, column, unit in comparison_metrics:
            for _, row in congestion.iterrows():
                long_rows.append({"Metric": label, "Scenario": scenario_labels.get(row["scenario"], row["scenario"]), "Repetition": str(row["repetition"]), "Value": row[column], "Unit": unit})
        long_frame = pd.DataFrame(long_rows)
        selected_metric = st.selectbox("Comparison metric", [item[0] for item in comparison_metrics])
        selected = long_frame[long_frame["Metric"] == selected_metric]
        chart = px.line(
            selected,
            x="Scenario",
            y="Value",
            color="Repetition",
            markers=True,
            category_orders={
                "Scenario": ["Basic static", "Tuned static", "Adaptive ANRE"]
            },
            title=f"Matched {selected_metric.lower()} results",
        )
        st.plotly_chart(style_figure(chart, 340), width="stretch", config={"displaylogo": False})

    section_header("Experiment 3 · Physical link failure", failure_path.name if failure_path else "No result file")
    if failure is None or failure.empty:
        empty_state("No complete link-failure CSV is available.")
    else:
        failure_chart = go.Figure()
        failure_chart.add_bar(name="Service interruption", x=failure["repetition"], y=failure["service_interruption_ms"], marker_color=COLORS["amber"])
        failure_chart.add_bar(name="Route convergence", x=failure["repetition"], y=failure["route_convergence_ms"], marker_color=COLORS["cyan"])
        failure_chart.update_layout(title="Recovery timing by repetition", barmode="group", xaxis_title="Repetition", yaxis_title="Milliseconds")
        st.plotly_chart(style_figure(failure_chart, 340), width="stretch", config={"displaylogo": False})
        st.markdown(panel_html("Measured recovery summary", [
            ("Mean packets lost", display_value(failure["packets_lost_during_convergence"].mean(), "", 2)),
            ("Mean interruption", display_value(failure["service_interruption_ms"].mean(), " ms", 2)),
            ("Mean convergence", display_value(failure["route_convergence_ms"].mean(), " ms", 2)),
            ("Mean primary restoration", display_value(failure["primary_restoration_ms"].mean(), " ms", 2)),
        ]), unsafe_allow_html=True)

    ospf_note = ospf_path.name if ospf_path else "No result file"
    if ospf is not None and not ospf.empty:
        ospf_repetitions = int(ospf["repetition"].nunique())
        ospf_note += (
            f" · Formal evidence ({ospf_repetitions} matched repetitions)"
            if ospf_repetitions >= 10
            else f" · Pilot evidence ({ospf_repetitions} of 10 matched repetitions)"
        )
    section_header("Experiment 4 · OSPF optimization", ospf_note)
    if ospf is None or ospf.empty:
        empty_state("No default-versus-tuned OSPF comparison is available yet.")
    else:
        ospf_labels = {"OSPF_DEFAULT": "Default", "OSPF_TUNED": "Tuned"}
        ospf_chart = go.Figure()
        for scenario, color in (("OSPF_DEFAULT", COLORS["dim"]), ("OSPF_TUNED", COLORS["cyan"])):
            sample = ospf[ospf["scenario"] == scenario]
            ospf_chart.add_scatter(
                name=ospf_labels[scenario],
                x=sample["repetition"],
                y=sample["service_interruption_ms"],
                mode="lines+markers",
                line=dict(color=color, width=2),
            )
        ospf_chart.update_layout(
            title="Matched service interruption by repetition",
            xaxis_title="Repetition",
            yaxis_title="Milliseconds",
        )
        st.plotly_chart(style_figure(ospf_chart, 340), width="stretch", config={"displaylogo": False})
        default_rows = ospf[ospf["scenario"] == "OSPF_DEFAULT"]
        tuned_rows = ospf[ospf["scenario"] == "OSPF_TUNED"]
        default_ms = default_rows["service_interruption_ms"].mean()
        tuned_ms = tuned_rows["service_interruption_ms"].mean()
        improvement = ((default_ms - tuned_ms) / default_ms) * 100 if default_ms else 0
        st.markdown(panel_html("Measured OSPF comparison", [
            ("Matched repetitions", int(min(default_rows["repetition"].nunique(), tuned_rows["repetition"].nunique()))),
            ("Default interruption", display_value(default_ms, " ms", 2)),
            ("Tuned interruption", display_value(tuned_ms, " ms", 2)),
            ("Recovery improvement", display_value(improvement, "%", 2)),
            ("Default packets lost", display_value(default_rows["packets_lost_during_convergence"].mean(), "", 2)),
            ("Tuned packets lost", display_value(tuned_rows["packets_lost_during_convergence"].mean(), "", 2)),
        ]), unsafe_allow_html=True)

    routing_note = (
        adaptive_routing_path.name if adaptive_routing_path else "No result file"
    )
    if adaptive_routing is not None and not adaptive_routing.empty:
        routing_repetitions = int(adaptive_routing["repetition"].nunique())
        routing_note += (
            f" · Formal evidence ({routing_repetitions} repetitions)"
            if routing_repetitions >= 10
            else f" · Pilot evidence ({routing_repetitions} of 10 repetitions)"
        )
    section_header("Experiment 5 · Closed-loop adaptive routing", routing_note)
    if adaptive_routing is None or adaptive_routing.empty:
        empty_state("No adaptive-routing experiment is available yet.")
    else:
        routing_chart = go.Figure()
        for metric, label, color in (
            ("degradation_detection_ms", "Degradation detection", COLORS["amber"]),
            ("route_shift_ms", "Route shift", COLORS["cyan"]),
            ("route_restore_ms", "Route restoration", COLORS["green"]),
        ):
            routing_chart.add_bar(
                name=label,
                x=adaptive_routing["repetition"],
                y=adaptive_routing[metric],
                marker_color=color,
            )
        routing_chart.update_layout(
            title="Controller and routing response by repetition",
            barmode="group",
            xaxis_title="Repetition",
            yaxis_title="Milliseconds",
        )
        st.plotly_chart(
            style_figure(routing_chart, 340),
            width="stretch",
            config={"displaylogo": False},
        )
        st.markdown(panel_html("Closed-loop evidence", [
            ("Mean degradation detection", display_value(adaptive_routing["degradation_detection_ms"].mean(), " ms", 2)),
            ("Mean route shift", display_value(adaptive_routing["route_shift_ms"].mean(), " ms", 2)),
            ("Configured hold-down", display_value(adaptive_routing["hold_down_seconds"].mean(), " s", 1)),
            ("Observed hold-down", display_value(adaptive_routing["hold_down_observed_ms"].mean(), " ms", 2)),
            ("Mean route restoration", display_value(adaptive_routing["route_restore_ms"].mean(), " ms", 2)),
            ("Final ANRE state", ", ".join(sorted(set(adaptive_routing["final_anre_state"].astype(str))))),
        ]), unsafe_allow_html=True)

    if congestion is not None and not congestion.empty and failure is not None and not failure.empty:
        repetitions = int(congestion["repetition"].nunique())
        evidence_note = (
            f"{repetitions} matched repetitions; formal reports include 95% confidence intervals"
            if repetitions >= 10
            else f"Pilot evidence from {repetitions} repetition(s); run 10 for formal analysis"
        )
        section_header("Hypothesis evaluation", evidence_note)
        st.dataframe(hypothesis_table(congestion, failure, ospf), width="stretch", hide_index=True)


def render_events(events: list[dict[str, Any]]) -> None:
    if not events:
        empty_state("No events are stored for the selected run.")
        return
    categories = sorted({event_category(event) for event in events})
    severities = sorted({str(event.get("severity") or "UNKNOWN").upper() for event in events})
    col1, col2 = st.columns(2)
    with col1:
        selected_categories = st.multiselect("Categories", categories, default=categories)
    with col2:
        selected_severities = st.multiselect("Severity", severities, default=severities)
    filtered = [event for event in events if event_category(event) in selected_categories and str(event.get("severity") or "UNKNOWN").upper() in selected_severities]
    if not filtered:
        empty_state("No events match the selected filters.")
        return
    frame = pd.DataFrame([{
        "Timestamp (UTC)": format_timestamp(event.get("timestamp_utc")),
        "Severity": str(event.get("severity") or "UNKNOWN").upper(),
        "Category": event_category(event), "Event": event.get("event_type"),
        "Description": event.get("message"), "Action": event.get("action"),
    } for event in filtered])
    st.dataframe(frame, width="stretch", hide_index=True)
    section_header("Event timeline", f"{len(filtered)} matching records")
    render_event_stream(filtered, limit=50)


def render_system(run: dict[str, Any], latest: dict[str, Any] | None, results: list[dict[str, Any]]) -> None:
    st.markdown(panel_html(
        "Selected run",
        [("Run ID", run["id"]), ("Name", run["name"]), ("Type", run["run_type"]),
         ("Status", run["status"]), ("Experimental", "Yes" if run["is_experimental"] else "No"),
         ("Started", format_timestamp(run.get("started_at_utc"))), ("Ended", format_timestamp(run.get("ended_at_utc"))),
         ("Telemetry rows", run.get("telemetry_count", 0)), ("Event rows", run.get("event_count", 0)),
         ("Result rows", run.get("result_count", 0))],
    ), unsafe_allow_html=True)
    section_header("Data sources", "Read-only dashboard access")
    st.markdown(panel_html("Runtime", [
        ("SQLite database", DATABASE_PATH), ("Database exists", "Yes" if DATABASE_PATH.is_file() else "No"),
        ("Results directory", RESULTS_ROOT), ("Latest telemetry", format_timestamp((latest or {}).get("timestamp_utc"))),
        ("Dashboard mode", "Read-only"),
    ]), unsafe_allow_html=True)
    section_header("Stored result metrics", "Rows committed for the selected run")
    if results:
        result_frame = pd.DataFrame(results)[["scenario", "traffic_class", "metric_name", "metric_value", "unit"]]
        st.dataframe(result_frame, width="stretch", hide_index=True)
    else:
        empty_state("This run has no stored result metrics.")
    st.markdown('<p class="cs-caption">The dashboard never changes Mininet, FRRouting, QoS, routing, security, or experiment state.</p>', unsafe_allow_html=True)


if not DATABASE_PATH.is_file():
    st.error(f"CampusShield database not found: {DATABASE_PATH}")
    st.code("python3 database/validate_database.py", language="bash")
    st.stop()

try:
    RUNS = load_runs(DATABASE_PATH)
except Exception as error:  # pragma: no cover
    st.error(f"Could not read the CampusShield database: {error}")
    st.stop()

if not RUNS:
    st.warning("The database contains no runs yet. Complete a validation or experiment first.")
    st.stop()

run_by_id = {int(run["id"]): run for run in RUNS}
run_labels = {int(run["id"]): sidebar_run_label(run) for run in RUNS}

st.sidebar.markdown(
    '<div class="cs-brand"><div class="cs-brand-name">CampusShield</div>'
    '<div class="cs-brand-sub">Network Operations Center</div>'
    '<div class="cs-live"><span class="cs-live-dot"></span>Evidence console</div></div>'
    '<div class="cs-side-label">Workspace</div>',
    unsafe_allow_html=True,
)
PAGE = st.sidebar.radio("Primary navigation", NAVIGATION, label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.markdown('<div class="cs-side-label cs-side-label-controls">Evidence</div>', unsafe_allow_html=True)
SELECTED_RUN_ID = st.sidebar.selectbox("Run", options=list(run_by_id), format_func=lambda run_id: run_labels[run_id])
SAMPLE_LIMIT = int(st.sidebar.number_input(
    "History samples", min_value=25, max_value=1_000, value=300, step=25,
))
LIVE_REFRESH = st.sidebar.toggle("Live refresh", value=False)
if st.sidebar.button("Reload evidence", width="stretch"):
    st.rerun()

SELECTED_RUN = run_by_id[SELECTED_RUN_ID]
render_header(PAGE)


@st.fragment(run_every=2.0 if LIVE_REFRESH else None)
def render_page() -> None:
    latest = load_latest_telemetry(DATABASE_PATH, SELECTED_RUN_ID)
    history = load_telemetry_history(DATABASE_PATH, SELECTED_RUN_ID, SAMPLE_LIMIT)
    events = load_recent_events(DATABASE_PATH, SELECTED_RUN_ID, limit=200)
    results = load_results(DATABASE_PATH, SELECTED_RUN_ID)
    if PAGE == "Overview":
        render_overview(SELECTED_RUN, latest, events)
    elif PAGE == "Topology":
        render_topology(latest)
    elif PAGE == "Telemetry":
        render_telemetry(latest, history)
    elif PAGE == "Routing":
        render_routing(latest, events)
    elif PAGE == "QoS":
        queue_history = load_qos_class_history(
            DATABASE_PATH, SELECTED_RUN_ID, SAMPLE_LIMIT
        )
        render_qos(latest, queue_history)
    elif PAGE == "ANRE":
        render_anre(SELECTED_RUN, latest, events)
    elif PAGE == "Experiments":
        render_experiments()
    elif PAGE == "Events":
        render_events(events)
    elif PAGE == "System":
        render_system(SELECTED_RUN, latest, results)


render_page()
