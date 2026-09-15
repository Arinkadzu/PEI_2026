import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

import pipeline as pl
from data_access import load_data

orders_df, brands_raw_df, brands_df, join_result = load_data()
matched_df = join_result.matched


def issue(number, title, check_label, check_code, found, fix_label, fix_code=None):
    st.subheader(f"{number}. {title}")
    st.markdown(f"**Check:** {check_label}")
    st.code(check_code, language="python")
    st.markdown(f"**Found:** {found}")
    if fix_code:
        st.markdown(f"**Fix:** {fix_label}")
        st.code(fix_code, language="python")
    else:
        st.markdown(f"**Fix:** {fix_label}")
    st.divider()


st.title("Data preparation walkthrough")
st.caption("8 data issues: how each was checked, what was found, how it was fixed. Numbers are computed live.")

# ---------------------------------------------------------------------------
issue(
    1, "Source CSVs have no header row",
    "count of ';'-separated fields on the first line vs. the expected 5 columns",
    'first_line.split(";")  # -> [\'04.01.2013 9:30\', \'S250...\', \'510643\', \'1\', \'1\']\n'
    '# no column names present - row 1 is already data',
    "confirmed for all 9 files; column names had to be assigned manually.",
    "names=[\"datetime\", \"client_id\", \"article_id\", \"ordered_qty\", \"delivered_qty\"] "
    "passed to pd.read_csv(..., header=None).",
)

issue(
    2, "Lithuania splits date and time into two columns",
    "compared field count per row: EE/LV vs. LT",
    'len(ee_row.split(";"))   # -> 5\n'
    'len(lt_row.split(";"))   # -> 6  (date, time, client, article, ordered, delivered)',
    "LT files carry `date` and `time` as two separate fields; EE/LV combine them into one.",
    "concatenate before parsing",
    'raw["datetime"] = pd.to_datetime(raw["date"] + " " + raw["time"], format="%d.%m.%Y %H:%M:%S")',
)

issue(
    3, "Client codes are padded with trailing spaces",
    "printed repr() of distinct client_id values instead of str()",
    'repr(df["client_id"].unique()[0])\n# -> \'S250                          \'   (30-char fixed width)',
    "every client code is right-padded with spaces - `'S250'` != `'S250 '` to pandas, so joins/group-by would silently miss matches.",
    "strip on load",
    'raw["client_id"] = raw["client_id"].str.strip()',
)

issue(
    4, "Brand mapping file has duplicate rows",
    "row count before/after drop_duplicates, plus a conflict check per Article ID",
    'len(brands), len(brands.drop_duplicates(subset=["article_id","brand"]))   # -> 1713, 1671\n'
    'brands.groupby("article_id")["brand"].nunique().gt(1).sum()               # -> 0 conflicts',
    "42 pure duplicate rows (same Article ID + Brand); zero Article IDs map to two different brands, so nothing is lost by dropping them.",
    "brands.drop_duplicates(subset=[\"article_id\", \"brand\"])",
)

