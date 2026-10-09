---
name: CampusShield
description: Evidence-first network operations UI built as a dark infrastructure atlas.
colors:
  canvas: "#07111f"
  shell: "#091827"
  panel: "#0c1d2d"
  panel-raised: "#102436"
  border: "#24384a"
  border-strong: "#355066"
  text-primary: "#f4f7fa"
  text-secondary: "#9db0c0"
  text-tertiary: "#8ba0b2"
  route-active: "#38bdf8"
  status-normal: "#32d583"
  status-degraded: "#f5b942"
  status-critical: "#f97066"
  route-inspected: "#7aa2f7"
typography:
  display:
    fontFamily: '"Segoe UI Variable", "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "1.28rem"
    fontWeight: 720
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  headline:
    fontFamily: '"Segoe UI Variable", "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: '"Segoe UI Variable", "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: '"Segoe UI Variable", "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "0.78rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: '"Segoe UI Variable", "Segoe UI", Helvetica, Arial, sans-serif'
    fontSize: "0.68rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0.06em"
  data:
    fontFamily: '"Cascadia Code", "SFMono-Regular", Consolas, monospace'
    fontSize: "1.08rem"
    fontWeight: 650
    lineHeight: 1.25
rounded:
  control: "4px"
  surface: "6px"
  pill: "999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.25rem"
components:
  button-secondary:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.75rem"
    height: "36px"
  navigation-item-active:
    backgroundColor: "#12314a"
    textColor: "#d9f3ff"
    rounded: "{rounded.control}"
    padding: "0 0.7rem"
    height: "38px"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.surface}"
    padding: "0.9rem"
  input:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    height: "38px"
  status-pill-normal:
    textColor: "{colors.status-normal}"
    rounded: "{rounded.pill}"
    padding: "0.24rem 0.48rem"
  status-pill-degraded:
    textColor: "{colors.status-degraded}"
    rounded: "{rounded.pill}"
    padding: "0.24rem 0.48rem"
  status-pill-critical:
    textColor: "{colors.status-critical}"
    rounded: "{rounded.pill}"
    padding: "0.24rem 0.48rem"
---

# Design System: CampusShield

## Overview

**Creative North Star: "Network Atlas"**

CampusShield is a dark infrastructure atlas: a serious network-operations surface where topology, route state, telemetry, decisions, and experimental provenance are the visual story. The system favors evidence density, precise alignment, and progressive disclosure over a marketing hero or a wall of equal KPI cards.

The working field is blue-black, nested operational surfaces are cool navy, and hairline seams organize information without visual noise. Real topology is the signature expression. Every status, trend, and action must remain traceable to SQLite or result-file evidence; missing evidence is shown explicitly.

**Key Characteristics:**

- Dark, compact NOC shell with deliberate information density.
- Real network topology and active routes as the signature visual.
- Evidence-first hierarchy with explicit run and result-file provenance.
- Cyan for interaction and routing; green, amber, and red only for state.
- High-contrast technical values, visible focus, and honest empty states.

## Colors

The palette is a cool midnight infrastructure field with restrained cyan interaction cues and strictly semantic state accents.

### Primary

- **Active Route Cyan** (`route-active`): Active links, interactive emphasis, links, focus outlines, and selected route geometry.

### Secondary

- **Inspected Route Blue** (`route-inspected`): A configured or inspected path that is not the active path.

### Tertiary

- **Normal Green**, **Degraded Amber**, and **Critical Red**: Operational state only; pair each color with a text label or other non-color cue.

### Neutral

- **Midnight Canvas** (`canvas`) and **NOC Shell** (`shell`): Main work area and persistent navigation rail.
- **Evidence Panel** (`panel`) and **Raised Panel** (`panel-raised`): Repeated data containers and interactive controls.
- **Hairline Border** (`border`) and **Strong Border** (`border-strong`): Structure, dividers, and emphasized container edges.
- **Primary**, **Secondary**, and **Tertiary Text**: White data, supporting copy, and low-emphasis metadata respectively.

### Named Rules

**The Semantic Signal Rule.** Green, amber, and red communicate NORMAL, DEGRADED, and CRITICAL states only; they are never decorative accents.

**The Cyan Path Rule.** Cyan identifies interaction, keyboard focus, and the active network path, making its rarity operationally meaningful.

## Typography

**Display Font:** Segoe UI Variable (with Segoe UI, Helvetica, Arial, sans-serif fallbacks)  
**Body Font:** Segoe UI Variable (with Segoe UI, Helvetica, Arial, sans-serif fallbacks)  
**Label/Mono Font:** Cascadia Code (with SFMono-Regular, Consolas, monospace fallbacks)

**Character:** The sans stack is compact and workmanlike. Monospace is reserved for measurements, addresses, costs, timestamps, and other evidence where alignment and scan speed matter.

### Hierarchy

- **Display** (720, `1.28rem`, 1.25): Page titles in the compact system bar.
- **Headline** (700, `1.5rem`, 1.25): The network-health statement; its numeric score may rise to `2rem` in the mono face.
- **Title** (700, `1rem`, 1.25): Section and panel hierarchy.
- **Body** (400, `0.78rem`, 1.45): Operational explanations, notes, and controls.
- **Label** (700, `0.68rem`, `0.06em`, uppercase where categorical): Measurement labels, provenance labels, and event categories.
- **Data** (650, `1.08rem`, 1.25): Tabular numeric evidence with tabular figures.

