from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DATA_DIR = Path(__file__).resolve().parent.parent / "Data"
RAW_DIR = DATA_DIR / "raw"
ORDERS_DIR = RAW_DIR / "Raw data for task 2"
BRANDS_PATH = DATA_DIR / "Articles with Brands.xlsx"

WAREHOUSE_FILES = {
    "EED1": "HIST_EE",
    "LVD1": "HIST_LV",
    "LTD1": "HIST_LT",
}
YEARS = (2013, 2014, 2015)

BRAND_CUTOVERS = {
    "A": "2014-03-01",
    "B": "2014-01-01",
    "C": "2014-09-01",
    "D": "2014-07-01",
    "E": "2014-10-01",
}

CENTRAL_WAREHOUSE = "LVD1"
CENTRAL_CLIENTS_OF_LVD1 = {"EED1", "LTD1"}

DUPLICATE_ROW_COLUMNS = ["datetime", "source_warehouse", "client_id", "article_id", "ordered_qty", "delivered_qty"]


RAW_COLUMN_NAMES = {
    "LTD1": ["date", "time", "client_id", "article_id", "ordered_qty", "delivered_qty"],
    "_default": ["datetime", "client_id", "article_id", "ordered_qty", "delivered_qty"],
}


def raw_preview(warehouse: str, year: int, n: int = 5) -> pd.DataFrame:
    """Return the first n rows of a raw file exactly as they look on disk, before any cleaning."""
    prefix = WAREHOUSE_FILES[warehouse]
    path = ORDERS_DIR / f"{prefix}_{year}.csv"
    names = RAW_COLUMN_NAMES.get(warehouse, RAW_COLUMN_NAMES["_default"])
    return pd.read_csv(path, sep=";", header=None, names=names, dtype=str, nrows=n)


def _load_one_file(warehouse: str, year: int) -> pd.DataFrame:
    prefix = WAREHOUSE_FILES[warehouse]
    path = ORDERS_DIR / f"{prefix}_{year}.csv"
    if warehouse == "LTD1":
        raw = pd.read_csv(
            path,
            sep=";",
            header=None,
            names=["date", "time", "client_id", "article_id", "ordered_qty", "delivered_qty"],
            dtype={"client_id": str},
        )
        raw["datetime"] = pd.to_datetime(
            raw["date"] + " " + raw["time"], format="%d.%m.%Y %H:%M:%S"
        )
        raw = raw.drop(columns=["date", "time"])
    else:
        raw = pd.read_csv(
            path,
            sep=";",
            header=None,
            names=["datetime", "client_id", "article_id", "ordered_qty", "delivered_qty"],
            dtype={"client_id": str},
        )
        raw["datetime"] = pd.to_datetime(raw["datetime"], format="%d.%m.%Y %H:%M")

    raw["client_id"] = raw["client_id"].str.strip()
    raw["article_id"] = raw["article_id"].astype(int)
    raw["ordered_qty"] = raw["ordered_qty"].astype(int)
    raw["delivered_qty"] = raw["delivered_qty"].astype(int)
    raw["source_warehouse"] = warehouse
    return raw[
        ["datetime", "source_warehouse", "client_id", "article_id", "ordered_qty", "delivered_qty"]
    ]


def load_orders() -> pd.DataFrame:
    """Load all 9 raw order files and join them into one clean dataframe."""
    frames = [
        _load_one_file(warehouse, year)
        for warehouse in WAREHOUSE_FILES
        for year in YEARS
    ]
    return pd.concat(frames, ignore_index=True)


def load_brands_raw() -> pd.DataFrame:
    """Load the brands file and clean up the column names, duplicates included."""
    brands = pd.read_excel(BRANDS_PATH)
    brands.columns = [c.strip() for c in brands.columns]
    brands = brands.rename(columns={"Article ID": "article_id", "Brand": "brand"})
    brands["brand"] = brands["brand"].str.strip()
    return brands


def load_brands() -> pd.DataFrame:
    return load_brands_raw().drop_duplicates(subset=["article_id", "brand"])


@dataclass
class JoinResult:
    matched: pd.DataFrame
    unmatched_sample: pd.DataFrame
    unmatched_article_count: int
    unmatched_row_count: int
    unmatched_ordered_qty: int


