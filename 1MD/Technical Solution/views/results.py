import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

import pipeline as pl
from data_access import load_data

orders_df, brands_raw_df, brands_df, join_result = load_data()
matched_df = join_result.matched
summary = pl.compute_all(matched_df)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
ALL_BRANDS = list(pl.BRAND_CUTOVERS.keys())
if "selected_brands" not in st.session_state:
    st.session_state.selected_brands = ALL_BRANDS.copy()


def _select_all_brands():
    st.session_state.selected_brands = ALL_BRANDS.copy()


st.sidebar.header("Filters")
st.sidebar.button("Select all brands", on_click=_select_all_brands, use_container_width=True)
selected_brands = st.sidebar.multiselect("Brands", ALL_BRANDS, key="selected_brands")

visible_rows = summary[summary["brand"].isin(selected_brands + ["All brands combined"])]

if visible_rows.empty:
    st.info("Select at least one brand in the sidebar to see results.")
    st.stop()

# ---------------------------------------------------------------------------
# CSL headline
# ---------------------------------------------------------------------------
st.subheader("CSL before vs. after centralization")
cols = st.columns(len(visible_rows))
for col, (_, row) in zip(cols, visible_rows.iterrows()):
    delta = None
    if row["csl_before"] is not None and row["csl_after"] is not None:
        delta = f"{row['csl_after'] - row['csl_before']:+.1f}%"
    label = row["brand"] if row["brand"] == "All brands combined" else f"Brand {row['brand']}"
    after_display = f"{row['csl_after']:.1f}%" if row["csl_after"] is not None else "n/a"
    col.metric(label, after_display, delta)
    col.caption(f"before: {row['csl_before']:.1f}%" if row["csl_before"] is not None else "before: n/a")

st.plotly_chart(pl.build_csl_chart(visible_rows), use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# CSL over time (monthly trend + brand x month heatmap)
# ---------------------------------------------------------------------------
monthly_df = pl.monthly_csl_by_offset(matched_df)
visible_monthly = monthly_df[monthly_df["brand"].isin(selected_brands)]

st.subheader("Monthly CSL trend, relative to each brand's own cutover")
if visible_monthly.empty:
    st.info("Select at least one individual brand to see the monthly trend (not available for the combined row).")
else:
    st.plotly_chart(pl.build_csl_trend_chart(visible_monthly), use_container_width=True)

st.subheader("CSL heatmap: brand x month")
if visible_monthly.empty:
    st.info("Select at least one individual brand to see the heatmap.")
else:
    st.plotly_chart(pl.build_csl_heatmap(visible_monthly), use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Order fulfillment status breakdown
# ---------------------------------------------------------------------------
st.subheader("Not fully served order lines")
st.plotly_chart(pl.build_fulfillment_chart(visible_rows), use_container_width=True)

st.subheader("Over-delivered order lines")
st.plotly_chart(pl.build_over_delivery_chart(visible_rows), use_container_width=True)

st.subheader("Duplicate order lines")
st.plotly_chart(pl.build_duplicate_chart(visible_rows), use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Unique clients before / after
# ---------------------------------------------------------------------------
st.subheader("Unique clients behind the numbers")
ccols = st.columns(len(visible_rows))
for col, (_, row) in zip(ccols, visible_rows.iterrows()):
    label = row["brand"] if row["brand"] == "All brands combined" else f"Brand {row['brand']}"
    before, after = row["unique_clients_before"], row["unique_clients_after"]
    pct_change = 100 * (after - before) / before if before else None
    delta = f"{pct_change:+.1f}%" if pct_change is not None else None
    col.metric(label, f"{after}", delta)
    col.caption(f"before: {before}")