### Named Rules

**The Evidence Face Rule.** Use monospace for machine values, not for general prose or headings.

## Layout

The desktop frame uses a persistent `272px` navigation rail and a fluid main canvas capped at `1540px`. Main content begins with `2rem` horizontal padding, while recurring panels use a compact `0.9rem` gap and roughly `0.75rem–1rem` internal rhythm. The overview privileges the topology canvas with an asymmetric `1.65fr / 0.75fr` evidence grid rather than equal cards.

At `1100px`, two-column regions stack into one column and main padding tightens to `1.1rem`. At `768px`, measurement cells reflow to two columns and the ANRE loop becomes vertical. At `480px`, main padding becomes `0.7rem`, measurements become a single column, key/value rows and event entries stack, and values align left.

**The Topology-First Rule.** When topology shares a row with supporting evidence, topology receives the larger region and remains legible before ancillary detail.

## Elevation & Depth

The system is flat and structurally layered. It uses background tone, one-pixel borders, and nested surfaces instead of card shadows. The only glow is the low semantic halo around the read-only status dot; it indicates state rather than elevation.

### Shadow Vocabulary

- **Live-status halo** (`0 0 0 3px rgba(50,213,131,.12)`): A restrained ring behind the green evidence-console dot.

### Named Rules

**The Tonal Depth Rule.** Surfaces gain hierarchy through navy tone and hairline seams; do not add floating-card shadows.

## Shapes

Geometry is tight and technical. Interactive controls use gently squared `4px` corners, panels use `6px` corners, and only state pills and circular indicators use fully rounded geometry. Borders are normally one pixel; dashed borders identify unavailable or empty evidence. Topology routers are square nodes, reinforcing the infrastructure-map language.

## Components

### Buttons

- **Shape:** Compact control corners (`4px`) with a minimum height of `36px`.
- **Secondary:** Raised navy fill, primary white text, and a strong hairline border.
- **Hover / Focus:** Hover shifts the border to cyan; keyboard focus uses a `2px` cyan outline with a `2px` offset.

### Chips

- **Style:** Status pills use a transparent surface, a one-pixel current-color border, a leading dot, compact uppercase type, and fully rounded ends.
- **State:** Normal, degraded, and critical variants change both label and semantic color; unknown or disabled uses secondary text.

### Cards / Containers

- **Corner Style:** Tight panel rounding (`6px`).
- **Background:** Evidence Panel on the Midnight Canvas.
- **Shadow Strategy:** None; see the Tonal Depth Rule.
- **Border:** One-pixel Hairline Border, strengthened for the primary health line.
- **Internal Padding:** Usually `0.75rem–1rem`, with row dividers preserved for scanability.

### Inputs / Fields

- **Style:** Evidence Panel fill, Strong Border, compact `4px` corners, and readable white values.
- **History input:** Use a direct bounded number field (`25–1000`, step `25`) with keyboard entry and compact decrement/increment controls; do not use a precision-hostile slider.
- **Focus:** Global cyan focus outline; selection fill is a deeper route cyan.
- **Disabled:** Retains legible secondary text and never implies live control over the read-only dashboard.

### Navigation

The `272px` rail separates `Workspace` navigation from compact `Evidence` controls. Nine plain-language destinations use full-width `34px` targets without exposed radio controls; hover adds a raised navy field and subtle border, while the active destination uses a deeper blue field and a two-pixel cyan edge. Run labels are human-readable and compact (for example, `#21 · Recovery · R3`), and implementation paths remain in the System view rather than the navigation shell. A permanently visible close chevron collapses the open rail. When collapsed, the rail reserves zero layout width so the `1540px` canvas remains mathematically centered; a visible, keyboard-focusable `Menu` control restores it.

### Measurement Band

Four measurements share one bordered strip instead of separate cards. Labels are compact uppercase sans text; values are larger monospace with tabular figures. The band reflows from four columns to two at `768px` and one at `480px`.

### Network Topology

The topology map is the signature component. Square router nodes and small circular segment nodes sit on a real campus graph; cyan solid links show the observed active route, blue emphasizes an inspected configured link, and subdued dotted or hairline links show alternatives. Hover detail carries subnet, cost, capacity, and delay without inventing state.

### Empty State

Unavailable evidence appears as muted copy inside a lightly tinted panel with a dashed Strong Border. It names what is missing and, where possible, the next valid action.

## Do's and Don'ts

### Do:

- **Do** keep run provenance in the sidebar and System view, and expose result-file provenance beside the relevant experiment section without crowding page titles.
- **Do** keep topology, values, timestamps, labels, and chart states traceable to real SQLite or CSV evidence.
- **Do** pair every semantic color with a named state, label, line style, or other non-color cue.
- **Do** preserve visible keyboard focus, reduced-motion behavior, mobile access to all nine navigation destinations, and the verified small secondary-text contrast of approximately `6.32:1`.
- **Do** show an explicit unavailable or empty state when evidence is sparse.

### Don't:

- **Don't** fabricate trends, topology state, routing state, decisions, events, or experimental results.
- **Don't** use green, amber, or red as decorative brand colors.
- **Don't** replace the topology-led evidence hierarchy with a generic wall of equal KPI cards.
- **Don't** add soft floating shadows, oversized marketing typography, or spacious consumer-SaaS padding.
- **Don't** hide experimental provenance or imply that validation-only evidence belongs to the selected operational run.
