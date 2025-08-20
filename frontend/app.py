# frontend/app.py
from __future__ import annotations

import statistics

import httpx
import streamlit as st
from streamlit_tags import st_tags

API_URL = "http://127.0.0.1:8000"


def fmt2(x) -> str:
    """Format any number to 2 decimals; otherwise '0.00'."""
    try:
        return f"{float(x):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def parse_price(s: str | float | None) -> float | None:
    """Accept '28,09' or '28.09' or a float; return float or None."""
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
    """Small HTTP helper with nicer Streamlit errors."""
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


def _color_from_scale(x: float, vmin: float, vmed: float, vmax: float) -> str:
    """
    Map value x onto a red(0deg)→yellow(60deg)→green(120deg) HSL hue.
    Uses vmin, vmed, vmax (min/median/max of the column).
    Returns an inline CSS style string for background color.
    """
    if vmin == vmax:
        return "background-color: hsl(0, 0%, 90%); border-radius: 6px; padding: 2px 6px;"
    if x <= vmed:
        t = 0.0 if vmed == vmin else (x - vmin) / (vmed - vmin)
        hue = 0 + (60 * max(0.0, min(1.0, t)))
    else:
        t = 1.0 if vmax == vmed else (x - vmed) / (vmax - vmed)
        hue = 60 + (60 * max(0.0, min(1.0, t)))
    return f"background-color: hsl({hue:.0f}, 70%, 85%); border-radius: 6px; padding: 2px 6px;"


def _color_from_scale_intraday(x: float | None, vmin: float, vmax: float) -> str:
    """
    Asymmetric color scale for intraday %:
    - Negatives map red (worst) -> orange/yellow (near 0)
    - Positives map yellow (near 0) -> strong green (best)
    Intense colors via high saturation / moderate lightness.
    """
    if x is None:
        return "background-color: hsl(0, 0%, 90%); border-radius: 6px; padding: 2px 6px;"

    try:
        x = float(x)
    except Exception:
        return "background-color: hsl(0, 0%, 90%); border-radius: 6px; padding: 2px 6px;"

    neg_min = min(0.0, float(vmin))  # most negative (≤ 0)
    pos_max = max(0.0, float(vmax))  # most positive (≥ 0)

    # Fallback: all zeros
    if neg_min == 0.0 and pos_max == 0.0:
        return "background-color: hsl(0, 0%, 90%); border-radius: 6px; padding: 2px 6px;"

    # Stronger, more vivid palette
    SAT = 92
    LGT = 70

    if x < 0 and neg_min < 0:
        # Map [neg_min .. 0] -> [red(0°) .. orange/yellow(50°)]
        t = (x - 0.0) / (neg_min - 0.0)  # in [0..1], 1=most negative, 0=near 0-
        t = max(0.0, min(1.0, t))
        hue = 0.0 + (50.0 * (1.0 - t))  # 0 -> 50
    elif x > 0 and pos_max > 0:
        # Map [0 .. pos_max] -> [yellow(60°) .. strong green(140°)]
        t = x / pos_max  # in [0..1]
        t = max(0.0, min(1.0, t))
        hue = 60.0 + (80.0 * t)  # 60 -> 140
    else:
        # Exactly zero (or no span on that side) -> yellow
        hue = 58.0

    return (
        f"background-color: hsl({hue:.0f}, {SAT}%, {LGT}%); border-radius: 6px; padding: 2px 6px;"
    )


