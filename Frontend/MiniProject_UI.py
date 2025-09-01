# app.py
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import random, math
import requests

# ===================== CONFIG =====================
API_BASE = "http://127.0.0.1:8000"  # FastAPI local

st.set_page_config(page_title="Hydro Software Services App", layout="wide")
st.title("Hydro Software Services App")

# ===================== API HELPERS =====================
# --- Stations ---
def api_get_stations():
    r = requests.get(f"{API_BASE}/stations", timeout=10)
    r.raise_for_status()
    return r.json()

def api_create_station(weather_station_code: str, weather_station_name: str):
    payload = {
        "weather_station_code": weather_station_code.strip(),
        "weather_station_name": weather_station_name.strip(),
    }
    r = requests.post(f"{API_BASE}/stations", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

def api_patch_station(code: str, new_name: str | None = None, new_code: str | None = None):
    payload = {}
    if new_name is not None:
        payload["weather_station_name"] = new_name.strip()
    if new_code is not None:
        payload["new_weather_station_code"] = new_code.strip()
    r = requests.patch(f"{API_BASE}/stations/{code}", json=payload, timeout=10)
    if r.status_code == 409:
        raise RuntimeError("A station with this new code already exists.")
    r.raise_for_status()
    return r.json()

def api_delete_station(code: str):
    r = requests.delete(f"{API_BASE}/stations/{code}", timeout=10)
    r.raise_for_status()
    return r.json()

# --- Plants ---
def api_get_plants():
    r = requests.get(f"{API_BASE}/plants", timeout=10)
    r.raise_for_status()
    return r.json()

def api_create_plant(hpp_code: str, hpp_name: str, weather_station_id: int | None):
    payload = {
        "hpp_code": hpp_code.strip(),
        "hpp_name": hpp_name.strip(),
        "weather_station_id": weather_station_id,
    }
    r = requests.post(f"{API_BASE}/plants", json=payload, timeout=10)
    if r.status_code == 409:
        raise RuntimeError("A plant with this code already exists.")
    r.raise_for_status()
    return r.json()

def api_patch_plant(
    hpp_code: str,
    hpp_name: str | None = None,
    weather_station_id: int | None = None,
    new_hpp_code: str | None = None,
):
    payload = {}
    if hpp_name is not None:
        payload["hpp_name"] = hpp_name.strip()
    # on envoie toujours la clé, None => délinker (côté API plants.py)
    payload["weather_station_id"] = weather_station_id
    if new_hpp_code:
        payload["new_hpp_code"] = new_hpp_code.strip()

    r = requests.patch(f"{API_BASE}/plants/{hpp_code}", json=payload, timeout=10)
    if r.status_code == 409:
        raise RuntimeError("A plant with this new code already exists.")
    r.raise_for_status()
    return r.json()

def api_delete_plant(hpp_code: str):
    r = requests.delete(f"{API_BASE}/plants/{hpp_code}", timeout=10)
    r.raise_for_status()
    return r.json()

# ===================== STATE INIT =====================
if "show_form" not in st.session_state:
    st.session_state.show_form = False
if "show_station_form" not in st.session_state:
    st.session_state.show_station_form = False

if "stations" not in st.session_state:
    st.session_state.stations = []
if "plants_api" not in st.session_state:
    st.session_state.plants_api = []

if "active_prod_id" not in st.session_state:
    st.session_state.active_prod_id = None
if "active_rain_id" not in st.session_state:
    st.session_state.active_rain_id = None

if "open_actions" not in st.session_state:
    st.session_state.open_actions = {}

if "confirm_plant_delete_code" not in st.session_state:
    st.session_state.confirm_plant_delete_code = None
if "confirm_ws_delete_code" not in st.session_state:
    st.session_state.confirm_ws_delete_code = None

def refresh_from_api():
    try:
        st.session_state.stations = api_get_stations()
    except Exception as e:
        st.warning(f"Could not load stations: {e}")
    try:
        st.session_state.plants_api = api_get_plants()
    except Exception as e:
        st.warning(f"Could not load plants: {e}")

# Bandeau de confirmation suppression Station (reste visible même si le popover s’est refermé)
if st.session_state.get("confirm_ws_delete_code"):
    code = st.session_state["confirm_ws_delete_code"]
    with st.container(border=True):
        st.warning(f"Delete weather station `{code}` ? Linked plants will be unlinked (FK SET NULL).")
        c1, c2 = st.columns(2)
        if c1.button("Yes, delete", use_container_width=True, key="ws_del_yes"):
            try:
                api_delete_station(code)
                st.toast("Station deleted.", icon="🗑️")
                st.session_state["confirm_ws_delete_code"] = None
                refresh_from_api()
                st.rerun()
            except Exception as e:
                st.error(f"API error: {e}")
        if c2.button("Cancel", use_container_width=True, key="ws_del_no"):
            st.session_state["confirm_ws_delete_code"] = None
            st.rerun()

# premier chargement
if not st.session_state.stations or not st.session_state.plants_api:
    refresh_from_api()

# ===================== HELPERS =====================
def station_label_from_id(stations: list[dict], ws_id: int | None) -> str:
    if not ws_id:
        return "—"
    s = next((x for x in stations if x["id"] == ws_id), None)
    if not s:
        return f"id={ws_id}"
    return f"{s['weather_station_code']} ({s['weather_station_name']})"

# ===================== DUMMY SERIES (provisoirement) =====================
def date_window_last_30_to_yesterday():
    today = datetime.now().date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=29)
    return pd.date_range(start, end, freq="D")

