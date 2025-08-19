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


def call_api(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    timeout: float = 20.0,
):
    url = f"{API_URL}{path}"
    try:
        r = httpx.request(method, url, json=json, params=params, timeout=timeout)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        return r.json() if "application/json" in ctype else r.text
    except httpx.TimeoutException:
        st.warning("⏳ Backend is taking longer than usual. Try again in a few seconds.")
        st.stop()
    except httpx.HTTPError as e:
        st.error(f"API error while calling `{path}`: {e}")
        st.stop()


@st.dialog("Edit Position")
def edit_dialog(pos):
    with st.form("edit_dialog_form"):
        symbol = st.text_input("Ticker Symbol", value=pos["symbol"]).upper()
        qty = st.number_input(
            "Quantity", min_value=0.0, step=1.0, format="%.2f", value=float(pos["quantity"])
        )
        cost = st.number_input(
            "Cost Price", min_value=0.0, step=0.01, format="%.2f", value=float(pos["cost_price"])
        )

        is_closed = st.checkbox("Closed", value=bool(pos.get("is_closed", False)))

        closing_price = None
        if is_closed:
            cp_default = pos.get("closing_price")
            cp_default_txt = "" if cp_default is None else fmt2(cp_default)
            closing_price_txt = st.text_input(
                "Closing Price", value=cp_default_txt, help="You can type 28,09 or 28.09"
            )
            closing_price = parse_price(closing_price_txt)

        tags_text = ", ".join(pos.get("tags", []))
        tags = st.text_input("Tags (comma-separated)", value=tags_text)

        save_btn = st.form_submit_button("Save")
        cancel_btn = st.form_submit_button("Cancel")

    if save_btn:
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


def load_tags():
    return call_api("GET", "/tags")


def load_positions():
    return call_api("GET", "/positions")


def load_summary():
    return call_api("GET", "/positions/summary")


def load_tag_summary():
    return call_api("GET", "/positions/tags/summary")


def post_position(data: dict):
    return call_api("POST", "/positions", json=data)


def delete_position(position_id: str):
    return call_api("DELETE", f"/positions/{position_id}")