@st.dialog("Edit Position")
def edit_dialog(pos):
    """Modal dialog for editing a position."""
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
    st.set_page_config(page_title="Portfolio Dashboard")
    st.title("📊 Portfolio Dashboard")

    # Global style tweaks
    st.markdown(
        """
        <style>
        /* Cells */
        .cell { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2rem; }
        .cell-wrap {
            white-space: normal; overflow: hidden;
            display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
            line-height: 1.2rem; max-height: calc(1.2rem * 2);
        }
        .tag-badge { background:#eee; border-radius:4px; padding:2px 6px; margin:0 2px; display:inline-block; }
        .status-badge { font-size:0.9em; margin-left: 6px; }
        .pos-green { color: #0a0; }
        .pos-red { color: #c00; }
        .muted { color: #666; }

        /* Tight layout */
        .block-container {
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
            max-width: 100% !important;
        }
        .main { padding-left: 0rem !important; padding-right: 0rem !important; }
        header { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Tag filter state
    if "filter_tag" not in st.session_state:
        st.session_state.filter_tag = None

    # ── Add Position ─────────────────────────────────────────────
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

    # ── Data ────────────────────────────────────────────────────
    positions = load_positions()
    tags_summary = load_tag_summary()

    # ── Tag Summary (click to filter) ────────────────────────────────────
    st.subheader("Tag Summary (click to filter)")

    # Collect intraday % values to set the color scale range
    iday_values = []
    for t in tags_summary:
        v = t.get("intraday_change_pct")
        try:
            if v is not None:
                iday_values.append(float(v))
        except Exception:
            pass

    if iday_values:
        vmin_tag = min(iday_values)
        vmax_tag = max(iday_values)
    else:
        vmin_tag = vmax_tag = 0.0  # fallback when no data

    # Header row (add Intraday % as a narrow column)
    hdr_tag, hdr_mv, hdr_pl, hdr_iday, _ = st.columns([2.2, 1.2, 1.2, 0.9, 0.4])
    hdr_tag.markdown("**Tag**")
    hdr_mv.markdown("**Market Value**")
    hdr_pl.markdown("**Unrealized P/L**")
    hdr_iday.markdown("**Intraday %**")

    # Data rows
    for t in tags_summary:
        c_tag, c_mv, c_pl, c_iday, c_sp = st.columns([2.2, 1.2, 1.2, 0.9, 0.4])

        # Tag as a filter button
        if c_tag.button(t["tag"], key=f"filter_{t['tag']}"):
            st.session_state.filter_tag = t["tag"]

        # Market Value & Unrealized P/L
        c_mv.write(fmt2(t.get("total_market_value", 0.0)))
        c_pl.write(fmt2(t.get("total_unrealized_pl", 0.0)))

        # Intraday % with asymmetric color scale (red→orange/yellow for negatives, yellow→green for positives)
        pct = t.get("intraday_change_pct")
        if pct is None:
            c_iday.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            try:
                pctf = float(pct)
                style = _color_from_scale_intraday(pctf, vmin_tag, vmax_tag)
                c_iday.markdown(
                    f"<div class='cell' style='{style}'>{pctf:.2f}%</div>",
                    unsafe_allow_html=True,
                )
            except Exception:
                c_iday.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)

        c_sp.write("")

    # Show/clear active filter
    if st.session_state.filter_tag:
        st.markdown(f"**Filtering by tag:** `{st.session_state.filter_tag}`")
        if st.button("Clear filter"):
            st.session_state.filter_tag = None
            st.rerun()

    if st.session_state.filter_tag:
        positions = [p for p in positions if st.session_state.filter_tag in p.get("tags", [])]

    # ── Build rows & color-scale stats ──────────────────────────
    rows = []
    pnl_values = []
    intraday_pcts = []  # collect INTRADAY % for the scale
    total_invest_val = 0.0
    total_mv_val = 0.0

    for pos in positions:
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
        pnl_pct = (pnl_value / invest * 100.0) if invest else 0.0

        # Intraday % for scale (only when open & present)
        intraday_pct = None if is_closed else pos.get("intraday_change_pct")
        if intraday_pct is not None:
            try:
                intraday_pcts.append(float(intraday_pct))
            except Exception:
                pass

        rows.append(
            (
                pos,
                is_closed,
                effective_price,
                qty,
                cost,
                invest,
                current_value,
                pnl_value,
                pnl_pct,
                intraday_pct,
            )
        )
        pnl_values.append(pnl_value)

        total_invest_val += invest
        total_mv_val += current_value

    # P/L scale
    if pnl_values:
        vmin_pl = min(pnl_values)
        vmax_pl = max(pnl_values)
        vmed_pl = statistics.median(pnl_values)
    else:
        vmin_pl = vmax_pl = vmed_pl = 0.0

    # Intraday % scale
    if intraday_pcts:
        vmin_idp = min(intraday_pcts)
        vmax_idp = max(intraday_pcts)
    else:
        vmin_idp = vmax_idp = 0.0

    # ── Positions Table ─────────────────────────────────────────
    st.subheader("Positions")

    # Columns: Symbol | Name | Qty | Cost | Current | Invest | Value
    # | P/L | P/L % | Intraday | Intraday % | Tags | Actions
    col_layout = [
        1.1,
        3.2,
        0.9,
        1.0,
        1.1,
        1.1,
        1.3,
        1.1,
        1.0,
        1.0,
        1.0,
        1.6,
        0.7,
    ]
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
        "P/L %",
        "Intraday",
        "Intraday %",
        "Tags",
        "",
    ]
    for col, header in zip(cols, headers):
        col.markdown(f"**{header}**")

    for (
        pos,
        is_closed,
        effective_price,
        qty,
        cost,
        invest,
        current_value,
        pnl_value,
        pnl_pct,
        intraday_pct,
    ) in rows:
        (
            c_sym,
            c_name,
            c_qty,
            c_cost,
            c_cur,
            c_inv,
            c_val,
            c_pl,
            c_plpct,
            c_iday,
            c_idaypct,
            c_tags,
            c_act,
        ) = st.columns(col_layout)

        # Ticker link + closed icon
        sym_html = f"<a href='https://finance.yahoo.com/quote/{pos['symbol']}' target='_blank'>{pos['symbol']}</a>"
        closed_icon = " <span class='status-badge'>🔒</span>" if is_closed else ""
        c_sym.markdown(f"<div class='cell'>{sym_html}{closed_icon}</div>", unsafe_allow_html=True)

        # Long name (2 lines max)
        long_name = pos.get("long_name") or ""
        c_name.markdown(f"<div class='cell-wrap'>{long_name}</div>", unsafe_allow_html=True)

        # Numeric basics
        c_qty.markdown(f"<div class='cell'>{fmt2(qty)}</div>", unsafe_allow_html=True)
        c_cost.markdown(f"<div class='cell'>{fmt2(cost)}</div>", unsafe_allow_html=True)
        c_cur.markdown(f"<div class='cell'>{fmt2(effective_price)}</div>", unsafe_allow_html=True)
        c_inv.markdown(f"<div class='cell'>{fmt2(invest)}</div>", unsafe_allow_html=True)
        # Current Value: hide for closed positions
        if is_closed:
            c_val.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            c_val.markdown(
                f"<div class='cell'>{fmt2(current_value)}</div>",
                unsafe_allow_html=True,
            )
        # P/L (colored scale)
        c_pl.markdown(
            f"<div class='cell' style='{_color_from_scale(pnl_value, vmin_pl, vmed_pl, vmax_pl)}'>"
            f"{fmt2(pnl_value)}</div>",
            unsafe_allow_html=True,
        )
        # P/L % (plain text)
        c_plpct.markdown(f"<div class='cell'>{pnl_pct:.2f}%</div>", unsafe_allow_html=True)

        # Intraday absolute (red/green text or em dash if closed/missing)
        intraday_abs = None if is_closed else pos.get("intraday_change")
        if intraday_abs is None:
            c_iday.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            intraday_class = "pos-green" if float(intraday_abs) >= 0 else "pos-red"
            c_iday.markdown(
                f"<div class='cell {intraday_class}'>{fmt2(intraday_abs)}</div>",
                unsafe_allow_html=True,
            )
        # Intraday % (colored scale using asymmetric intraday palette)
        if (intraday_pct is None) or is_closed:
            c_idaypct.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            intraday_pct_val = float(intraday_pct)
            style = _color_from_scale_intraday(intraday_pct_val, vmin_idp, vmax_idp)
            c_idaypct.markdown(
                f"<div class='cell' style='{style}'>{intraday_pct_val:.2f}%</div>",
                unsafe_allow_html=True,
            )

        # Tags
        badges = " ".join(f"<span class='tag-badge'>{t}</span>" for t in pos.get("tags", []))
        c_tags.markdown(f"<div class='cell'>{badges}</div>", unsafe_allow_html=True)

        # Actions (icons only)
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

    # ── Totals ─────────────────────────────────────────────────
    st.subheader("Totals")

    # Total Invest (ALL positions, open + closed)
    total_invest_all = sum(
        float(p.get("quantity", 0.0)) * float(p.get("cost_price", 0.0)) for p in positions
    )

    # Total Market Value (OPEN positions only, use live/current price)
    total_mv_open = 0.0
    for p in positions:
        if bool(p.get("is_closed")):
            continue
        qty = float(p.get("quantity", 0.0))
        price = float(p.get("current_price") or 0.0)
        total_mv_open += qty * price

    # P/L (Open vs Invest All) and % vs Invest All (based on MV_open and Invest_all)
    pl_open_vs_invest_all = total_mv_open - total_invest_all
    pl_pct_vs_invest_all = (
        ((total_mv_open - total_invest_all) / total_invest_all) * 100.0 if total_invest_all else 0.0
    )

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Total Invest (All)", fmt2(total_invest_all))
    t2.metric("Total Market Value (Open)", fmt2(total_mv_open))
    t3.metric("P/L (Open vs Invest All)", fmt2(pl_open_vs_invest_all))
    t4.metric("P/L % (vs Invest All)", f"{pl_pct_vs_invest_all:.2f}%")


if __name__ == "__main__":
    main()
