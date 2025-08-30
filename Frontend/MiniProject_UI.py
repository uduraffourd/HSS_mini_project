# app.py
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import random, math, uuid

st.set_page_config(page_title="Hydro Software Services App", layout="wide")
st.title("Hydro Software Services App")

# ---------- Session state ----------
if "plants" not in st.session_state:
    st.session_state.plants = []  # Each: {"uid","name","id","created_at","weather":{"name","id"}}
if "show_form" not in st.session_state:
    st.session_state.show_form = False
if "new_name" not in st.session_state:
    st.session_state.new_name = ""
if "new_id" not in st.session_state:
    st.session_state.new_id = ""
if "open_actions" not in st.session_state:
    st.session_state.open_actions = {}  # uid -> bool (actions panel open/closed)

# NEW: which plant drives the center chart (production) and optional rain overlay
if "active_prod_uid" not in st.session_state:
    st.session_state.active_prod_uid = None
if "active_rain_uid" not in st.session_state:
    st.session_state.active_rain_uid = None

if "delete_confirms" not in st.session_state:
    st.session_state.delete_confirms = {}  # uid -> bool

# ---------- Helpers ----------
def now_human():
    return datetime.now().strftime("%d-%m-%Y at %H:%M:%S")

def add_plant(name: str, pid: str):
    st.session_state.plants.append({
        "uid": str(uuid.uuid4()),
        "name": name.strip(),
        "id": pid.strip(),
        "created_at": now_human(),
        "weather": {"name": "", "id": ""}
    })

def get_plant_by_uid(uid: str):
    for p in st.session_state.plants:
        if p["uid"] == uid:
            return p
    return None

def delete_plant_by_uid(uid: str):
    st.session_state.plants = [p for p in st.session_state.plants if p["uid"] != uid]
    st.session_state.delete_confirms.pop(uid, None)
    st.session_state.open_actions.pop(uid, None)
    # Clear selections if they pointed to this plant
    if st.session_state.active_prod_uid == uid:
        st.session_state.active_prod_uid = None
    if st.session_state.active_rain_uid == uid:
        st.session_state.active_rain_uid = None

def save_weather(uid: str, ws_name: str, ws_id: str):
    p = get_plant_by_uid(uid)
    if not p: return
    p["weather"]["name"] = ws_name.strip()
    p["weather"]["id"] = ws_id.strip()

def modify_plant(uid: str, new_name: str, new_id: str, ws_name: str, ws_id: str):
    p = get_plant_by_uid(uid)
    if not p: return
    p["name"] = new_name.strip()
    p["id"] = new_id.strip()
    p["weather"]["name"] = ws_name.strip()
    p["weather"]["id"] = ws_id.strip()
    # Do not auto-toggle production/rain here

def date_window_last_30_to_yesterday():
    today = datetime.now().date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=29)
    return pd.date_range(start, end, freq="D")

def placeholder_production_series(idx: pd.DatetimeIndex):
    # Dummy kWh shape
    base, amp = 1200.0, 300.0
    day0 = idx[0].to_pydatetime().toordinal()
    vals, rnd = [], random.Random(42)
    for t in idx:
        x = (t.to_pydatetime().toordinal() - day0)
        y = base + amp * math.sin(2*math.pi * x / 14) + rnd.uniform(-50, 50)
        vals.append(round(max(0, y), 1))
    return pd.Series(vals, index=idx, name="Production (kWh)")

def placeholder_rain_series(idx: pd.DatetimeIndex, seed_text: str):
    rnd = random.Random(seed_text)
    vals = []
    for _ in range(len(idx)):
        r = rnd.random()
        if r < 0.1: vals.append(round(rnd.uniform(8, 20), 1))
        elif r < 0.4: vals.append(round(rnd.uniform(0.5, 5), 1))
        else: vals.append(0.0)
    return pd.Series(vals, index=idx, name="Rain (mm)")

