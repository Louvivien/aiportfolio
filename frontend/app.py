# frontend/app.py
from __future__ import annotations

import statistics

import httpx
import streamlit as st
from streamlit_tags import st_tags

API_URL = "http://127.0.0.1:8000"

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CHF": "CHF",
    "CAD": "C$",
    "AUD": "A$",
    "HKD": "HK$",
    "CNY": "¥",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
}


def fmt_money(amount: float | None, currency: str | None) -> str:
    if amount is None:
        return "—"
    s = fmt2(amount)
    cur = (currency or "").upper()
    sym = CURRENCY_SYMBOLS.get(cur)
    return f"{sym}{s}" if sym else (f"{s} {cur}" if cur else s)


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


# --- Google Sheets–style color helpers ---------------------------------------
def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _blend(c1: str, c2: str, t: float) -> str:
    """Linear blend between two hex colors (0..1)."""
    t = max(0.0, min(1.0, float(t)))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return _rgb_to_hex((r, g, b))


# Google palette (matches your sheet screenshot)
_GS_RED = "#d93025"
_GS_YEL = "#fbbc04"
_GS_GRN = "#34a853"
_NEUTRAL = "#e9ecef"  # light gray fallback


def _color_from_scale(x: float, vmin: float, vmed: float, vmax: float) -> str:
    """
    Return a Google Sheets–style 3-color scale:
    min → red, mid → yellow, max → green.
    Used for P/L (value) cells.
    """
    try:
        x = float(x)
    except Exception:
        return f"background-color:{_NEUTRAL}; color:black; " "border-radius:6px; padding:2px 6px;"

    if vmin == vmax:
        return f"background-color:{_NEUTRAL}; color:black; " "border-radius:6px; padding:2px 6px;"

    if x <= vmed:
        # min..mid → red..yellow
        t = 0.0 if vmed == vmin else (x - vmin) / (vmed - vmin)
        color = _blend(_GS_RED, _GS_YEL, t)
    else:
        # mid..max → yellow..green
        t = 1.0 if vmax == vmed else (x - vmed) / (vmax - vmed)
        color = _blend(_GS_YEL, _GS_GRN, t)

    # always white text
    return f"background-color:{color}; color:white; border-radius:6px; padding:2px 6px;"


