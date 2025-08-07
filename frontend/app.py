# frontend/app.py

import httpx
import streamlit as st
from streamlit_tags import st_tags

API_URL = "http://127.0.0.1:8000"


@st.dialog("Edit Position")
def edit_dialog(pos):
    """Show a modal dialog for editing a position."""
    with st.form("edit_dialog_form"):
        symbol = st.text_input("Ticker Symbol", value=pos["symbol"]).upper()
        qty = st.number_input(
            "Quantity", min_value=0.0, step=1.0, format="%.2f", value=pos["quantity"]
        )
        cost = st.number_input(
            "Cost Price",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            value=pos["cost_price"],
        )
        tags = st.text_input("Tags (comma-separated)", value=", ".join(pos["tags"]))
        save_btn = st.form_submit_button("Save")
        cancel_btn = st.form_submit_button("Cancel")

    # “Save” lives here:
    if save_btn:
        # 1) Push to backend
        put_position(
            pos["_id"],
            {
                "symbol": symbol,
                "quantity": qty,
                "cost_price": cost,
                "tags": [t.strip() for t in tags.split(",") if t.strip()],
            },
        )
        st.success(f"Updated {symbol}")
        # 2) Rerun the app; on next run you’ll see new data and dialog will be gone
        st.rerun()

    # “Cancel” also just reruns (closing the dialog with no change)
    if cancel_btn:
        st.info("Edit cancelled")
        st.rerun()


def load_tags():
    r = httpx.get(f"{API_URL}/tags")
    r.raise_for_status()
    return [t["name"] for t in r.json()]


# ── Helper functions ─────────────────────────────────────────────────────────────


def load_positions():
    r = httpx.get(f"{API_URL}/positions")
    r.raise_for_status()
    return r.json()


def load_summary():
    r = httpx.get(f"{API_URL}/positions/summary")
    r.raise_for_status()
    return r.json()


def load_tag_summary():
    """
    Fetch the tag roll-up summary: one row per tag with
    total quantity, total market value, and total unrealized P/L.
    """
    r = httpx.get(f"{API_URL}/positions/tags/summary")
    r.raise_for_status()
    return r.json()


def post_position(data: dict):
    r = httpx.post(f"{API_URL}/positions", json=data)
    r.raise_for_status()
    return r.json()


def put_position(position_id: str, data: dict):
    r = httpx.put(f"{API_URL}/positions/{position_id}", json=data)
    r.raise_for_status()
    return r.json()


def delete_position(position_id: str):
    r = httpx.delete(f"{API_URL}/positions/{position_id}")
    r.raise_for_status()
    return r.json()


# ── Main App ────────────────────────────────────────────────────────────────────


def main():
    st.set_page_config(page_title="Portfolio Dashboard")
    st.title("📊 P. D.")

    # ─── Session state for edit modal ───────────────────────
    if "edit_id" not in st.session_state:
        st.session_state.edit_id = None
    # ─── Session state for tag filter ───────────────────────
    if "filter_tag" not in st.session_state:
        st.session_state.filter_tag = None

    # 1) Add Position form
    with st.expander("➕ Add Position", expanded=True):
        with st.form("add_form"):
            symbol = st.text_input("Ticker Symbol").upper()
            quantity = st.number_input(
                "Quantity", min_value=0.0, step=1.0, format="%.2f"
            )
            cost_price = st.number_input(
                "Cost Price", min_value=0.0, step=0.01, format="%.2f"
            )
            all_tags = load_tags()
            tags = st_tags(
                label="Tags",
                text="Press enter to add tag",
                value=[],
                suggestions=all_tags,
                maxtags=10,
                key="add_tags",
            )
            submitted = st.form_submit_button("Add")
        if submitted:
            data = {
                "symbol": symbol,
                "quantity": quantity,
                "cost_price": cost_price,
                "tags": tags,
            }
            try:
                post_position(data)
                st.success(f"Added {symbol}")
            except Exception as e:
                st.error(f"Error adding position: {e}")

    # 2) Load data
    positions = load_positions()
    summary = load_summary()
    tags_summary = load_tag_summary()

    # 4.5) Tag roll-up summary
    st.subheader("Tag Summary (click to filter)")
    # Render header
    hdr1, hdr2, hdr3, hdr4, _ = st.columns([2, 1, 1, 1, 0.5])
    hdr1.markdown("**Tag**")
    hdr2.markdown("**Qty**")
    hdr3.markdown("**Market Value**")
    hdr4.markdown("**Unrealized P/L**")

    # Render each tag as a button + stats
    for t in tags_summary:
        c0, c1, c2, c3, c4 = st.columns([2, 1, 1, 1, 0.5])
        if c0.button(t["tag"], key=f"filter_{t['tag']}"):
            st.session_state.filter_tag = t["tag"]
        c1.write(t["total_quantity"])
        c2.write(t["total_market_value"])
        c3.write(t["total_unrealized_pl"])
        c4.write("")  # spacer

    # Clear filter
    if st.session_state.filter_tag:
        st.markdown(f"**Filtering by tag:** `{st.session_state.filter_tag}`")
        if st.button("Clear filter"):
            st.session_state.filter_tag = None

    # ─── Filter positions list ───────────────────────────────
    if st.session_state.filter_tag:
        positions = [p for p in positions if st.session_state.filter_tag in p["tags"]]

    st.subheader("Positions")
    # 3) Table header
    cols = st.columns([1, 1, 1, 1, 1, 1, 1])
    headers = [
        "Symbol",
        "Quantity",
        "Cost Price",
        "Current Price",
        "Unrealized P/L",
        "Tags",
        "Actions",
    ]
    for col, header in zip(cols, headers):
        col.markdown(f"**{header}**")

    # 4) Rows with Edit/Delete
    for pos in positions:
        c1, c2, c3, c4, c5, c6, c7 = st.columns([1, 1, 1, 1, 1, 1, 1])
        c1.write(pos["symbol"])
        c2.write(pos["quantity"])
        c3.write(pos["cost_price"])
        c4.write(pos["current_price"])
        c5.write(round(pos["current_price"] - pos["cost_price"], 2))
        badges = " ".join(
            f"<span style='background:#eee;border-radius:4px;padding:2px 6px;margin:2px'>{t}</span>"
            for t in pos["tags"]
        )
        c6.markdown(badges, unsafe_allow_html=True)

        if c7.button("✏️ Edit", key=f"edit_{pos['_id']}"):
            # launch the dialog (which now does its save+rerun internally)
            edit_dialog(pos)

        # Delete button
        if c7.button("🗑️ Delete", key=f"del_{pos['_id']}"):
            confirm_key = f"confirm_delete_{pos['_id']}"
            confirmed = st.checkbox(f"Confirm delete {pos['symbol']}?", key=confirm_key)
            if confirmed:
                try:
                    delete_position(pos["_id"])
                    st.success(f"Deleted {pos['symbol']}")
                except Exception as e:
                    st.error(f"Error deleting: {e}")

    # 5) Totals
    st.subheader("Totals")
    col_mv, col_pl = st.columns(2)
    col_mv.metric("Total Market Value", summary["total_market_value"])
    col_pl.metric("Total Unrealized P/L", summary["total_unrealized_pl"])


if __name__ == "__main__":
    main()
