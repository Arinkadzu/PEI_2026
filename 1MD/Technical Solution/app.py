import streamlit as st

st.set_page_config(page_title="CSL Centralization Analysis", layout="wide")

pg = st.navigation(
    [
        st.Page("views/results.py", title="Results", icon="📊", default=True),
        st.Page("views/data_preparation.py", title="Data preparation", icon="🧹"),
        st.Page("views/transition_windows.py", title="Transition windows", icon="🕒"),
    ]
)
pg.run()