def placeholder_production_series(idx: pd.DatetimeIndex):
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
        if r < 0.1:
            vals.append(round(rnd.uniform(8, 20), 1))
        elif r < 0.4:
            vals.append(round(rnd.uniform(0.5, 5), 1))
        else:
            vals.append(0.0)
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
        bargap=0.15,
        hovermode="x unified",
        height=460,
    )
    return fig

# ===================== LAYOUT =====================
left, right = st.columns([2.4, 1.2], gap="large")

# -------- LEFT: Chart --------
with left:
    st.subheader("Plant production")
    if st.session_state.active_prod_id is None:
        st.info("No plant selected yet. Open actions on a plant → “Show hydro power plant production”.")
    else:
        plant = next((p for p in st.session_state.plants_api if p["id"] == st.session_state.active_prod_id), None)
        idx = date_window_last_30_to_yesterday()
        prod = placeholder_production_series(idx)
        rain = None
        if plant and st.session_state.active_rain_id == plant["id"]:
            # temporaire : pluie simulée tant que /rain n’est pas branché dans l’UI
            rain = placeholder_rain_series(idx, seed_text=plant["hpp_code"])
        st.plotly_chart(build_fig(prod, rain), use_container_width=True)
        if plant:
            ws_text = f"Weather station: {station_label_from_id(st.session_state.stations, plant['weather_station_id'])}"
            st.caption(
                f"Window: last 30 days up to yesterday • Showing: **{plant['hpp_name']}** "
                f"(Code `{plant['hpp_code']}` • DB id {plant['id']}) • {ws_text}"
            )

