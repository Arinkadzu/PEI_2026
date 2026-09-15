# Technical Solution — CSL Centralization Analysis

Streamlit app that reproduces the Customer Service Level (CSL) analysis from
raw source data (`../Data/raw/Raw data for task 2/` and
`../Data/Articles with Brands.xlsx`) with no manual steps or hardcoded results.

## Setup

```
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

## Run

```
streamlit run app.py
```

Three pages, navigated from the top of the sidebar (above the filters):
**Results** (CSL numbers, charts, data-quality stats, brand filter),
**Data preparation** (8 data issues, each as Check / Found / Fix with the
actual pandas code behind it), and **Transition windows** (visualizes each
brand's before/after cutover window). `app.py` only wires up the navigation;
the page content lives in `views/`.

The loaded/cleaned dataset is cached for the session
(`@st.cache_data` in `data_access.py`), so it's only read and joined once
regardless of which page is opened first.