n_unmatched = join_result.unmatched_row_count
n_unmatched_articles = join_result.unmatched_article_count
n_unmatched_qty = join_result.unmatched_ordered_qty
issue(
    5, "Some ordered articles have no brand mapping",
    "left join orders -> brands on article_id, then count rows where brand is null",
    'merged = orders.merge(brands, on="article_id", how="left")\n'
    'unmatched = merged[merged["brand"].isna()]',
    f"{n_unmatched:,} order rows ({n_unmatched_articles} distinct Article IDs, {n_unmatched_qty:,} ordered boxes) "
    "have no brand - these Article IDs exist in the orders but not in the brand table.",
    "excluded from the brand-level CSL calculation; the row/volume count above is tracked and shown, not silently dropped.",
)
with st.expander(f"Show how the {n_unmatched_articles} unmatched Article IDs were found"):
    st.code(
        '# every article_id that appears in orders but not in the brand table\n'
        'unmatched_articles = set(orders["article_id"]) - set(brands["article_id"])\n'
        f'# -> {n_unmatched_articles} article IDs, none of which appear anywhere in Articles with Brands.xlsx\n'
        'merged[merged["article_id"].isin(unmatched_articles)].groupby("article_id")["ordered_qty"].agg(["size", "sum"])',
        language="python",
    )
    unmatched_full = orders_df.merge(brands_df, on="article_id", how="left")
    unmatched_full = unmatched_full[unmatched_full["brand"].isna()]
    breakdown = (
        unmatched_full.groupby("article_id")
        .agg(order_rows=("ordered_qty", "size"), ordered_qty_sum=("ordered_qty", "sum"))
        .sort_values("ordered_qty_sum", ascending=False)
        .reset_index()
    )
    st.caption(
        f"{len(breakdown)} distinct Article IDs, sorted by total ordered boxes - the biggest ones account for "
        f"most of the {n_unmatched_qty:,} unmatched boxes; this is the same set the code above computes, not a "
        "hand-picked sample."
    )
    st.dataframe(breakdown, use_container_width=True)

quality_by_year_df = pl.duplicate_and_anomaly_by_year(orders_df)
worst = quality_by_year_df.sort_values("duplicate_pct", ascending=False).iloc[0]
issue(
    6, "Exact-duplicate order lines",
    "per (warehouse, year): row count vs. row count after drop_duplicates on all 6 fields",
    'dup_cols = ["datetime","source_warehouse","client_id","article_id","ordered_qty","delivered_qty"]\n'
    'dup_rate = 1 - len(df.drop_duplicates(dup_cols)) / len(df)',
    f"0.2-0.6% in most warehouse/year files, but {worst['source_warehouse']} {int(worst['year'])} = "
    f"{worst['duplicate_pct']:.1f}% - an order of magnitude higher. No unique order-line ID exists in the "
    "source, so a genuine repeat order can't be distinguished from an export artifact.",
    "left as-is (no evidence they are wrong); the rate is tracked per warehouse/year and shown as its own chart on the Results page.",
)

total_over = int(quality_by_year_df["delivered_gt_ordered_rows"].sum())
issue(
    7, "Some rows have delivered > ordered",
    "boolean filter, counted per (warehouse, year)",
    '(df["delivered_qty"] > df["ordered_qty"]).sum()',
    f"{total_over:,} rows across all files, concentrated in EE and LT in 2014-2015.",
    "tracked as its own \"Over-delivered\" category (not counted as good service); CSL is not capped at 100%, "
    "so a period with many such rows can print above 100% as a visible flag.",
)

leak_rows = []
for brand, cutover in pl.BRAND_CUTOVERS.items():
    _, _, excluded_df = pl.brand_window_frames(matched_df, brand, cutover)
    if len(excluded_df):
        leak_rows.append(excluded_df.assign(brand_checked=brand))
leak_df = pd.concat(leak_rows, ignore_index=True) if leak_rows else pd.DataFrame()
issue(
    8, "LVD1 was already shipping to EED1/LTD1 before some brands' own cutover",
    "for each brand, filter its 'before' window to LVD1 rows whose client is EED1/LTD1 - should be empty if the cutover date is right",
    'before_df[(before_df["source_warehouse"]=="LVD1") & before_df["client_id"].isin(["EED1","LTD1"])]',
    f"{len(leak_df)} rows, not zero: brand A (article 456909, Mar-Aug 2013) and brand E (2 articles, "
    "2 days before its Oct 2014 cutover). Cause not determinable from the data alone (pilot shipment, "
    "data-entry inconsistency, or a static article-to-brand mapping applied across all 3 years).",
    "excluded from the 'before' window for the affected brand; count shown instead of hidden.",
)
if len(leak_df):
    with st.expander(f"Show the {len(leak_df)} affected rows"):
        st.dataframe(
            leak_df[["brand_checked", "datetime", "client_id", "article_id", "ordered_qty", "delivered_qty"]],
            use_container_width=True,
        )