def join_brands(orders: pd.DataFrame, brands: pd.DataFrame) -> JoinResult:
    merged = orders.merge(brands, on="article_id", how="left")
    unmatched = merged[merged["brand"].isna()]
    matched = merged[merged["brand"].notna()].copy()
    return JoinResult(
        matched=matched,
        unmatched_sample=unmatched.drop(columns=["brand"]).head(5),
        unmatched_article_count=unmatched["article_id"].nunique(),
        unmatched_row_count=len(unmatched),
        unmatched_ordered_qty=int(unmatched["ordered_qty"].sum()),
    )


def _window_totals(df: pd.DataFrame) -> tuple[int, int]:
    return int(df["ordered_qty"].sum()), int(df["delivered_qty"].sum())


def brand_window_frames(df: pd.DataFrame, brand: str, cutover: str):
    """Split one brand's rows into the before window and the after window around its cutover date."""
    cutover_ts = pd.Timestamp(cutover)
    window_start = cutover_ts - pd.DateOffset(months=12)
    window_end = cutover_ts + pd.DateOffset(months=12)

    brand_df = df[df["brand"] == brand]

    before_all = brand_df[(brand_df["datetime"] >= window_start) & (brand_df["datetime"] < cutover_ts)]
    before_contaminated = before_all[
        (before_all["source_warehouse"] == CENTRAL_WAREHOUSE)
        & (before_all["client_id"].isin(CENTRAL_CLIENTS_OF_LVD1))
    ]
    before_df = before_all.drop(before_contaminated.index)

    after_all = brand_df[(brand_df["datetime"] >= cutover_ts) & (brand_df["datetime"] < window_end)]
    after_df = after_all[after_all["source_warehouse"] == CENTRAL_WAREHOUSE]

    return before_df, after_df, before_contaminated


def _fulfillment_counts(df: pd.DataFrame) -> tuple[int, int, int, int, int]:
    """Count rows as over delivered, exactly served, partially served or zero delivered."""
    total = len(df)
    zero = int((df["delivered_qty"] == 0).sum())
    over = int((df["delivered_qty"] > df["ordered_qty"]).sum())
    exact = int(((df["delivered_qty"] == df["ordered_qty"]) & (df["delivered_qty"] > 0)).sum())
    partial = total - zero - over - exact
    return total, over, exact, partial, zero


def _duplicate_row_count(df: pd.DataFrame) -> int:
    return len(df) - len(df.drop_duplicates(subset=DUPLICATE_ROW_COLUMNS))


def _summarize(brand: str, cutover: str, before_df: pd.DataFrame, after_df: pd.DataFrame, excluded_before_rows: int) -> dict:
    ordered_before, delivered_before = _window_totals(before_df)
    ordered_after, delivered_after = _window_totals(after_df)
    rows_before, over_before, exact_before, partial_before, zero_before = _fulfillment_counts(before_df)
    rows_after, over_after, exact_after, partial_after, zero_after = _fulfillment_counts(after_df)
    dup_rows_before = _duplicate_row_count(before_df)
    dup_rows_after = _duplicate_row_count(after_df)

    return {
        "brand": brand,
        "cutover": cutover,
        "ordered_before": ordered_before,
        "delivered_before": delivered_before,
        "csl_before": 100 * delivered_before / ordered_before if ordered_before else None,
        "ordered_after": ordered_after,
        "delivered_after": delivered_after,
        "csl_after": 100 * delivered_after / ordered_after if ordered_after else None,
        "excluded_before_rows": excluded_before_rows,
        "rows_before": rows_before,
        "over_rows_before": over_before,
        "exact_rows_before": exact_before,
        "partial_rows_before": partial_before,
        "zero_rows_before": zero_before,
        "rows_after": rows_after,
        "over_rows_after": over_after,
        "exact_rows_after": exact_after,
        "partial_rows_after": partial_after,
        "zero_rows_after": zero_after,
        "over_pct_before": 100 * over_before / rows_before if rows_before else 0.0,
        "over_pct_after": 100 * over_after / rows_after if rows_after else 0.0,
        "not_fully_served_pct_before": 100 * (partial_before + zero_before) / rows_before if rows_before else 0.0,
        "not_fully_served_pct_after": 100 * (partial_after + zero_after) / rows_after if rows_after else 0.0,
        "dup_rows_before": dup_rows_before,
        "dup_rows_after": dup_rows_after,
        "dup_pct_before": 100 * dup_rows_before / rows_before if rows_before else 0.0,
        "dup_pct_after": 100 * dup_rows_after / rows_after if rows_after else 0.0,
        "unique_clients_before": before_df["client_id"].nunique(),
        "unique_clients_after": after_df["client_id"].nunique(),
    }


