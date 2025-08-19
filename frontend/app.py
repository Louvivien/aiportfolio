# frontend/app.py

from __future__ import annotations

import httpx
import streamlit as st
from streamlit_tags import st_tags

API_URL = "http://127.0.0.1:8000"


def fmt2(x) -> str:
    try:
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def parse_price(s: str | float | None) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = s.strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── Tiny helper: longer timeout + friendly messaging ───────────────────────────
def call_api(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    timeout: float = 20.0,  # bump default timeout
):
    """
    Make an HTTP request to the backend with a longer timeout.
    If the backend is slow/unavailable, show a friendly message and stop the app.
    """
    url = f"{API_URL}{path}"
    try:
        r = httpx.request(method, url, json=json, params=params, timeout=timeout)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        return r.json() if "application/json" in ctype else r.text
    except httpx.TimeoutException:
        st.warning("⏳ Backend is taking longer than usual. Try again in a few seconds.")
        st.stop()  # prevent the rest of the script from erroring
    except httpx.HTTPError as e:
        st.error(f"API error while calling `{path}`: {e}")
        st.stop()


# ── Edit dialog ────────────────────────────────────────────────────────────────
@st.dialog("Edit Position")
def edit_dialog(pos):
    """Show a modal dialog for editing a position."""
    with st.form("edit_dialog_form"):
        symbol = st.text_input("Ticker Symbol", value=pos["symbol"]).upper()
        qty = st.number_input(
            "Quantity",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            value=float(pos["quantity"]),
        )
        cost = st.number_input(
            "Cost Price",
            min_value=0.0,
            step=0.01,
            format="%.2f",
            value=float(pos["cost_price"]),
        )

        is_closed = st.checkbox("Closed", value=bool(pos.get("is_closed", False)))

        closing_price = None
        if is_closed:
            cp_default = pos.get("closing_price")
            cp_default_txt = "" if cp_default is None else fmt2(cp_default)
            closing_price_txt = st.text_input(
                "Closing Price",
                value=cp_default_txt,
                help="You can type 28,09 or 28.09",
            )
            closing_price = parse_price(closing_price_txt)

        tags_text = ", ".join(pos.get("tags", []))
        tags = st.text_input("Tags (comma-separated)", value=tags_text)

        save_btn = st.form_submit_button("Save")
        cancel_btn = st.form_submit_button("Cancel")

    if save_btn:
        # Push to backend, then rerun to refresh table and close dialog
        call_api(
            "PUT",
            f"/positions/{pos['_id']}",
            json={
                "symbol": symbol,
                "quantity": qty,
                "cost_price": cost,
                "tags": [t.strip() for t in tags.split(",") if t.strip()],
                "is_closed": is_closed,
                "closing_price": (closing_price if is_closed else None),
            },
        )
        st.success(f"Updated {symbol}")
        st.rerun()

    if cancel_btn:
        st.info("Edit cancelled")
        st.rerun()


# ── API wrappers using the helper ──────────────────────────────────────────────
def load_tags():
    return call_api("GET", "/tags")


def load_positions():
    return call_api("GET", "/positions")


def load_summary():
    return call_api("GET", "/positions/summary")


def load_tag_summary():
    """
    Fetch the tag roll-up summary: one row per tag with
    total market value and total unrealized P/L.
    """
    return call_api("GET", "/positions/tags/summary")


def post_position(data: dict):
    return call_api("POST", "/positions", json=data)


def put_position(position_id: str, data: dict):
    return call_api("PUT", f"/positions/{position_id}", json=data)


def delete_position(position_id: str):
    return call_api("DELETE", f"/positions/{position_id}")