# -------- RIGHT: Forms & lists --------
with right:
    # --- Create plant (FIRST) ---
    st.subheader("Add a power plant")
    if st.button("➕ Add a power plant", use_container_width=True, key="btn_add_open"):
        st.session_state.show_form = True
    if st.session_state.show_form:
        with st.form(key="create_plant_form", border=True):
            st.markdown("**Create a new Hydropower Plant**")
            name = st.text_input("Hydro Power Plant name",
                                 placeholder="e.g., Breuchin Small Hydro #1", key="new_plant_name")
            code = st.text_input("Hydro Power Plant code",
                                 placeholder="e.g., HPP-0001", key="new_plant_code")

            station_options = ["(no station)"] + [
                f"{s['id']} — {s['weather_station_code']} — {s['weather_station_name']}"
                for s in st.session_state.stations
            ]
            choice = st.selectbox("Link to weather station (optional)", station_options, index=0)
            chosen_station_id = None if choice == "(no station)" else int(choice.split(" — ", 1)[0])

            if st.form_submit_button("Save", use_container_width=True):
                if not name.strip() or not code.strip():
                    st.error("Both name and code are required.")
                else:
                    try:
                        res = api_create_plant(hpp_code=code, hpp_name=name,
                                               weather_station_id=chosen_station_id)
                        st.success(f"Plant saved in DB (id={res.get('id')}).")
                        st.session_state.show_form = False
                        refresh_from_api()
                        st.rerun()
                    except Exception as e:
                        st.error(f"API error: {e}")

    st.divider()

    # --- Create station (SECOND) ---
    st.subheader("Add a weather station")
    if st.button("➕ Add a weather station", use_container_width=True, key="btn_add_station_open"):
        st.session_state.show_station_form = True
    if st.session_state.get("show_station_form", False):
        with st.form(key="create_station_form", border=True):
            st.markdown("**Create a new Weather Station**")
            ws_code = st.text_input("Weather station **numeric id** (Météo-France)", placeholder="e.g., 70473001")
            ws_name = st.text_input("Weather station **name**", placeholder="e.g., Luxeuil")
            if st.form_submit_button("Save station", use_container_width=True):
                if not ws_code.strip() or not ws_name.strip():
                    st.error("Both code and name are required.")
                else:
                    try:
                        res = api_create_station(ws_code, ws_name)
                        st.success(f"Station saved (status={res.get('status')}, id={res.get('id')}).")
                        st.session_state.show_station_form = False
                        refresh_from_api()
                        st.rerun()
                    except Exception as e:
                        st.error(f"API error: {e}")

    st.divider()

    # --- Manage stations (popover) ---
    with st.popover("Manage weather stations"):
        st.write("All registered weather stations.")
        if not st.session_state.stations:
            st.info("No stations yet.")
        else:
            for s in st.session_state.stations:
                code = s["weather_station_code"]
                name = s["weather_station_name"]
                with st.container(border=True):
                    st.caption(f"Code: `{code}` • DB id: {s['id']}")
                    c1, c2 = st.columns(2)
                    new_name = c1.text_input(f"Name — {code}", value=name, key=f"ws_edit_name_{code}")
                    new_code = c2.text_input(f"Code — {code}", value=code, key=f"ws_edit_code_{code}")
                    b1, b2 = st.columns([0.6, 0.4])
                    if b1.button("Save changes", key=f"ws_save_{code}", use_container_width=True):
                        try:
                            code_change = new_code.strip() if new_code.strip() != code else None
                            api_patch_station(code, new_name=new_name, new_code=code_change)
                            st.success("Station updated.")
                            refresh_from_api()
                            st.rerun()
                        except Exception as e:
                            st.error(f"API error: {e}")
                    if b2.button("Delete", key=f"ws_del_{code}", use_container_width=True):
                        st.session_state.confirm_ws_delete_code = code
                        st.rerun()

    st.divider()

    # --- List plants (from DB) + actions ---
    st.subheader("Saved plants (from DB)")
    if not st.session_state.plants_api:
        st.info("No plants yet.")
    else:
        for p in st.session_state.plants_api:
            pid = p["id"]  # PK interne
            st.session_state.open_actions.setdefault(pid, False)
            with st.container(border=True):
                top = st.columns([0.85, 0.15])
                with top[0]:
                    st.markdown(f"**{p['hpp_name']}**")
                    st.caption(f"Code: `{p['hpp_code']}` • DB id: {p['id']}")
                    st.write(f"Weather station: {station_label_from_id(st.session_state.stations, p['weather_station_id'])}")
                with top[1]:
                    if st.button("⋯", key=f"toggle_actions_{pid}", use_container_width=True):
                        st.session_state.open_actions[pid] = not st.session_state.open_actions[pid]
                        st.rerun()

                if st.session_state.open_actions[pid]:
                    with st.container(border=True):
                        st.markdown("**Actions**")

                        # Show/Hide production
                        show_prod = (st.session_state.active_prod_id == pid)
                        prod_label = "Hide hydro power plant production" if show_prod else "Show hydro power plant production"
                        if st.button(prod_label, use_container_width=True, key=f"show_prod_{pid}"):
                            st.session_state.active_prod_id = None if show_prod else pid
                            if st.session_state.active_prod_id is None and st.session_state.active_rain_id == pid:
                                st.session_state.active_rain_id = None
                            st.rerun()

                        # Show / Hide rain overlay (dummy until real /rain hookup)
                        is_rain_on = (st.session_state.active_rain_id == pid)
                        rain_label = "Hide rain data" if is_rain_on else "Show rain data"
                        if st.button(rain_label, use_container_width=True, key=f"toggle_rain_{pid}"):
                            if st.session_state.active_prod_id != pid:
                                st.toast("Show the plant production first, then overlay rain.", icon="ℹ️")
                            else:
                                st.session_state.active_rain_id = None if is_rain_on else pid
                                st.rerun()

                        # ---- Edit (PATCH name + code + station) ----
                        with st.expander("Edit plant", expanded=False):
                            new_name = st.text_input(
                                f"Plant name (edit) — {p['hpp_code']}",
                                value=p["hpp_name"], key=f"edit_name_{pid}"
                            )
                            new_code = st.text_input(
                                f"Plant code (edit) — {p['hpp_code']}",
                                value=p["hpp_code"], key=f"edit_code_{pid}"
                            )

                            station_options2 = ["(no station)"] + [
                                f"{s['id']} — {s['weather_station_code']} — {s['weather_station_name']}"
                                for s in st.session_state.stations
                            ]
                            if p.get("weather_station_id"):
                                pre_label = None
                                for s in st.session_state.stations:
                                    if s["id"] == p["weather_station_id"]:
                                        pre_label = f"{s['id']} — {s['weather_station_code']} — {s['weather_station_name']}"
                                        break
                                idx_pre = station_options2.index(pre_label) if pre_label in station_options2 else 0
                            else:
                                idx_pre = 0

                            choice2 = st.selectbox(
                                "Linked weather station", station_options2, index=idx_pre, key=f"edit_station_{pid}"
                            )
                            chosen_station_id2 = None if choice2 == "(no station)" else int(choice2.split(" — ", 1)[0])

                            if st.button("Save changes", use_container_width=True, key=f"save_edit_{pid}"):
                                try:
                                    api_patch_plant(
                                        hpp_code=p["hpp_code"],
                                        hpp_name=new_name if new_name.strip() != p["hpp_name"] else None,
                                        weather_station_id=chosen_station_id2,
                                        new_hpp_code=new_code.strip() if new_code.strip() != p["hpp_code"] else None,
                                    )
                                    st.success("Plant updated.")
                                    refresh_from_api()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"API error: {e}")

                        # ---- Delete plant (DELETE) avec confirmation persistante ----
                        if st.session_state.confirm_plant_delete_code == p["hpp_code"]:
                            st.warning("Confirm delete this plant?")
                            c1, c2 = st.columns(2)
                            if c1.button("Yes, delete", use_container_width=True, key=f"confirm_yes_{pid}"):
                                try:
                                    api_delete_plant(p["hpp_code"])
                                    st.toast("Plant deleted.", icon="🗑️")
                                    if st.session_state.active_prod_id == pid:
                                        st.session_state.active_prod_id = None
                                    if st.session_state.active_rain_id == pid:
                                        st.session_state.active_rain_id = None
                                    st.session_state.confirm_plant_delete_code = None
                                    refresh_from_api()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"API error: {e}")
                            if c2.button("Cancel", use_container_width=True, key=f"confirm_no_{pid}"):
                                st.session_state.confirm_plant_delete_code = None
                                st.rerun()
                        else:
                            if st.button("Delete", type="secondary", use_container_width=True, key=f"del_{pid}"):
                                st.session_state.confirm_plant_delete_code = p["hpp_code"]
                                st.rerun()