import streamlit as st

import pipeline as pl


@st.cache_data(show_spinner="Loading and joining raw order data (first run only)...")
def load_data():
    orders = pl.load_orders()
    brands_raw = pl.load_brands_raw()
    brands = brands_raw.drop_duplicates(subset=["article_id", "brand"])
    join_result = pl.join_brands(orders, brands)
    return orders, brands_raw, brands, join_result
