import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import pipeline as pl

st.title("Transition windows")

rows = []
for brand, cutover in pl.BRAND_CUTOVERS.items():
    cutover_ts = pd.Timestamp(cutover)
    window_start = cutover_ts - pd.DateOffset(months=12)
    window_end = cutover_ts + pd.DateOffset(months=12)
    rows.append({"brand": brand, "period": "Before (EED1+LVD1+LTD1)", "start": window_start, "end": cutover_ts, "cutover": cutover_ts})
    rows.append({"brand": brand, "period": "After (LVD1 only)", "start": cutover_ts, "end": window_end, "cutover": cutover_ts})

windows_df = pd.DataFrame(rows)

fig = px.timeline(
    windows_df,
    x_start="start",
    x_end="end",
    y="brand",
    color="period",
    color_discrete_map={"Before (EED1+LVD1+LTD1)": pl.COLOR_BLUE, "After (LVD1 only)": pl.COLOR_RED},
)
fig.update_traces(width=0.15, selector=dict(type="bar"))
fig.update_yaxes(categoryorder="array", categoryarray=sorted(pl.BRAND_CUTOVERS.keys(), reverse=True))
fig.update_xaxes(showgrid=True, gridcolor="lightgrey", dtick="M1", tickformat="%b %Y")
fig.update_layout(xaxis_title="Date", yaxis_title="Brand", legend_title=None)

# Cutover marked as a black tick (line-ns marker) at each brand's own row -
# its legend entry sits right next to the Before/After color swatches above.
fig.add_trace(
    go.Scatter(
        x=[pd.Timestamp(c) for c in pl.BRAND_CUTOVERS.values()],
        y=list(pl.BRAND_CUTOVERS.keys()),
        mode="markers",
        marker=dict(symbol="line-ns", size=26, line=dict(width=3, color="black")),
        name="Cutover date",
        showlegend=True,
    )
)

st.plotly_chart(fig, use_container_width=True)

def lv_date(ts: pd.Timestamp) -> str:
    return ts.strftime("%d.%m.%Y.")


st.dataframe(
    pd.DataFrame(
        {
            "brand": list(pl.BRAND_CUTOVERS.keys()),
            "cutover": [lv_date(pd.Timestamp(pl.BRAND_CUTOVERS[b])) for b in pl.BRAND_CUTOVERS],
            "before_window": [
                f"{lv_date(pd.Timestamp(pl.BRAND_CUTOVERS[b]) - pd.DateOffset(months=12))}"
                f"–{lv_date(pd.Timestamp(pl.BRAND_CUTOVERS[b]))}"
                for b in pl.BRAND_CUTOVERS
            ],
            "after_window": [
                f"{lv_date(pd.Timestamp(pl.BRAND_CUTOVERS[b]))}"
                f"–{lv_date(pd.Timestamp(pl.BRAND_CUTOVERS[b]) + pd.DateOffset(months=12))}"
                for b in pl.BRAND_CUTOVERS
            ],
        }
    ),
    use_container_width=True,
    hide_index=True,
)