def main():
    st.set_page_config(page_title="Portfolio Dashboard", layout="wide")
    st.title("📊 Portfolio Dashboard")

    st.markdown(
        """
        <style>
        .cell { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2rem; }
        .cell-wrap {
            white-space: normal; overflow: hidden;
            display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;  /* 2 lines */
            line-height: 1.2rem; max-height: calc(1.2rem * 2);
        }
        .tag-badge { background:#eee; border-radius:4px; padding:2px 6px; margin:0 2px; display:inline-block; }
        .status-badge { font-size:0.9em; margin-left:6px; }
        .pos-green { color: #0a0; }
        .pos-red { color: #c00; }
        .muted { color: #666; }
        .actions-col div[data-testid="column"] > div { display: flex; gap: 6px; }

        /* Reduce or remove Streamlit default padding and margins */
        .block-container {
            padding-top: 0rem !important;
            padding-bottom: 1rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100% !important;
        }
        .main {
            padding-left: 0rem;
            padding-right: 0rem;
        }
        header {visibility: hidden;}  /* hides Streamlit's default header space */
    </style>
        """,
        unsafe_allow_html=True,
    )

    if "filter_tag" not in st.session_state:
        st.session_state.filter_tag = None

    with st.expander("➕ Add Position", expanded=True):
        add_is_closed = st.checkbox("Mark as closed?", key="add_is_closed")

        with st.form("add_form"):
            symbol = st.text_input("Ticker Symbol").upper()
            quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
            cost_price = st.number_input("Cost Price", min_value=0.0, step=0.01, format="%.2f")

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

    positions = load_positions()
    summary = load_summary()
    tags_summary = load_tag_summary()

    st.subheader("Tag Summary (click to filter)")
    hdr_tag, hdr_mv, hdr_pl, _ = st.columns([2.2, 1.2, 1.2, 0.4])
    hdr_tag.markdown("**Tag**")
    hdr_mv.markdown("**Market Value**")
    hdr_pl.markdown("**Unrealized P/L**")

    for t in tags_summary:
        c_tag, c_mv, c_pl, c_sp = st.columns([2.2, 1.2, 1.2, 0.4])
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

    if st.session_state.filter_tag:
        positions = [p for p in positions if st.session_state.filter_tag in p.get("tags", [])]

    st.subheader("Positions")

    # Columns: Symbol | Name | Qty | Cost | Current | Invest | Value | P/L | Intraday | % | Tags | Actions
    col_layout = [1.1, 3.2, 0.9, 1.0, 1.1, 1.1, 1.3, 1.1, 1.0, 1.0, 1.6, 0.7]
    cols = st.columns(col_layout)
    headers = [
        "Symbol",
        "Name",
        "Qty",
        "Cost",
        "Current",
        "Invest",
        "Value",
        "P/L",
        "Intraday",
        "%",
        "Tags",
        "",
    ]
    for col, header in zip(cols, headers):
        col.markdown(f"**{header}**")

    for pos in positions:
        is_closed = bool(pos.get("is_closed"))
        # Price choice (closing if closed, else live)
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

        # Intraday: hide when closed or missing
        intraday = None if is_closed else pos.get("intraday_change")
        intraday_pct = None if is_closed else pos.get("intraday_change_pct")

        (
            c_sym,
            c_name,
            c_qty,
            c_cost,
            c_cur,
            c_inv,
            c_val,
            c_pl,
            c_iday,
            c_idaypct,
            c_tags,
            c_act,
        ) = st.columns(col_layout)

        # Symbol with Yahoo link + tiny closed indicator (no extra height)
        sym_html = f"<a href='https://finance.yahoo.com/quote/{pos['symbol']}' target='_blank'>{pos['symbol']}</a>"
        closed_icon = " <span class='status-badge'>🔒</span>" if is_closed else ""
        c_sym.markdown(f"<div class='cell'>{sym_html}{closed_icon}</div>", unsafe_allow_html=True)

        # Long name (no wrap)
        long_name = pos.get("long_name") or ""
        c_name.markdown(f"<div class='cell-wrap'>{long_name}</div>", unsafe_allow_html=True)

        # Numbers (fixed 2 decimals in a no-wrap cell)
        c_qty.markdown(f"<div class='cell'>{fmt2(qty)}</div>", unsafe_allow_html=True)
        c_cost.markdown(f"<div class='cell'>{fmt2(cost)}</div>", unsafe_allow_html=True)
        c_cur.markdown(f"<div class='cell'>{fmt2(effective_price)}</div>", unsafe_allow_html=True)
        c_inv.markdown(f"<div class='cell'>{fmt2(invest)}</div>", unsafe_allow_html=True)
        c_val.markdown(f"<div class='cell'>{fmt2(current_value)}</div>", unsafe_allow_html=True)
        c_pl.markdown(f"<div class='cell'>{fmt2(pnl_value)}</div>", unsafe_allow_html=True)

        # Intraday cells (— when closed or missing). Color green/red if present.
        intraday = None if is_closed else pos.get("intraday_change")
        intraday_pct = None if is_closed else pos.get("intraday_change_pct")

        if intraday is None:
            c_iday.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            intraday_class = "pos-green" if float(intraday) >= 0 else "pos-red"
            c_iday.markdown(
                f"<div class='cell {intraday_class}'>{fmt2(intraday)}</div>", unsafe_allow_html=True
            )

        if intraday_pct is None:
            c_idaypct.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            intraday_pct_class = "pos-green" if float(intraday_pct) >= 0 else "pos-red"
            c_idaypct.markdown(
                f"<div class='cell {intraday_pct_class}'>{float(intraday_pct):.2f}%</div>",
                unsafe_allow_html=True,
            )
        # Tags
        badges = " ".join(f"<span class='tag-badge'>{t}</span>" for t in pos.get("tags", []))
        c_tags.markdown(f"<div class='cell'>{badges}</div>", unsafe_allow_html=True)

        # Actions: icon-only, side-by-side (no labels)
        with c_act.container():
            b_edit, b_del = st.columns([1, 1])
            if b_edit.button("✏️", key=f"edit_{pos['_id']}"):
                edit_dialog(pos)
            if b_del.button("🗑️", key=f"del_{pos['_id']}"):
                try:
                    delete_position(pos["_id"])
                    st.success(f"Deleted {pos['symbol']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error deleting: {e}")

    st.subheader("Totals")
    col_mv, col_pl = st.columns(2)
    col_mv.metric("Total Market Value", fmt2(summary.get("total_market_value", 0.0)))
    col_pl.metric("Total Unrealized P/L", fmt2(summary.get("total_unrealized_pl", 0.0)))


if __name__ == "__main__":
    main()