# ── Main App ───────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Portfolio Dashboard")
    st.title("📊 Portfolio Dashboard")

    # session state
    if "filter_tag" not in st.session_state:
        st.session_state.filter_tag = None

    # 1) Add Position form
    with st.expander("➕ Add Position", expanded=True):
        # put the toggle OUTSIDE so the UI re-runs instantly when toggled
        add_is_closed = st.checkbox("Mark as closed?", key="add_is_closed")

        with st.form("add_form"):
            symbol = st.text_input("Ticker Symbol").upper()
            quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
            cost_price = st.number_input("Cost Price", min_value=0.0, step=0.01, format="%.2f")

            # show a TEXT input so we can accept "28,09" or "28.09"
            add_closing_price_txt = None
            if add_is_closed:
                add_closing_price_txt = st.text_input(
                    "Closing Price", help="You can type 28,09 or 28.09"
                )

            tag_models = load_tags()
            tag_suggestions = [t.get("name", "") for t in tag_models if t.get("name")]
            tags = st_tags(
                label="Tags",
                text="Press enter to add tag",
                value=[],
                suggestions=tag_suggestions,
                maxtags=10,
                key="add_tags",
            )

            submitted = st.form_submit_button("Add")

        if submitted:
            closing_price_val = parse_price(add_closing_price_txt) if add_is_closed else None
            data = {
                "symbol": symbol,
                "quantity": quantity,
                "cost_price": cost_price,
                "tags": tags,
                "is_closed": bool(add_is_closed),
                "closing_price": closing_price_val,
            }
            post_position(data)
            st.success(f"Added {symbol}")
            st.rerun()

    # 2) Load data (will show friendly message if slow)
    positions = load_positions()
    summary = load_summary()
    tags_summary = load_tag_summary()

    # 3) Tag roll-up summary
    st.subheader("Tag Summary (click to filter)")

    # Header
    hdr_tag, hdr_mv, hdr_pl, _ = st.columns([2, 1, 1, 0.5])
    hdr_tag.markdown("**Tag**")
    hdr_mv.markdown("**Market Value**")
    hdr_pl.markdown("**Unrealized P/L**")

    # Rows
    for t in tags_summary:
        c_tag, c_mv, c_pl, c_sp = st.columns([2, 1, 1, 0.5])
        if c_tag.button(t["tag"], key=f"filter_{t['tag']}"):
            st.session_state.filter_tag = t["tag"]
        c_mv.write(fmt2(t.get("total_market_value", 0.0)))
        c_pl.write(fmt2(t.get("total_unrealized_pl", 0.0)))
        c_sp.write("")

    if st.session_state.filter_tag:
        st.markdown(f"**Filtering by tag:** `{st.session_state.filter_tag}`")
        if st.button("Clear filter"):
            st.session_state.filter_tag = None
            st.rerun()

    # Apply filter to positions
    if st.session_state.filter_tag:
        positions = [p for p in positions if st.session_state.filter_tag in p.get("tags", [])]

    # 4) Positions table
    st.subheader("Positions")

    # Columns: Symbol (with link) | Name | Qty | Cost | Current | Invest | Current Value | P/L | Tags | Actions
    cols = st.columns([1.0, 1.7, 0.8, 0.9, 1.0, 1.0, 1.2, 1.0, 1.4, 1.0])
    headers = [
        "Symbol",
        "Name",
        "Quantity",
        "Cost Price",
        "Current Price",
        "Invest",
        "Current Value",
        "+/− Value",
        "Tags",
        "Actions",
    ]
    for col, header in zip(cols, headers):
        col.markdown(f"**{header}**")

    for pos in positions:
        # Effective current price: closing price if closed, else API current price
        is_closed = bool(pos.get("is_closed"))
        effective_price = float(
            pos.get("closing_price")
            if (is_closed and pos.get("closing_price") is not None)
            else pos.get("current_price", 0.0)
        )

        qty = float(pos.get("quantity", 0.0))
        cost = float(pos.get("cost_price", 0.0))
        invest = qty * cost
        current_value = qty * effective_price
        pnl_value = current_value - invest

        c1, cname, cqty, ccost, ccurr, cinv, cval, cpnl, ctags, cact = st.columns(
            [1.0, 1.7, 0.8, 0.9, 1.0, 1.0, 1.2, 1.0, 1.4, 1.0]
        )

        # Symbol with Yahoo Finance link + closed badge
        closed_badge = (
            " <span style='background:#666;color:#fff;border-radius:4px;padding:2px 6px;"
            "margin-left:4px;font-size:0.8em'>Closed</span>"
            if is_closed
            else ""
        )
        sym_link = f"[{pos['symbol']}](https://finance.yahoo.com/quote/{pos['symbol']})"
        c1.markdown(sym_link + closed_badge, unsafe_allow_html=True)

        # Name (long_name from backend if available)
        long_name = pos.get("long_name") or ""
        cname.write(long_name)

        cqty.write(fmt2(qty))
        ccost.write(fmt2(cost))
        ccurr.write(fmt2(effective_price))
        cinv.write(fmt2(invest))
        cval.write(fmt2(current_value))
        cpnl.write(fmt2(pnl_value))

        # Tags
        badges = " ".join(
            f"<span style='background:#eee;border-radius:4px;padding:2px 6px;margin:2px'>{t}</span>"
            for t in pos.get("tags", [])
        )
        ctags.markdown(badges, unsafe_allow_html=True)

        # Actions
        if cact.button("✏️ Edit", key=f"edit_{pos['_id']}"):
            edit_dialog(pos)  # dialog handles its own save + rerun

        if cact.button("🗑️ Delete", key=f"del_{pos['_id']}"):
            try:
                delete_position(pos["_id"])
                st.success(f"Deleted {pos['symbol']}")
                st.rerun()  # refresh table right away
            except Exception as e:
                st.error(f"Error deleting: {e}")

    # 5) Totals
    st.subheader("Totals")
    col_mv, col_pl = st.columns(2)
    col_mv.metric("Total Market Value", fmt2(summary.get("total_market_value", 0.0)))
    col_pl.metric("Total Unrealized P/L", fmt2(summary.get("total_unrealized_pl", 0.0)))


if __name__ == "__main__":
    main()