def build_fig(prod: pd.Series, rain: pd.Series | None):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prod.index, y=prod.values, mode="lines", name="Production (kWh)"))
    if rain is not None:
        fig.add_trace(go.Bar(x=rain.index, y=rain.values, name="Rain (mm)", opacity=0.4, yaxis="y2"))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Date",
        yaxis_title="kWh",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis2=dict(title="Rain (mm)", overlaying="y", side="right", rangemode="tozero"),
        bargap=0.15, hovermode="x unified", height=460
    )
    return fig

# ---------- Layout ----------
center, right = st.columns([2.4, 1.2], gap="large")

# CENTER-LEFT: Chart (only if a plant is “shown”)
with center:
    st.subheader("Plant production")
    if st.session_state.active_prod_uid is None:
        st.info("No plant selected yet. Use “⋯ → Show hydro power plant production” on a plant to display the chart.")
    else:
        idx = date_window_last_30_to_yesterday()
        prod = placeholder_production_series(idx)

        rain = None
        if st.session_state.active_rain_uid == st.session_state.active_prod_uid:
            active = get_plant_by_uid(st.session_state.active_rain_uid)
            if active:
                rain = placeholder_rain_series(idx, seed_text=active["id"])

        st.plotly_chart(build_fig(prod, rain), use_container_width=True)
        p = get_plant_by_uid(st.session_state.active_prod_uid)
        if p:
            ws = p["weather"]
            ws_text = f"Weather station: {ws['name']} ({ws['id']})" if (ws['name'] or ws['id']) else "Weather station: —"
            st.caption(f"Window: last 30 days up to yesterday • Showing: **{p['name']}** (ID `{p['id']}`) • {ws_text}")
        else:
            st.caption("Window: last 30 days up to yesterday.")