def _color_from_scale_intraday(x: float | None, vmin: float, vmax: float) -> str:
    """
    Google Sheets–style scale for INTRADAY % with hard 0 pivot:
      negatives  -> red .. yellow  (NEVER green)
      positives  -> yellow .. green
    """
    if x is None:
        return (
            f"background-color:{_NEUTRAL}; color:black; "
            "border-radius:6px; padding:2px 6px; display:inline-block; "
            "min-width:64px; text-align:right;"
        )
    try:
        x = float(x)
    except Exception:
        return (
            f"background-color:{_NEUTRAL}; color:black; "
            "border-radius:6px; padding:2px 6px; display:inline-block; "
            "min-width:64px; text-align:right;"
        )

    neg_min = min(0.0, float(vmin))
    pos_max = max(0.0, float(vmax))

    if x < 0 and neg_min < 0:
        # [neg_min .. 0] → red .. yellow
        t = (x - neg_min) / (0.0 - neg_min)
        color = _blend(_GS_RED, _GS_YEL, t)
    elif x > 0 and pos_max > 0:
        # [0 .. pos_max] → yellow .. green
        t = x / pos_max
        color = _blend(_GS_YEL, _GS_GRN, t)
    else:
        color = _GS_YEL  # exactly 0

    # white text for readability
    return (
        f"background-color:{color}; color:white; border-radius:6px; padding:2px 6px; "
        "display:inline-block; min-width:64px; text-align:right;"
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

    # 10D % scale (for table color)
    ten_day_pcts = []
    for pos, is_closed, _, qty, _, _, _, _, _, _ in rows:
        v = None if is_closed else pos.get("change_10d_pct")
        try:
            if v is not None:
                ten_day_pcts.append(float(v))
        except Exception:
            pass
    if ten_day_pcts:
        vmin_10d = min(ten_day_pcts)
        vmax_10d = max(ten_day_pcts)
    else:
        vmin_10d = vmax_10d = 0.0

    # ── Positions Table ─────────────────────────────────────────
    st.subheader("Positions")

    # ── Sort controls (clickable headers with arrows) ───────────
    if "sort_by" not in st.session_state:
        st.session_state.sort_by = None
        st.session_state.sort_desc = False

    # Which headers are sortable (no Actions)
    header_labels = [
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
        "10D %",
        "Tags",
    ]

    def _toggle_sort(column: str):
        if st.session_state.sort_by == column:
            st.session_state.sort_desc = not st.session_state.sort_desc
        else:
            st.session_state.sort_by = column
            st.session_state.sort_desc = False

    def _with_arrow(name: str) -> str:
        """Return header text with ▲/▼ if active."""
        if st.session_state.sort_by == name:
            return f"{name} {'▼' if st.session_state.sort_desc else '▲'}"
        return name

    # Header row: clickable buttons (no Actions column here)
    header_layout = [1.1, 3.2, 0.9, 1.0, 1.1, 1.1, 1.3, 1.1, 1.0, 1.0, 1.0, 1.6]
    hdr_cols = st.columns(header_layout)
    for col, header in zip(hdr_cols, header_labels):
        if col.button(_with_arrow(header), key=f"hdr_{header}"):
            _toggle_sort(header)

    # Reset to original DB order
    if st.button("🔄 Reset Order"):
        st.session_state.sort_by = None
        st.session_state.sort_desc = False

    # Apply sorting if active (uses your existing `rows` list)
    def _row_value(row):
        # rows: (pos, is_closed, effective_price, qty, cost, invest,
        #        current_value, pnl_value, pnl_pct, intraday_pct)
        pos, is_closed, eff, qty, cost, invest, curval, plv, plpct, idpct = row
        tags_joined = ", ".join(pos.get("tags", [])) if pos.get("tags") else ""
        sb = st.session_state.sort_by
        if sb == "Symbol":
            return (pos.get("symbol") or "").upper()
        if sb == "Name":
            return (pos.get("long_name") or "").upper()
        if sb == "Qty":
            return qty
        if sb == "Cost":
            return cost
        if sb == "Current":
            return eff
        if sb == "Invest":
            return invest
        if sb == "Value":
            return None if is_closed else curval
        if sb == "P/L":
            return plv
        if sb == "P/L %":
            return plpct
        if sb == "Intraday":
            if is_closed:
                return None
            ch = pos.get("intraday_change")
            try:
                return float(ch) * float(qty)  # sort by absolute intraday value (per-share × qty)
            except (TypeError, ValueError):
                return None
        if sb == "Intraday %":
            return None if is_closed else idpct
        if sb == "10D %":
            return None if is_closed else pos.get("change_10d_pct")
        if sb == "Tags":
            return tags_joined.upper()
        return None

    def _safe_key(v):
        # Sort robustly across None/str/float
        try:
            return (False, float(v))
        except Exception:
            if isinstance(v, str):
                return (False, v)
            return (True, 0.0)

    if st.session_state.sort_by:
        rows.sort(key=lambda r: _safe_key(_row_value(r)), reverse=st.session_state.sort_desc)

    # Columns: Symbol | Name | Qty | Cost | Current | Invest | Value
    # | P/L | P/L % | Intraday | Intraday % | Tags | Actions
    col_layout = [
        1.1,  # Symbol
        3.2,  # Name
        0.9,  # Qty
        1.0,  # Cost
        1.1,  # Current
        1.1,  # Invest
        1.3,  # Value
        1.1,  # P/L
        1.0,  # P/L %
        1.0,  # Intraday
        1.0,  # Intraday %
        1.0,  # 10D %
        1.6,  # Tags
        0.7,  # Actions
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
        "10D %",
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
            c_10dpct,
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
        c_cost.markdown(
            f"<div class='cell'>{fmt_money(cost, pos.get('currency'))}</div>",
            unsafe_allow_html=True,
        )
        c_cur.markdown(
            f"<div class='cell'>{fmt_money(effective_price, pos.get('currency'))}</div>",
            unsafe_allow_html=True,
        )
        c_inv.markdown(
            f"<div class='cell'>{fmt_money(invest, pos.get('currency'))}</div>",
            unsafe_allow_html=True,
        )
        # Current Value: hide for closed positions
        if is_closed:
            c_val.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            c_val.markdown(
                f"<div class='cell'>{fmt_money(current_value, pos.get('currency'))}</div>",
                unsafe_allow_html=True,
            )
        # P/L (colored scale)
        c_pl.markdown(
            f"<div class='cell' style='{_color_from_scale(pnl_value, vmin_pl, vmed_pl, vmax_pl)}'>"
            f"{fmt_money(pnl_value, pos.get('currency'))}</div>",
            unsafe_allow_html=True,
        )
        # P/L % (plain text)
        c_plpct.markdown(f"<div class='cell'>{pnl_pct:.2f}%</div>", unsafe_allow_html=True)

        # Intraday absolute (position value change = per-share change × quantity)
        raw_change = None if is_closed else pos.get("intraday_change")
        intraday_abs = None if (raw_change is None) else float(raw_change) * qty
        if intraday_abs is None:
            c_iday.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            intraday_class = "pos-green" if intraday_abs >= 0 else "pos-red"
            c_iday.markdown(
                f"<div class='cell {intraday_class}'>{fmt_money(intraday_abs, pos.get('currency'))}</div>",
                unsafe_allow_html=True,
            )

        # 10D % (colored scale like intraday but 10-day window)
        ten_pct = None if is_closed else pos.get("change_10d_pct")
        if ten_pct is None:
            c_10dpct.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)
        else:
            try:
                ten_val = float(ten_pct)
                # reuse intraday asymmetric palette (never green for negatives)
                style_10 = _color_from_scale_intraday(ten_val, vmin_10d, vmax_10d)
                c_10dpct.markdown(
                    f"<div class='cell' style='{style_10}'>{ten_val:.2f}%</div>",
                    unsafe_allow_html=True,
                )
            except Exception:
                c_10dpct.markdown("<div class='cell muted'>—</div>", unsafe_allow_html=True)

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

    # Totals for OPEN positions only
    total_mv_open = 0.0
    intraday_abs_sum = 0.0  # total absolute intraday change (in EUR)
    for p in positions:
        if bool(p.get("is_closed")):
            continue
        qty = float(p.get("quantity", 0.0))
        price = float(p.get("current_price") or 0.0)
        total_mv_open += qty * price

        # intraday absolute change for this position (per-share change × qty)
        ch = p.get("intraday_change")
        if ch is not None:
            try:
                intraday_abs_sum += float(ch) * qty
            except Exception:
                pass

    # P/L (Open vs Invest All) and % vs Invest All
    pl_open_vs_invest_all = total_mv_open - total_invest_all
    pl_pct_vs_invest_all = (
        ((total_mv_open - total_invest_all) / total_invest_all) * 100.0 if total_invest_all else 0.0
    )

    # Portfolio intraday % (weighted by open positions)
    portfolio_intraday_pct = (intraday_abs_sum / total_mv_open * 100.0) if total_mv_open else 0.0

    # Totals (formatted in EUR)
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Total Invest (All)", fmt_money(total_invest_all, "EUR"))
    t2.metric("Total Market Value (Open)", fmt_money(total_mv_open, "EUR"))
    t3.metric("P/L (Open vs Invest All)", fmt_money(pl_open_vs_invest_all, "EUR"))
    t4.metric("P/L % (vs Invest All)", f"{pl_pct_vs_invest_all:.2f}%")

    # Compact intraday badge with amount and percentage
    badge_bg = _GS_GRN if portfolio_intraday_pct >= 0 else _GS_RED
    st.markdown(
        f"<div style='display:inline-block; margin-top:4px; "
        f"padding:2px 8px; border-radius:6px; font-weight:600; "
        f"color:white; background:{badge_bg};'>"
        f"Intraday (Open): {fmt_money(intraday_abs_sum, 'EUR')} ({portfolio_intraday_pct:+.2f}%)</div>",
        unsafe_allow_html=True,
    )

    # --- 10D totals (Open) ---
    total_mv_open_10d = 0.0
    for p in positions:
        if bool(p.get("is_closed")):
            continue
        qty = float(p.get("quantity", 0.0))
        p10 = p.get("price_10d")
        try:
            if p10 is not None:
                total_mv_open_10d += qty * float(p10)
        except Exception:
            pass

    if total_mv_open_10d:
        ten_abs_sum = total_mv_open - total_mv_open_10d
        ten_pct_total = (ten_abs_sum / total_mv_open_10d) * 100.0
    else:
        ten_abs_sum = 0.0
        ten_pct_total = 0.0

    badge_bg_10 = _GS_GRN if ten_pct_total >= 0 else _GS_RED
    st.markdown(
        f"<div style='display:inline-block; margin-top:4px; margin-left:8px; "
        f"padding:2px 8px; border-radius:6px; font-weight:600; "
        f"color:white; background:{badge_bg_10};'>"
        f"10D (Open): {fmt_money(ten_abs_sum, 'EUR')} ({ten_pct_total:+.2f}%)</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
