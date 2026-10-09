"""CampusShield NOC design tokens and Streamlit CSS."""

NOC_CSS = r"""
<style>
:root {
  --cs-bg: #07111f;
  --cs-shell: #091827;
  --cs-panel: #0c1d2d;
  --cs-panel-2: #102436;
  --cs-line: #24384a;
  --cs-line-strong: #355066;
  --cs-text: #f4f7fa;
  --cs-muted: #9db0c0;
  --cs-dim: #8ba0b2;
  --cs-cyan: #38bdf8;
  --cs-green: #32d583;
  --cs-amber: #f5b942;
  --cs-red: #f97066;
  --cs-blue: #7aa2f7;
  --cs-radius: 6px;
  --cs-mono: "Cascadia Code", "SFMono-Regular", Consolas, monospace;
  --cs-sans: "Segoe UI Variable", "Segoe UI", Helvetica, Arial, sans-serif;
}

html, body, [class*="css"] { font-family: var(--cs-sans); }
.stApp { background: var(--cs-bg); color: var(--cs-text); }
[data-testid="stAppViewContainer"] { background: var(--cs-bg); }
[data-testid="stHeader"] { height: 2.7rem; background: rgba(7,17,31,.94); }
[data-testid="stToolbar"] { display:flex !important; }
[data-testid="stDecoration"], [data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] { display:none !important; }
[data-testid="stExpandSidebarButton"] { width:auto; gap:.35rem; padding:0 .35rem; }
[data-testid="stExpandSidebarButton"]::after {
  content:"Menu"; color:var(--cs-muted); font-size:.72rem; font-family:var(--cs-sans); }
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {
  visibility:visible !important; }
[data-testid="stMain"] .block-container {
  max-width: 1540px; padding: 1.25rem 2rem 3rem; }

[data-testid="stSidebar"] {
  background:var(--cs-shell); border-right:1px solid var(--cs-line); }
[data-testid="stSidebar"][aria-expanded="true"] {
  width:272px !important; min-width:272px !important; max-width:272px !important; }
[data-testid="stSidebar"][aria-expanded="false"] {
  width:0 !important; min-width:0 !important; max-width:0 !important; border-right:0; }
[data-testid="stSidebar"][aria-expanded="true"] [data-testid="stSidebarContent"] {
  width:272px !important; padding-top:.5rem; }
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding:0 1rem 1rem; }
[data-testid="stSidebar"] * { color: var(--cs-text); }
[data-testid="stSidebar"] hr { border-color:var(--cs-line); margin:.8rem 0; }
[data-testid="stSidebar"] .stRadio > label,
[data-testid="stSidebar"] .stRadio [data-testid="stWidgetLabel"] { display:none !important; }
[data-testid="stSidebar"] .stRadio,
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { width:100%; }
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> [data-testid="stRadio"]),
[data-testid="stSidebar"] [data-testid="stRadioGroup"] > div { width:100% !important; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { gap:2px; }
[data-testid="stSidebar"] .stRadio label {
  position:relative; display:flex !important; width:100% !important; box-sizing:border-box;
  min-height:34px; padding:0 .65rem; border-radius:4px;
  border:1px solid transparent; transition:background 120ms ease-out, border-color 120ms ease-out; }
[data-testid="stSidebar"] .stRadio [data-testid="stRadioOption"] > div { width:100%; }
[data-testid="stSidebar"] .stRadio [data-testid="stRadioOption"] > div > div:first-child {
  display:none; }
[data-testid="stSidebar"] .stRadio label:hover { background:#102436; border-color:#22384a; }
[data-testid="stSidebar"] .stRadio label:has(input:checked) {
  background:#102b40; border-color:#29475e; }
[data-testid="stSidebar"] .stRadio label:has(input:checked)::before {
  content:""; position:absolute; left:-1px; top:7px; bottom:7px; width:2px;
  border-radius:2px; background:var(--cs-cyan); }
[data-testid="stSidebar"] .stRadio label:has(input:checked) p { color: #d9f3ff; font-weight: 650; }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] label p { font-size:.78rem; }

.cs-brand { padding:.25rem 0 1rem; }
.cs-brand-name { font-size:1rem; font-weight:750; letter-spacing:-.01em; }
.cs-brand-sub { color:var(--cs-muted); font-size:.68rem; margin-top:.16rem; }
.cs-live { display:flex; align-items:center; gap:.4rem; margin-top:.55rem;
  color:var(--cs-muted); font-size:.67rem; }
.cs-live-dot { width:7px; height:7px; border-radius:50%; background:var(--cs-green);
  box-shadow:0 0 0 3px rgba(50,213,131,.12); }
.cs-side-label { margin:0 0 .4rem; color:var(--cs-dim); font-size:.62rem;
  font-weight:700; letter-spacing:.09em; text-transform:uppercase; }
.cs-side-label-controls { margin-top:.1rem; }

[data-testid="stSidebar"] [data-baseweb="select"] > div {
  min-height:40px; padding-left:.2rem; background:#081522 !important; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] { margin-bottom:.25rem; }
[data-testid="stSidebar"] [data-testid="stNumberInput"] { margin:.1rem 0 .25rem; }
[data-testid="stSidebar"] [data-testid="stNumberInput"] input {
  font-family:var(--cs-mono); font-variant-numeric:tabular-nums; }
[data-testid="stSidebar"] [data-testid="stToggle"] { margin:.15rem 0 .4rem; }
[data-testid="stSidebar"] .stButton > button { min-height:34px; }

.cs-topbar { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem;
  padding-bottom:1rem; margin-bottom:1.1rem; border-bottom:1px solid var(--cs-line); }
.cs-title { margin:0; color:var(--cs-text); font-size:1.28rem; line-height:1.25;
  font-weight:720; letter-spacing:-.015em; }
.cs-subtitle { margin:.28rem 0 0; color:var(--cs-muted); font-size:.79rem; }
.cs-state-line { display:block;
  border:1px solid var(--cs-line-strong); background:var(--cs-panel); border-radius:var(--cs-radius);
  margin-bottom:.9rem; overflow:hidden; }
.cs-state-primary { padding:1.05rem 1.2rem; display:flex; align-items:baseline; gap:.75rem; }
.cs-state-primary strong { font-size:1.5rem; letter-spacing:-.025em; }
.cs-state-primary .cs-score { font-family:var(--cs-mono); font-size:2rem; font-weight:650; }
.cs-pill { display:inline-flex; align-items:center; gap:.35rem; padding:.24rem .48rem;
  border:1px solid currentColor; border-radius:999px; font-size:.68rem; font-weight:750;
  letter-spacing:.05em; }
.cs-pill::before { content:""; width:6px; height:6px; border-radius:50%; background:currentColor; }
.cs-normal { color:var(--cs-green); }
.cs-degraded { color:var(--cs-amber); }
.cs-critical { color:var(--cs-red); }
.cs-disabled, .cs-unknown { color:var(--cs-muted); }

.cs-measurements { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
  background:var(--cs-panel); border:1px solid var(--cs-line); border-radius:var(--cs-radius);
  margin-bottom:1rem; }
.cs-measure { min-width:0; padding:.85rem 1rem; border-right:1px solid var(--cs-line); }
.cs-measure:last-child { border-right:0; }
.cs-measure-label { color:var(--cs-muted); font-size:.68rem; text-transform:uppercase;
  letter-spacing:.065em; }
.cs-measure-value { margin-top:.25rem; color:var(--cs-text); font-family:var(--cs-mono);
  font-size:1.08rem; font-variant-numeric:tabular-nums; white-space:nowrap; }

.cs-grid-2 { display:grid; grid-template-columns:minmax(0,1.65fr) minmax(300px,.75fr);
  gap:.9rem; align-items:start; }
.cs-grid-equal { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.9rem; }
.cs-panel { background:var(--cs-panel); border:1px solid var(--cs-line);
  border-radius:var(--cs-radius); overflow:hidden; }
.cs-panel-head { display:flex; justify-content:space-between; align-items:center; gap:1rem;
  min-height:44px; padding:.7rem .9rem; border-bottom:1px solid var(--cs-line); }
.cs-panel-title { margin:0; font-size:.82rem; font-weight:700; color:var(--cs-text); }
.cs-panel-note { color:var(--cs-dim); font-size:.68rem; }
.cs-panel-body { padding:.9rem; }

.cs-kv { display:grid; grid-template-columns:minmax(110px,.7fr) minmax(0,1.3fr);
  gap:0; border-top:1px solid var(--cs-line); }
.cs-kv:first-child { border-top:0; }
.cs-k, .cs-v { padding:.58rem .75rem; font-size:.74rem; }
.cs-k { color:var(--cs-muted); }
.cs-v { color:var(--cs-text); font-family:var(--cs-mono); text-align:right;
  font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }

.cs-section { display:flex; align-items:baseline; justify-content:space-between; gap:1rem;
  margin:1.4rem 0 .65rem; }
.cs-section h2 { margin:0; color:var(--cs-text); font-size:1rem; font-weight:700; }
.cs-section p { margin:0; color:var(--cs-muted); font-size:.72rem; }

.cs-loop { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); border:1px solid var(--cs-line);
  border-radius:var(--cs-radius); overflow:hidden; }
.cs-loop-step { position:relative; padding:.75rem; background:var(--cs-panel);
  border-right:1px solid var(--cs-line); }
.cs-loop-step:last-child { border-right:0; }
.cs-loop-step b { display:block; color:var(--cs-cyan); font-size:.7rem; letter-spacing:.06em; }
.cs-loop-step span { display:block; color:var(--cs-muted); font-size:.66rem; margin-top:.22rem; }

.cs-event { display:grid; grid-template-columns:118px 78px minmax(0,1fr); gap:.7rem;
  padding:.62rem .7rem; border-bottom:1px solid var(--cs-line); align-items:start; }
.cs-event:last-child { border-bottom:0; }
.cs-event-time, .cs-tech { font-family:var(--cs-mono); font-variant-numeric:tabular-nums; }
.cs-event-time { color:var(--cs-dim); font-size:.65rem; }
.cs-event-cat { color:var(--cs-cyan); font-size:.64rem; font-weight:700; text-transform:uppercase; }
.cs-event-msg { color:var(--cs-text); font-size:.72rem; line-height:1.45; }

.cs-empty { border:1px dashed var(--cs-line-strong); border-radius:var(--cs-radius);
  padding:1.25rem; color:var(--cs-muted); font-size:.78rem; background:rgba(12,29,45,.45); }
.cs-caption { color:var(--cs-dim); font-size:.67rem; line-height:1.45; }

h1, h2, h3 { color:var(--cs-text) !important; }
p, li { color:var(--cs-muted); }
a { color:var(--cs-cyan) !important; text-underline-offset:3px; }
code { color:#c9e9f8; font-family:var(--cs-mono); }
hr { border-color:var(--cs-line) !important; }

[data-testid="stSelectbox"] label p, [data-testid="stMultiSelect"] label p,
[data-testid="stSlider"] label p, [data-testid="stNumberInput"] label p,
[data-testid="stToggle"] label p {
  color:var(--cs-muted) !important; font-size:.75rem; }
[data-baseweb="select"] > div { background:var(--cs-panel) !important;
  border-color:var(--cs-line-strong) !important; border-radius:4px !important; }
[data-baseweb="tag"] { background:#163b55 !important; }
.stButton > button { border-radius:4px; background:var(--cs-panel-2); color:var(--cs-text);
  border:1px solid var(--cs-line-strong); min-height:36px; }
.stButton > button:hover { border-color:var(--cs-cyan); color:#e7f7ff; }
*:focus-visible { outline:2px solid var(--cs-cyan) !important; outline-offset:2px; }
::selection { background:#1f6b91; color:white; }

[data-testid="stDataFrame"] { border:1px solid var(--cs-line); border-radius:var(--cs-radius);
  overflow:hidden; }
[data-testid="stPlotlyChart"] { border:0; }
[data-testid="stExpander"] { border:1px solid var(--cs-line); border-radius:var(--cs-radius); }

@media (max-width: 1100px) {
  [data-testid="stMain"] .block-container { padding:1rem 1.1rem 2.5rem; }
  .cs-grid-2, .cs-grid-equal { grid-template-columns:1fr; }
  .cs-topbar { align-items:flex-start; flex-direction:column; }
  .cs-section { flex-direction:column; align-items:flex-start; gap:.2rem; }
  [data-testid="stHorizontalBlock"] { flex-wrap:wrap; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex:1 1 100% !important; min-width:100% !important; width:100% !important; }
}
@media (max-width: 768px) {
  .cs-measurements { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .cs-measure:nth-child(2) { border-right:0; }
  .cs-measure:nth-child(-n+2) { border-bottom:1px solid var(--cs-line); }
  .cs-loop { grid-template-columns:1fr; }
  .cs-loop-step { border-right:0; border-bottom:1px solid var(--cs-line); }
  .cs-loop-step:last-child { border-bottom:0; }
}
@media (max-width: 480px) {
  [data-testid="stMain"] .block-container { padding:.85rem .7rem 2rem; }
  .cs-state-primary { flex-wrap:wrap; gap:.4rem .7rem; }
  .cs-state-primary strong { width:100%; font-size:1.08rem; }
  .cs-state-primary .cs-score { font-size:1.55rem; }
  .cs-measurements { grid-template-columns:1fr; }
  .cs-measure { border-right:0; border-bottom:1px solid var(--cs-line); }
  .cs-measure:last-child { border-bottom:0; }
  .cs-event { grid-template-columns:1fr; gap:.22rem; }
  .cs-kv { grid-template-columns:1fr; }
  .cs-v { text-align:left; padding-top:0; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior:auto !important;
    transition-duration:.01ms !important; animation-duration:.01ms !important; }
}
</style>
"""