# RIGHT: Add (top) + Saved (bottom)
with right:
    # Top-right: Add form
    st.subheader("Add a power plant")
    if st.button("➕ Add a power plant", use_container_width=True, key="btn_add_open"):
        st.session_state.show_form = True
    if st.session_state.show_form:
        with st.form(key="create_plant_form", border=True):
            st.markdown("**Create a new Hydropower Plant**")
            name = st.text_input("Hydro Power Plant name", value=st.session_state.new_name,
                                 placeholder="e.g., Breuchin Small Hydro #1", key="new_plant_name")
            pid = st.text_input("Hydro Power Plant id", value=st.session_state.new_id,
                                placeholder="e.g., HPP-0001", key="new_plant_id")
            if st.form_submit_button("Save", use_container_width=True):
                if not name.strip() or not pid.strip():
                    st.error("Both fields are required.")
                elif any(p["id"].lower() == pid.strip().lower() for p in st.session_state.plants):
                    st.warning("A plant with this ID already exists.")
                else:
                    add_plant(name, pid)
                    st.success(f"Plant **{name}** (ID: {pid}) saved locally.")
                    st.session_state.new_name = ""
                    st.session_state.new_id = ""
                    st.session_state.show_form = False
                    st.rerun()

    st.divider()

    # Bottom-right: List
    st.subheader("Saved plants")
    if not st.session_state.plants:
        st.info("No plants yet.")
    else:
        for p in st.session_state.plants:
            uid = p["uid"]
            if uid not in st.session_state.open_actions:
                st.session_state.open_actions[uid] = False

            with st.container(border=True):
                top = st.columns([0.85, 0.15])
                with top[0]:
                    st.markdown(f"**{p['name']}**")
                    st.caption(f"ID: `{p['id']}` • Added: {p['created_at']}")
                    ws = p["weather"]
                    ws_line = "Weather station: "
                    if ws["name"] or ws["id"]:
                        ws_line += f"{ws['name']} ({ws['id']})"
                    st.write(ws_line)
                with top[1]:
                    # Small icon-like button "⋯" to toggle actions panel
                    if st.button("⋯", key=f"toggle_actions_{uid}", use_container_width=True):
                        st.session_state.open_actions[uid] = not st.session_state.open_actions[uid]
                        st.rerun()

                # Actions panel
                if st.session_state.open_actions[uid]:
                    with st.container(border=True):
                        st.markdown("**Actions**")

                        # Show/Hide production (controls the center chart)
                        show_prod = (st.session_state.active_prod_uid == uid)
                        prod_label = "Hide hydro power plant production" if show_prod else "Show hydro power plant production"
                        if st.button(prod_label, use_container_width=True, key=f"show_prod_{uid}"):
                            st.session_state.active_prod_uid = None if show_prod else uid
                            # If we hide production, also hide rain for that plant
                            if st.session_state.active_prod_uid is None and st.session_state.active_rain_uid == uid:
                                st.session_state.active_rain_uid = None
                            st.rerun()

                        # Add weather station
                        with st.expander("Add weather station", expanded=False):
                            ws_name = st.text_input(f"Weather station name {uid}",
                                                    value=p['weather']['name'],
                                                    placeholder="e.g., Meteo Breuchin",
                                                    key=f"ws_name_{uid}")
                            ws_id = st.text_input(f"Weather station id {uid}",
                                                  value=p['weather']['id'],
                                                  placeholder="e.g., WS-001",
                                                  key=f"ws_id_{uid}")
                            if st.button("Save weather station", use_container_width=True, key=f"ws_save_{uid}"):
                                save_weather(uid, ws_name, ws_id)
                                st.success("Weather station saved.")
                                st.rerun()

                        # Modify plant + weather
                        with st.expander("Modify", expanded=False):
                            new_name = st.text_input(f"Plant name {uid}", value=p["name"], key=f"plant_name_{uid}")
                            new_id = st.text_input(f"Plant id {uid}", value=p["id"], key=f"plant_id_{uid}")
                            new_ws_name = st.text_input(f"Weather station name (edit) {uid}",
                                                        value=p["weather"]["name"], key=f"plant_ws_name_{uid}")
                            new_ws_id = st.text_input(f"Weather station id (edit) {uid}",
                                                      value=p["weather"]["id"], key=f"plant_ws_id_{uid}")
                            if st.button("Save changes", use_container_width=True, key=f"plant_save_{uid}"):
                                if not new_name.strip() or not new_id.strip():
                                    st.error("Plant name and id are required.")
                                elif any(other["uid"] != uid and other["id"].lower() == new_id.strip().lower()
                                         for other in st.session_state.plants):
                                    st.warning("Another plant already uses this ID.")
                                else:
                                    # If this plant is currently driving the rain overlay, and ID changes,
                                    # keep overlay by uid (we use uid for state, so it's fine). Nothing to do.
                                    modify_plant(uid, new_name, new_id, new_ws_name, new_ws_id)
                                    st.success("Plant updated.")
                                    st.rerun()

                        # Show / Hide rain overlay (requires a production plant shown)
                        is_rain_on = (st.session_state.active_rain_uid == uid)
                        rain_label = "Hide rain data" if is_rain_on else "Show rain data"
                        if st.button(rain_label, use_container_width=True, key=f"toggle_rain_{uid}"):
                            if st.session_state.active_prod_uid != uid:
                                st.toast("Show the plant production first, then overlay rain.", icon="ℹ️")
                            else:
                                st.session_state.active_rain_uid = None if is_rain_on else uid
                                st.rerun()

                        # Delete with confirmation
                        confirm = st.session_state.delete_confirms.get(uid, False)
                        if not confirm:
                            if st.button("Delete", type="secondary", use_container_width=True, key=f"del_{uid}"):
                                st.session_state.delete_confirms[uid] = True
                                st.rerun()
                        else:
                            st.warning("Confirm delete?")
                            c1, c2 = st.columns(2)
                            if c1.button("Yes, delete", use_container_width=True, key=f"yes_{uid}"):
                                delete_plant_by_uid(uid)
                                st.toast("Plant deleted.", icon="🗑️")
                                st.rerun()
                            if c2.button("Cancel", use_container_width=True, key=f"no_{uid}"):
                                st.session_state.delete_confirms[uid] = False
                                st.rerun()