def compute_brand_csl(df: pd.DataFrame, brand: str, cutover: str) -> dict:
    before_df, after_df, before_contaminated = brand_window_frames(df, brand, cutover)
    return _summarize(brand, cutover, before_df, after_df, len(before_contaminated))


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    before_frames, after_frames, rows = [], [], []
    for brand, cutover in BRAND_CUTOVERS.items():
        before_df, after_df, excluded_df = brand_window_frames(df, brand, cutover)
        before_frames.append(before_df)
        after_frames.append(after_df)
        rows.append(_summarize(brand, cutover, before_df, after_df, len(excluded_df)))

    combined_before = pd.concat(before_frames, ignore_index=True)
    combined_after = pd.concat(after_frames, ignore_index=True)
    combined = _summarize(
        "All brands combined",
        "-",
        combined_before,
        combined_after,
        sum(r["excluded_before_rows"] for r in rows),
    )
    rows.append(combined)
    return pd.DataFrame(rows)


def duplicate_and_anomaly_by_year(orders: pd.DataFrame) -> pd.DataFrame:
    """Count duplicate rows and over delivered rows for each warehouse and year."""
    df = orders.copy()
    df["year"] = df["datetime"].dt.year

    rows = []
    for (warehouse, year), group in df.groupby(["source_warehouse", "year"]):
        total = len(group)
        duplicate_rows = _duplicate_row_count(group)
        over_delivered_rows = int((group["delivered_qty"] > group["ordered_qty"]).sum())
        rows.append(
            {
                "source_warehouse": warehouse,
                "year": int(year),
                "total_rows": total,
                "duplicate_rows": duplicate_rows,
                "duplicate_pct": 100 * duplicate_rows / total if total else 0.0,
                "delivered_gt_ordered_rows": over_delivered_rows,
                "delivered_gt_ordered_pct": 100 * over_delivered_rows / total if total else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["source_warehouse", "year"]).reset_index(drop=True)

COLOR_RED = "#D92534"
COLOR_BLUE = "#2072B2"
COLOR_GREEN = "#0B8C50"
COLOR_YELLOW = "#F2E30F"
COLOR_ORANGE = "#F28322"

PERIOD_COLORS = {"Before": COLOR_BLUE, "After": COLOR_RED}


def build_csl_chart(summary: pd.DataFrame):
    """Make a bar chart comparing CSL before and after for each brand."""
    chart_df = summary.melt(
        id_vars=["brand"],
        value_vars=["csl_before", "csl_after"],
        var_name="period",
        value_name="csl",
    )
    chart_df["period"] = chart_df["period"].map({"csl_before": "Before", "csl_after": "After"})
    fig = px.bar(
        chart_df,
        x="brand",
        y="csl",
        color="period",
        barmode="group",
        category_orders={"period": ["Before", "After"]},
        color_discrete_map=PERIOD_COLORS,
        labels={"csl": "CSL (%)", "brand": "Brand"},
        text_auto=".1f",
    )
    fig.update_layout(yaxis_range=[0, max(100, chart_df["csl"].max() * 1.1)])
    return fig


def build_fulfillment_chart(summary: pd.DataFrame):
    """Make a bar chart showing how many order lines were not fully served."""
    return _build_anomaly_rate_chart(
        summary, "not_fully_served_pct_before", "not_fully_served_pct_after", "Not fully served order lines (%)"
    )


def _build_anomaly_rate_chart(summary: pd.DataFrame, before_col: str, after_col: str, y_label: str, decimals: int = 2):
    """Make the shared bar chart style used by all the percentage based charts."""
    chart_df = summary.melt(
        id_vars=["brand"],
        value_vars=[before_col, after_col],
        var_name="period",
        value_name="pct",
    )
    chart_df["period"] = chart_df["period"].map({before_col: "Before", after_col: "After"})
    fig = px.bar(
        chart_df,
        x="brand",
        y="pct",
        color="period",
        barmode="group",
        category_orders={"period": ["Before", "After"]},
        color_discrete_map=PERIOD_COLORS,
        labels={"pct": y_label, "brand": "Brand"},
    )
    fig.update_traces(texttemplate=f"%{{y:.{decimals}f}}")
    return fig


def build_over_delivery_chart(summary: pd.DataFrame):
    """Make a bar chart showing how many order lines were over delivered."""
    return _build_anomaly_rate_chart(
        summary, "over_pct_before", "over_pct_after", "Over-delivered order lines (%)", decimals=4
    )


def build_duplicate_chart(summary: pd.DataFrame):
    """Make a bar chart showing how many order lines are exact duplicates."""
    return _build_anomaly_rate_chart(
        summary, "dup_pct_before", "dup_pct_after", "Duplicate order lines (%)"
    )


def monthly_csl_by_offset(df: pd.DataFrame) -> pd.DataFrame:
    """Compute CSL for each month, counted relative to each brand's own cutover month."""
    rows = []
    for brand, cutover in BRAND_CUTOVERS.items():
        cutover_period = pd.Timestamp(cutover).to_period("M")
        before_df, after_df, _ = brand_window_frames(df, brand, cutover)
        combined = pd.concat([before_df, after_df])
        if combined.empty:
            continue
        grouped = combined.groupby(combined["datetime"].dt.to_period("M")).agg(
            ordered=("ordered_qty", "sum"), delivered=("delivered_qty", "sum")
        )
        for month_period, row in grouped.iterrows():
            offset = (month_period.year - cutover_period.year) * 12 + (month_period.month - cutover_period.month)
            rows.append(
                {
                    "brand": brand,
                    "month": month_period.to_timestamp(),
                    "month_offset": offset,
                    "ordered": int(row["ordered"]),
                    "delivered": int(row["delivered"]),
                    "csl": 100 * row["delivered"] / row["ordered"] if row["ordered"] else None,
                }
            )
    return pd.DataFrame(rows)


def build_csl_trend_chart(monthly_df: pd.DataFrame):
    """Make a line chart of CSL over time for each brand, relative to its own cutover month."""
    plot_df = monthly_df.sort_values(["brand", "month_offset"]).copy()
    plot_df["month_label"] = plot_df["month"].dt.strftime("%B %Y")
    fig = px.line(
        plot_df,
        x="month_offset",
        y="csl",
        color="brand",
        markers=True,
        custom_data=["month_label"],
        labels={"month_offset": "Months relative to cutover (0 = cutover month)", "csl": "CSL (%)"},
    )
    fig.update_traces(
        hovertemplate="Brand %{fullData.name}<br>%{customdata[0]}<br>CSL: %{y:.1f}%<extra></extra>"
    )
    fig.add_vline(x=-0.5, line_dash="dash", line_color=COLOR_RED)
    fig.add_annotation(x=-0.5, y=1.05, yref="paper", showarrow=False, text="Cutover", font=dict(color=COLOR_RED))
    return fig


def build_csl_heatmap(monthly_df: pd.DataFrame):
    """Make a heatmap of CSL by brand and month, relative to each brand's own cutover month."""
    pivot = monthly_df.pivot(index="brand", columns="month_offset", values="csl")
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)
    month_labels = monthly_df.pivot(index="brand", columns="month_offset", values="month")
    month_labels = month_labels.reindex(sorted(month_labels.columns), axis=1)
    month_labels = month_labels.apply(lambda col: col.dt.strftime("%B %Y"))

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            customdata=month_labels.values,
            colorscale=[[0, COLOR_RED], [0.5, COLOR_YELLOW], [1, COLOR_GREEN]],
            text=pivot.values,
            texttemplate="%{text:.0f}",
            hovertemplate="Brand %{y}<br>%{customdata}<br>CSL: %{z:.1f}%<extra></extra>",
            colorbar=dict(title="CSL (%)"),
        )
    )
    fig.update_xaxes(title="Months relative to cutover (0 = cutover month)")
    fig.update_yaxes(title="Brand")
    fig.add_vline(x=-0.5, line_dash="dash", line_color="black")
    return fig


def load_and_prepare() -> tuple[pd.DataFrame, JoinResult]:
    """Load, clean and join the raw data, ready for the CSL calculations."""
    orders = load_orders()
    brands = load_brands()
    join_result = join_brands(orders, brands)
    return orders, join_result
