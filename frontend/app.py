import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import requests
import json
import os
import copy
import sys
import branca.colormap as cm

# Add project root to python path to import forecasting locally
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up Streamlit Page Configuration
st.set_page_config(
    page_title="Prediktivní Sociální Atlas Ústeckého kraje",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration and Fetch Helper
API_URL = "http://localhost:8000"

@st.cache_data(ttl=3600)
def _fetch_data_cached(endpoint, params_json=None):
    params = json.loads(params_json) if params_json else None
    try:
        response = requests.get(f"{API_URL}{endpoint}", params=params, timeout=2)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass

    # Local Fallback Engine
    return fallback_fetch(endpoint, params)

def fetch_data(endpoint, params=None):
    """
    Attempt to fetch data from the FastAPI backend.
    Uses Streamlit caching to avoid redundant HTTP requests and JSON parsing on reruns.
    """
    params_json = json.dumps(params, sort_keys=True) if params else None
    return _fetch_data_cached(endpoint, params_json)

def fallback_fetch(endpoint, params=None):
    """
    Local data loader and calculation engine used if FastAPI backend is offline.
    """
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    if endpoint == "/api/orp/geojson":
        filepath = os.path.join(data_dir, "orp_usti.geojson")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    elif endpoint == "/api/orp/indicators":
        filepath = os.path.join(data_dir, "social_indicators.json")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    elif endpoint == "/api/orp/demographics":
        filepath = os.path.join(data_dir, "demographics_historical.json")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    elif endpoint == "/api/social-services":
        filepath = os.path.join(data_dir, "social_services.json")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    elif endpoint == "/api/orp/cssz":
        filepath = os.path.join(data_dir, "cssz_data.json")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    elif endpoint == "/api/predictions":
        year = int(params.get("year", 2030) if params else 2030)
        threshold = float(params.get("capacity_deficit_threshold", 20.0) if params else 20.0)

        from backend.forecasting import calculate_capacity_deficit
        filepath = os.path.join(data_dir, "social_indicators.json")
        with open(filepath, "r", encoding="utf-8") as f:
            indicators = json.load(f)

        predictions = {}
        for orp in indicators.keys():
            deficit_info = calculate_capacity_deficit(orp, year)
            predictions[orp] = {
                "orp": orp,
                "year": year,
                **deficit_info,
                "stress_alert": deficit_info["deficit_percent"] >= threshold,
                "unemployment_rate": indicators[orp]["unemployment_rate"],
                "exekuce_rate": indicators[orp]["exekuce_rate"],
                "excluded_localities_ratio": indicators[orp]["excluded_localities_ratio"]
            }
        return predictions

    elif endpoint == "/api/white-spots":
        year = int(params.get("year", 2030) if params else 2030)
        from backend.forecasting import get_white_spots
        return get_white_spots(year)

    else:
        raise ValueError(f"Unknown endpoint: {endpoint}")

# Helper to extract ORP name from streamlit-folium click output
def get_clicked_orp_name(map_output):
    if not map_output:
        return None
    click_info = map_output.get("last_object_clicked")
    if not click_info:
        return None
    if isinstance(click_info, dict):
        properties = click_info.get("properties")
        if isinstance(properties, dict):
            name = properties.get("name")
            if name:
                return name
        # If not in properties, try the 'id' field
        feature_id = click_info.get("id")
        if feature_id and isinstance(feature_id, str):
            return feature_id
    elif isinstance(click_info, str):
        return click_info
    return None

# Helper to load and inject custom stylesheet
def local_css(file_name):
    with open(file_name, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Load styling
css_path = os.path.join(os.path.dirname(__file__), "style.css")
if os.path.exists(css_path):
    local_css(css_path)

# Initialize Session State
if "selected_orp" not in st.session_state:
    st.session_state.selected_orp = "Celý kraj"

# Fetch global datasets
try:
    indicators = fetch_data("/api/orp/indicators")
    services = fetch_data("/api/social-services")
    geojson_data = fetch_data("/api/orp/geojson")
    cssz_data = fetch_data("/api/orp/cssz")
    demographics_data = fetch_data("/api/orp/demographics")
except Exception as e:
    st.error(f"Nepodařilo se načíst základní data. Zkontrolujte prosím přítomnost souborů ve složce data/. Detaily: {e}")
    st.stop()

# Ensure each GeoJSON feature has the name as its root ID for Folium click mapping
for feature in geojson_data.get("features", []):
    feature["id"] = feature["properties"]["name"]

# ----------------- SIDEBAR PANEL -----------------
st.sidebar.markdown("""
<div style="text-align: center; padding-bottom: 10px;">
    <h2 style="color: #ffffff; font-weight: 800; margin-bottom: 0px;">NASTAVENÍ</h2>
    <span style="color: #525a7a; font-size: 0.85rem;">PREDIKTIVNÍ ATLAS</span>
</div>
""", unsafe_allow_html=True)

# Selected ORP selector
orp_options = ["Celý kraj"] + sorted(list(indicators.keys()))
try:
    default_idx = orp_options.index(st.session_state.selected_orp)
except ValueError:
    default_idx = 0

selected_orp = st.sidebar.selectbox(
    "Vyberte území (ORP):",
    orp_options,
    index=default_idx,
    key="orp_sidebar_select"
)

# Sync sidebar select back to session state
if selected_orp != st.session_state.selected_orp:
    st.session_state.selected_orp = selected_orp
    st.rerun()

st.sidebar.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 15px 0px;'/>", unsafe_allow_html=True)

# Map visual options
st.sidebar.subheader("Vrstvy mapy (Sociální Atlas)")
selected_indicator_label = st.sidebar.selectbox(
    "Zobrazovaný indikátor:",
    [
        "Míra nezaměstnanosti (%)",
        "Podíl obyvatel v exekuci (%)",
        "Podíl vyloučených lokalit (%)",
        "Kriminalita na 1000 obyv.",
        "Příspěvky na bydlení na 1000 obyv."
    ]
)

# Mapping selections to data keys
INDICATOR_MAPPING = {
    "Míra nezaměstnanosti (%)": ("unemployment_rate", "%", "unemployment_rate", cm.linear.YlOrRd_09),
    "Podíl obyvatel v exekuci (%)": ("exekuce_rate", "%", "exekuce_rate", cm.linear.OrRd_09),
    "Podíl vyloučených lokalit (%)": ("excluded_localities_ratio", "%", "excluded_localities_ratio", cm.linear.Reds_09),
    "Kriminalita na 1000 obyv.": ("crime_rate_per_1k", "případů", "crime_rate_per_1k", cm.linear.Purples_09),
    "Příspěvky na bydlení na 1000 obyv.": ("housing_benefits_per_1k", "příjemců", "housing_benefits_per_1k", cm.linear.PuRd_09)
}

indicator_key, indicator_unit, indicator_title, colormap_fn = INDICATOR_MAPPING[selected_indicator_label]

st.sidebar.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 15px 0px;'/>", unsafe_allow_html=True)

st.sidebar.subheader("Zobrazit body zájmu (POI):")
show_stationary = st.sidebar.checkbox("Pobytová zařízení (red)", value=True)
show_field = st.sidebar.checkbox("Terénní služby (green)", value=True)
show_shelters = st.sidebar.checkbox("Azylové domy (blue)", value=False)

# Add sidebar context info
st.sidebar.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 15px 0px;'/>", unsafe_allow_html=True)
st.sidebar.markdown("""
<div class="metric-card" style="padding: 15px !important; margin: 0px !important;">
    <div style="font-size: 0.75rem; color: #8c96bc; font-weight: 600; text-transform: uppercase;">Aktivní území</div>
    <div style="font-size: 1.15rem; color: #ffffff; font-weight: 800; margin-top: 5px;">""" + selected_orp + """</div>
</div>
""", unsafe_allow_html=True)


# ----------------- MAIN APP CONTENT -----------------

# Header Section
st.markdown("""
<div style="text-align: center; margin-top: 10px; margin-bottom: 30px;">
    <h1 class="header-title" style="font-size: 2.8rem; margin-bottom: 0px; text-transform: uppercase;">Prediktivní Sociální Atlas</h1>
    <h3 class="header-subtitle" style="font-size: 1.15rem; margin-top: 5px;">Ústecký kraj &bull; Systém podpory rozhodování a modelování budoucích kapacit sociálních služeb</h3>
</div>
""", unsafe_allow_html=True)

# Helper function to render metric cards mapping to CSS classes
def render_metric_card(label, value, trend_text="", trend_direction="none", extra_class=""):
    trend_html = ""
    if trend_direction == "up":
        trend_html = f'<div class="metric-trend trend-up">▲ {trend_text}</div>'
    elif trend_direction == "down":
        trend_html = f'<div class="metric-trend trend-down">▼ {trend_text}</div>'
    elif trend_text:
        trend_html = f'<div class="metric-trend">{trend_text}</div>'

    st.markdown(f"""
    <div class="metric-card {extra_class}">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {trend_html}
    </div>
    """, unsafe_allow_html=True)

# Create App Tabs (Excluding LLM/AI Assistant completely)
tab_atlas, tab_predictions, tab_exports, tab_cssz = st.tabs([
    "📂 SOCIÁLNÍ ATLAS (Současnost)",
    "📈 PREDIKTIVNÍ MODEL (2026–2035)",
    "📊 ANALÝZA A EXPORT DAT",
    "🏥 DATA ČSSZ (Dávky a důchody)"
])

# ----------------- TAB 1: SOCIÁLNÍ ATLAS -----------------
with tab_atlas:
    st.markdown("<h4 style='color: #ffffff; font-weight: 600; margin-bottom: 15px;'>Současná sociální a demografická situace</h4>", unsafe_allow_html=True)

    # 1. Row of KPI metric cards
    col1, col2, col3, col4 = st.columns(4)

    # Calculations based on selected ORP
    if selected_orp == "Celý kraj":
        total_pop_2025 = sum(dem[2025-2018]["total_pop"] for dem in fetch_data("/api/orp/demographics").values())
        avg_unemployment = round(np.mean([ind["unemployment_rate"] for ind in indicators.values()]), 1)
        avg_exekuce = round(np.mean([ind["exekuce_rate"] for ind in indicators.values()]), 1)
        total_capacity = sum(s["capacity"] for s in services)

        with col1:
            render_metric_card("Celková populace kraje (2025)", f"{total_pop_2025:,}".replace(",", " "), "Stabilní vývoj", "none")
        with col2:
            render_metric_card("Průměrná nezaměstnanost", f"{avg_unemployment} %", "Nejvyšší v ČR", "up")
        with col3:
            render_metric_card("Podíl obyvatel v exekuci", f"{avg_exekuce} %", "Závažný socioekonomický stres", "up")
        with col4:
            render_metric_card("Celková lůžková kapacita (DS)", f"{total_capacity} lůžek", f"Celkem {len(services)} poskytovatelů", "none")
    else:
        hist_dem = fetch_data("/api/orp/demographics")[selected_orp]
        pop_2025 = hist_dem[-1]["total_pop"]
        unemp = indicators[selected_orp]["unemployment_rate"]
        exek = indicators[selected_orp]["exekuce_rate"]
        orp_capacity = sum(s["capacity"] for s in services if s["orp"] == selected_orp)

        with col1:
            render_metric_card(f"Populace - {selected_orp} (2025)", f"{pop_2025:,}".replace(",", " "), "Dle dat ČSÚ", "none")
        with col2:
            render_metric_card("Míra nezaměstnanosti", f"{unemp} %", "Krajský průměr: 6.7%", "up" if unemp > 6.7 else "down")
        with col3:
            render_metric_card("Podíl obyvatel v exekuci", f"{exek} %", "Krajský průměr: 13.5%", "up" if exek > 13.5 else "down")
        with col4:
            render_metric_card("Lůžková kapacita (DS)", f"{orp_capacity} lůžek", f"V ORP {selected_orp}", "none")

    st.markdown("<br/>", unsafe_allow_html=True)

    # 2. Main Visualization Row: Map (left) + Side Comparison charts (right)
    col_map, col_chart = st.columns([5, 4])

    with col_map:
        st.markdown(f"<div style='font-size: 0.9rem; color: #8c96bc; margin-bottom: 10px; font-weight: 600;'>KARTOGRAFICKÉ ZOBRAZENÍ: {selected_indicator_label}</div>", unsafe_allow_html=True)

        # Prepare Map
        # Base map centering Ústí region
        m = folium.Map(location=[50.55, 13.90], zoom_start=9, tiles="cartodbpositron")

        # Merge selected indicator value into GeoJSON feature properties for tooltip
        map_geo = copy.deepcopy(geojson_data)
        values = [ind[indicator_key] for ind in indicators.values()]
        min_val, max_val = min(values), max(values)

        # Initialize color map
        colormap = colormap_fn.scale(min_val, max_val)
        colormap.caption = f"{selected_indicator_label}"
        colormap.add_to(m)

        for feature in map_geo.get("features", []):
            name = feature["properties"]["name"]
            val = indicators.get(name, {}).get(indicator_key, 0.0)
            feature["properties"]["indicator_val"] = val
            feature["properties"]["indicator_label"] = selected_indicator_label

        def style_fn(feature):
            val = feature["properties"].get("indicator_val", 0.0)
            # Custom styling function
            name = feature["properties"]["name"]
            is_selected = (name == selected_orp)
            return {
                "fillColor": colormap(val),
                "color": "#ffffff" if is_selected else "#444444",
                "weight": 3 if is_selected else 1.2,
                "fillOpacity": 0.75 if is_selected else 0.55,
            }

        def highlight_fn(feature):
            return {
                "weight": 3,
                "color": "#ffffff",
                "fillOpacity": 0.85
            }

        tooltip_widget = folium.GeoJsonTooltip(
            fields=["name", "indicator_val"],
            aliases=["ORP:", "Hodnota:"],
            localize=True,
            sticky=True,
            labels=True
        )

        folium.GeoJson(
            map_geo,
            style_function=style_fn,
            highlight_function=highlight_fn,
            tooltip=tooltip_widget,
            name="ORP Hranice"
        ).add_to(m)

        # Overlay Social Services markers
        fg_stationary = folium.FeatureGroup(name="Pobytová zařízení (DS)", show=show_stationary)
        fg_field = folium.FeatureGroup(name="Terénní služby", show=show_field)
        fg_shelters = folium.FeatureGroup(name="Azylové domy", show=show_shelters)

        for s in services:
            # Highlight only current ORP markers if specific ORP is selected
            if selected_orp != "Celý kraj" and s["orp"] != selected_orp:
                continue

            popup_html = f"""
            <div style="font-family: 'Outfit', sans-serif; font-size: 0.85rem; color: #111;">
                <h5 style="margin: 0px 0px 5px 0px; font-weight: 700;">{s['name']}</h5>
                <b>Typ služby:</b> {s['type']}<br/>
                <b>Adresa:</b> {s['address']}<br/>
                <b>Lůžková kapacita:</b> {s['capacity']}<br/>
                <b>Obsazenost:</b> {s['filled']} / {s['capacity']} ({int(s['filled']/s['capacity']*100)}%)
            </div>
            """
            iframe = folium.IFrame(popup_html, width=280, height=130)
            popup_obj = folium.Popup(iframe, max_width=280)

            if "Stationary Care" in s["type"]:
                if show_stationary:
                    folium.Marker(
                        location=[s["lat"], s["lon"]],
                        popup=popup_obj,
                        icon=folium.Icon(color="red", icon="home", prefix="fa"),
                        tooltip=s["name"]
                    ).add_to(fg_stationary)
            elif "Field Care" in s["type"]:
                if show_field:
                    folium.Marker(
                        location=[s["lat"], s["lon"]],
                        popup=popup_obj,
                        icon=folium.Icon(color="green", icon="heart", prefix="fa"),
                        tooltip=s["name"]
                    ).add_to(fg_field)
            else:
                if show_shelters:
                    folium.Marker(
                        location=[s["lat"], s["lon"]],
                        popup=popup_obj,
                        icon=folium.Icon(color="blue", icon="shield", prefix="fa"),
                        tooltip=s["name"]
                    ).add_to(fg_shelters)

        if show_stationary:
            fg_stationary.add_to(m)
        if show_field:
            fg_field.add_to(m)
        if show_shelters:
            fg_shelters.add_to(m)

        # Render Folium Map in Streamlit
        map_output = st_folium(m, height=450, width='stretch', key="atlas_map")

        # Check map selection click and update selected ORP
        clicked_name = get_clicked_orp_name(map_output)
        if clicked_name and clicked_name in indicators.keys() and clicked_name != st.session_state.selected_orp:
            st.session_state.selected_orp = clicked_name
            st.rerun()

    with col_chart:
        # Side comparison bar chart
        st.markdown("<div style='font-size: 0.9rem; color: #8c96bc; margin-bottom: 10px; font-weight: 600;'>POROVNÁNÍ NAPŘÍČ OBLASTMI</div>", unsafe_allow_html=True)

        comp_list = []
        for orp_name, ind in indicators.items():
            comp_list.append({
                "ORP": orp_name,
                "Hodnota": ind[indicator_key],
                "Skupina": "Vybraná oblast" if orp_name == selected_orp else "Ostatní ORP"
            })
        df_comp = pd.DataFrame(comp_list).sort_values(by="Hodnota", ascending=True)

        fig_comp = px.bar(
            df_comp,
            x="Hodnota",
            y="ORP",
            orientation="h",
            color="Skupina",
            color_discrete_map={"Vybraná oblast": "#ff4b4b", "Ostatní ORP": "#282c3c"},
            labels={"Hodnota": f"{selected_indicator_label} [{indicator_unit}]", "ORP": ""},
            height=430
        )
        fig_comp.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)")
        )
        st.plotly_chart(fig_comp, width='stretch')

# ----------------- TAB 2: PREDIKTIVNÍ MODEL -----------------
with tab_predictions:
    st.markdown("<h4 style='color: #ffffff; font-weight: 600; margin-bottom: 15px;'>Predikce a modelování kapacit pobytové péče (2026–2035)</h4>", unsafe_allow_html=True)

    # Parameter sliders
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        pred_year = st.slider("Cílový rok projekce:", min_value=2026, max_value=2035, value=2030, step=1)
    with col_s2:
        deficit_threshold = st.slider("Kritický kapacitní deficit (%):", min_value=0.0, max_value=50.0, value=20.0, step=5.0,
                                      help="Hodnota kapacitního deficitu, nad kterou je oblast označena varovnou červenou barvou z důvodu ohrožení nedostatečnou kapacitou.")

    st.markdown("<br/>", unsafe_allow_html=True)

    # Fetch predictions for targeted year and threshold
    predictions_val = fetch_data("/api/predictions", {"year": pred_year, "capacity_deficit_threshold": deficit_threshold})

    # 1. Highlight Capacity Deficits KPI Cards
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)

    if selected_orp == "Celý kraj":
        total_capacity_2025 = sum(p["current_capacity"] for p in predictions_val.values())
        total_demand_pred = sum(p["predicted_demand"] for p in predictions_val.values())
        weighted_deficit_pct = round(((total_demand_pred - total_capacity_2025) / total_capacity_2025) * 100.0, 1) if total_capacity_2025 > 0 else 0
        stressed_orps_count = sum(1 for p in predictions_val.values() if p["stress_alert"])

        with col_p1:
            render_metric_card(f"Předpovídaná poptávka kraje ({pred_year})", f"{total_demand_pred:,}".replace(",", " ") + " lůžek", "Založeno na stárnutí 75+", "none")
        with col_p2:
            render_metric_card("Stabilní kapacita lůžek", f"{total_capacity_2025:,}".replace(",", " ") + " lůžek", "Současný stav v kraji", "none")
        with col_p3:
            is_crit = weighted_deficit_pct >= deficit_threshold
            render_metric_card(
                "Celkový deficit kraje",
                f"{weighted_deficit_pct} %",
                "Průměrný deficit kapacit",
                "up" if weighted_deficit_pct > 0 else "none",
                extra_class="glow-alert" if is_crit else ""
            )
        with col_p4:
            render_metric_card(
                "Počet ORP v kritickém deficitu",
                f"{stressed_orps_count} / 16",
                f"Deficit > {deficit_threshold}%",
                "up" if stressed_orps_count > 0 else "none",
                extra_class="glow-alert" if stressed_orps_count > 4 else ""
            )
    else:
        orp_pred = predictions_val[selected_orp]
        demand_pred = orp_pred["predicted_demand"]
        cap_2025 = orp_pred["current_capacity"]
        def_pct = orp_pred["deficit_percent"]
        growth_75plus = round(((orp_pred["pop_75plus"] - orp_pred["hist_2025_pop_75plus"]) / orp_pred["hist_2025_pop_75plus"]) * 100.0, 1)

        with col_p1:
            render_metric_card(f"Očekávaná poptávka ({pred_year})", f"{demand_pred} lůžek", f"Pop. 75+: {orp_pred['pop_75plus']} obyv.", "none")
        with col_p2:
            render_metric_card("Stávající kapacita lůžek", f"{cap_2025} lůžek", f"V ORP {selected_orp}", "none")
        with col_p3:
            is_crit = orp_pred["stress_alert"]
            render_metric_card(
                "Deficit kapacit",
                f"{def_pct} %",
                f"Srovnání poptávky s kapacitou",
                "up" if def_pct > 0 else "none",
                extra_class="glow-alert" if is_crit else ""
            )
        with col_p4:
            render_metric_card("Nárůst seniorů 75+ (do r. " + str(pred_year) + ")", f"+ {growth_75plus} %", "Oproti roku 2025", "up")

    st.markdown("<br/>", unsafe_allow_html=True)

    # 2. Prediction Maps & Demographic Trend Plots
    col_p_map, col_p_chart = st.columns([5, 4])

    with col_p_map:
        st.markdown(f"<div style='font-size: 0.9rem; color: #8c96bc; margin-bottom: 10px; font-weight: 600;'>KAPACITNÍ DEFICITY V ROCE {pred_year} (ČERVENÁ = ALARM DEFICITU > {deficit_threshold}%)</div>", unsafe_allow_html=True)

        m_pred = folium.Map(location=[50.55, 13.90], zoom_start=9, tiles="cartodbpositron")
        pred_geo = copy.deepcopy(geojson_data)

        for feature in pred_geo.get("features", []):
            name = feature["properties"]["name"]
            pred = predictions_val.get(name, {})
            feature["properties"]["current_capacity"] = pred.get("current_capacity", 0)
            feature["properties"]["predicted_demand"] = pred.get("predicted_demand", 0)
            feature["properties"]["deficit_percent"] = pred.get("deficit_percent", 0.0)
            feature["properties"]["stress_alert"] = pred.get("stress_alert", False)

        def pred_style_fn(feature):
            name = feature["properties"]["name"]
            alert = feature["properties"].get("stress_alert", False)
            deficit = feature["properties"].get("deficit_percent", 0.0)
            is_selected = (name == selected_orp)

            if alert:
                fill_col = "#dc3545" # warning alert red
                line_weight = 3 if is_selected else 1.5
            elif deficit > 0:
                fill_col = "#ff9f1c" # warning moderate orange
                line_weight = 3 if is_selected else 1.2
            else:
                fill_col = "#2ec4b6" # satisfactory green
                line_weight = 3 if is_selected else 1.0

            return {
                "fillColor": fill_col,
                "color": "#ffffff" if is_selected else "#444444",
                "weight": line_weight,
                "fillOpacity": 0.7 if is_selected else 0.5,
            }

        def pred_highlight_fn(feature):
            return {
                "weight": 3.5,
                "color": "#ffffff",
                "fillOpacity": 0.8
            }

        tooltip_pred = folium.GeoJsonTooltip(
            fields=["name", "current_capacity", "predicted_demand", "deficit_percent"],
            aliases=["ORP:", "Kapacita lůžek:", "Očekávaná poptávka:", "Kapacitní deficit (%):"],
            localize=True,
            sticky=True,
            labels=True
        )

        folium.GeoJson(
            pred_geo,
            style_function=pred_style_fn,
            highlight_function=pred_highlight_fn,
            tooltip=tooltip_pred,
            name="Predikce Deficitu"
        ).add_to(m_pred)

        map_pred_output = st_folium(m_pred, height=450, width='stretch', key="prediction_map")

        # Click handler for prediction map
        clicked_name = get_clicked_orp_name(map_pred_output)
        if clicked_name and clicked_name in indicators.keys() and clicked_name != st.session_state.selected_orp:
            st.session_state.selected_orp = clicked_name
            st.rerun()

    with col_p_chart:
        # Chart displaying population trends
        st.markdown("<div style='font-size: 0.9rem; color: #8c96bc; margin-bottom: 10px; font-weight: 600;'>DEMOGRAFICKÝ VÝVOJ A PROJEKCE POPULACE</div>", unsafe_allow_html=True)

        active_orp = selected_orp if selected_orp != "Celý kraj" else "Ústí nad Labem" # Default to regional center if whole region is selected

        # Load historical & future forecast timeline for trend visualization
        hist_data = fetch_data("/api/orp/demographics")[active_orp]

        # Calculate future list via import
        from backend.forecasting import get_forecast_for_orp
        future_list = []
        for y in range(2026, 2036):
            forecast = get_forecast_for_orp(active_orp, y)
            if forecast:
                future_list.append({
                    "year": y,
                    "total_pop": forecast["total_pop"],
                    "pop_65plus": forecast["pop_65plus"],
                    "pop_75plus": forecast["pop_75plus"],
                    "net_migration": forecast["net_migration"]
                })

        df_hist = pd.DataFrame(hist_data)
        df_hist["typ"] = "Historická data"
        df_fut = pd.DataFrame(future_list)
        df_fut["typ"] = "Demografická projekce"
        df_all = pd.concat([df_hist, df_fut], ignore_index=True)

        fig_trend = go.Figure()
        # Total Population Plot (secondary axis or separate line)
        fig_trend.add_trace(go.Scatter(
            x=df_all["year"], y=df_all["total_pop"],
            name="Celková populace",
            line=dict(color="#4285f4", width=3)
        ))
        # Seniors 65+
        fig_trend.add_trace(go.Scatter(
            x=df_all["year"], y=df_all["pop_65plus"],
            name="Senioři 65+",
            line=dict(color="#ff9f1c", width=2, dash="dash")
        ))
        # Seniors 75+
        fig_trend.add_trace(go.Scatter(
            x=df_all["year"], y=df_all["pop_75plus"],
            name="Senioři 75+",
            line=dict(color="#dc3545", width=2, dash="dot")
        ))

        # Highlight projection split
        fig_trend.add_vline(x=2025.5, line_width=1, line_dash="dash", line_color="#8c96bc")
        fig_trend.add_annotation(x=2024.5, y=df_all["total_pop"].max() * 0.95, text="Historie", showarrow=False, font=dict(color="#8c96bc"))
        fig_trend.add_annotation(x=2027.5, y=df_all["total_pop"].max() * 0.95, text="Projekce", showarrow=False, font=dict(color="#8c96bc"))

        fig_trend.update_layout(
            title=dict(text=f"Vývoj věkové struktury: {active_orp}", font=dict(size=14, color="#ffffff")),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)", dtick=2),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)")
        )
        st.plotly_chart(fig_trend, width='stretch')

    st.markdown("<hr style='border-color: rgba(255,255,255,0.05); margin: 30px 0px;'/>", unsafe_allow_html=True)

    # 3. White Spots Index Ranking
    st.markdown(f"<h5 style='color: #ffffff; font-weight: 600; margin-bottom: 15px;'>Identifikace \"Bílých míst\" (Nepokrytá území s vysokým rizikem v roce {pred_year})</h5>", unsafe_allow_html=True)

    # Toggle to show White Spot analysis
    show_white_spots = st.checkbox("Zobrazit detailní analýzu Bílých míst (White Spots Index)", value=True)

    if show_white_spots:
        # Get White Spots Data from API
        white_spots = fetch_data("/api/white-spots", {"year": pred_year})
        df_ws = pd.DataFrame(white_spots)

        col_ws_chart, col_ws_desc = st.columns([5, 4])

        with col_ws_chart:
            # Bar chart ranking ORPs
            fig_ws = px.bar(
                df_ws,
                x="white_spot_index",
                y="orp",
                orientation="h",
                color="white_spot_index",
                color_continuous_scale="Reds",
                labels={"white_spot_index": "Index Bílého místa (WSI)", "orp": ""},
                title="Srovnání ORP podle Indexu Bílých míst (vyšší index = vyšší riziko)",
                height=380
            )
            fig_ws.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=40, b=10),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig_ws, width='stretch')

        with col_ws_desc:
            st.markdown("""
            <div class="metric-card white-spot-card" style="margin-top: 15px;">
                <div style="font-weight: 800; font-size: 1.1rem; color: #ff6b6b; margin-bottom: 10px;">Metodika White Spot Indexu (WSI)</div>
                <p style="font-size: 0.9rem; color: #c4ccdf; line-height: 1.5; margin-bottom: 10px;">
                    <strong>Index bílých míst (WSI)</strong> identifikuje regiony, které vyžadují naléhavou pozornost při plánování sociálních služeb. Index se vypočítává jako poměr syntetického
                    sociálního stresu (kombinace nezaměstnanosti, exekucí a vyloučených lokalit) a očekávaného tempa stárnutí seniorů 75+ ku celkové lokální kapacitě služeb.
                </p>
                <div style="background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); font-family: monospace; font-size: 0.85rem; color: #ffbe0b;">
                    WSI = (Socioekonomický stres * Růst populace 75+) * 100 / (Kapacita služeb + 10)
                </div>
                <p style="font-size: 0.9rem; color: #c4ccdf; margin-top: 10px; line-height: 1.5;">
                    💡 <strong>Nejohroženější oblastí</strong> je dlouhodobě ORP <strong>Podbořany</strong>, které disponuje pouze terénními službami,
                    ale zcela postrádá kamenné pobytové zařízení pro seniory, přičemž populace 75+ zde roste velmi dynamicky.
                </p>
            </div>
            """, unsafe_allow_html=True)

        # Table output formatted beautifully
        st.markdown("<div style='font-size: 0.9rem; color: #8c96bc; margin-top: 15px; margin-bottom: 10px; font-weight: 600;'>TABULKOVÉ VYJÁDŘENÍ INDEXU BÍLÝCH MÍST</div>", unsafe_allow_html=True)

        # Rename columns to Czech labels for output
        df_table = df_ws.copy()
        df_table.columns = ["ORP", "Index Bílého místa (WSI)", "Nezaměstnanost (%)", "Exekuce (%)", "Celková kapacita (lůžka/klienti)", "Růst seniorů 75+ (%)"]

        st.dataframe(
            df_table,
            width='stretch',
            hide_index=True
        )

# ----------------- TAB 3: REPORTY A EXPORT -----------------
with tab_exports:
    st.markdown("<h4 style='color: #ffffff; font-weight: 600; margin-bottom: 15px;'>Exekutivní shrnutí a exporty datových sad</h4>", unsafe_allow_html=True)

    # 1. Executive Summary Generator block
    st.markdown("### 📝 Exekutivní analýza pro vybrané území")

    if selected_orp == "Celý kraj":
        # Regional overview report
        stressed_orps = [p["orp"] for p in predictions_val.values() if p["stress_alert"]]
        st.markdown(f"""
        <div class="metric-card" style="border-left: 5px solid #ff4b4b !important;">
            <div style="font-size: 1.3rem; font-weight: 800; color: #ffffff; margin-bottom: 10px;">KRITICKÁ ANALÝZA ÚSTECKÉHO KRAJE (Horizont do roku 2035)</div>
            <p style="color: #c4ccdf; line-height: 1.6; font-size: 0.95rem;">
                Ústecký kraj čelí <strong>kombinovanému tlaku</strong>: vysokému socioekonomickému znevýhodnění a výrazně zrychlenému stárnutí populace.
                Do roku 2035 dojde v celém kraji k nárůstu populace starší 75 let o průměrně <strong>35-40 %</strong>.
            </p>
            <div style="margin: 15px 0px; padding: 12px; background: rgba(220, 53, 69, 0.08); border: 1px solid rgba(220, 53, 69, 0.2); border-radius: 8px;">
                <strong>🚨 Hlavní kapacitní rizika (Kritický deficit kapacit nad {deficit_threshold}%):</strong><br/>
                Kritické ohrožení nedostatkem lůžek pobytové péče je v roce <strong>{pred_year}</strong> detekováno v <strong>{len(stressed_orps)} z 16 ORP</strong>.<br/>
                Jedná se o oblasti: <strong>{", ".join(stressed_orps)}</strong>.
            </div>
            <p style="color: #c4ccdf; line-height: 1.6; font-size: 0.95rem;">
                <strong>Doporučená strategická opatření:</strong><br/>
                1. <strong>Investiční podpora pobytových služeb:</strong> Zaměřit krajské dotace na výstavbu lůžkových kapacit zejména v oblastech s nulovým stavem (Podbořany) a kritickým deficitem.<br/>
                2. <strong>Posílení terénní péče:</strong> Navýšit personální a finanční kapacity pečovatelských služeb v ORP Louny, Kadaň a Žatec, což umožní seniorům setrvat déle v domácím prostředí a sníží tlak na lůžkové kapacity.<br/>
                3. <strong>Podpora sociálního bydlení:</strong> Propojit plánování sociálních služeb s řešením exekucí a sociálního bydlení v ORP Most a Chomutov pro omezení odlivu produktivní síly z regionu.
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Single ORP report
        orp_p = predictions_val[selected_orp]
        def_pct = orp_p["deficit_percent"]
        growth_pct = round(((orp_p["pop_75plus"] - orp_p["hist_2025_pop_75plus"]) / orp_p["hist_2025_pop_75plus"]) * 100.0, 1)

        # Risk classification
        if orp_p["stress_alert"]:
            risk_title = "🚨 KRITICKÉ KAPACITNÍ RIZIKO (VYSOKÉ)"
            risk_border = "border-left: 5px solid #dc3545 !important;"
            risk_desc = f"V oblasti {selected_orp} je predikován vážný nedostatek lůžek. Rychlý růst nejstarší věkové skupiny ({growth_pct}%) překonává stávající stacionární péči. Doporučuje se okamžité plánování nových kapacit pobytových služeb nebo zásadní transformace a posílení terénních služeb o min. 25 %."
        elif def_pct > 0:
            risk_title = "⚠️ STŘEDNÍ KAPACITNÍ RIZIKO"
            risk_border = "border-left: 5px solid #ff9f1c !important;"
            risk_desc = f"Kapacita stacionárních služeb v ORP {selected_orp} je prozatím stabilní, avšak do roku {pred_year} se očekává deficit {def_pct}%. Situaci je nutno průběžně sledovat a koordinovat posílení domácí ošetřovatelské péče."
        else:
            risk_title = "✅ NÍZKÉ KAPACITNÍ RIZIKO"
            risk_border = "border-left: 5px solid #2ec4b6 !important;"
            risk_desc = f"ORP {selected_orp} vykazuje dostatečnou lůžkovou kapacitu pro pokrytí očekávaného nárůstu seniorů v horizontu do roku {pred_year}. Je doporučeno udržovat stávající síť poskytovatelů."

        st.markdown(f"""
        <div class="metric-card" style="{risk_border}">
            <div style="font-size: 1.3rem; font-weight: 800; color: #ffffff; margin-bottom: 5px;">HODNOCENÍ ÚZEMÍ: ORP {selected_orp}</div>
            <div style="font-size: 0.9rem; font-weight: 600; color: #ffbe0b; margin-bottom: 15px;">{risk_title}</div>

            <p style="color: #c4ccdf; line-height: 1.6; font-size: 0.95rem;">
                <strong>Socioekonomický kontext:</strong><br/>
                Míra nezaměstnanosti v oblasti činí <strong>{orp_p['unemployment_rate']} %</strong> (krajský průměr: 6.7%).
                Podíl exekucí zasahuje <strong>{orp_p['exekuce_rate']} %</strong> obyvatel (krajský průměr: 13.5%).
            </p>

            <p style="color: #c4ccdf; line-height: 1.6; font-size: 0.95rem;">
                <strong>Analýza poptávky a stárnutí:</strong><br/>
                Populace seniorů nad 75 let vzroste do roku {pred_year} o <strong>{growth_pct} %</strong> (z původních {orp_p['hist_2025_pop_75plus']} na očekávaných {orp_p['pop_75plus']} osob).<br/>
                Očekávaná teoretická poptávka po lůžkách stacionární péče činí <strong>{orp_p['predicted_demand']} lůžek</strong> oproti stávající kapacitě <strong>{orp_p['current_capacity']} lůžek</strong>.
            </p>

            <div style="margin: 15px 0px; padding: 12px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; color: #ffffff; font-size: 0.95rem;">
                <strong>Doporučení pro rozvoj sociálních služeb v ORP {selected_orp}:</strong><br/>
                {risk_desc}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)

    # 2. Raw Data Export Section
    st.markdown("### 📥 Stáhnout datové podklady v otevřených formátech")

    col_d1, col_d2, col_d3 = st.columns(3)

    # Export 1: Demographics (history + predictions)
    with col_d1:
        st.markdown("""
        <div class="metric-card" style="padding: 15px !important; margin: 0px !important;">
            <div style="font-weight: 600; color: #ffffff; margin-bottom: 10px;">Demografická časová řada</div>
            <p style="font-size: 0.8rem; color: #8c96bc; min-height: 50px;">Historická data 2018–2025 a predikce 2026–2035 pro vybrané území.</p>
        </div>
        """, unsafe_allow_html=True)

        # Prepare demographics export data
        export_orp = selected_orp if selected_orp != "Celý kraj" else "Ústí nad Labem"
        hist_exp = fetch_data("/api/orp/demographics")[export_orp]

        from backend.forecasting import get_forecast_for_orp
        future_exp = []
        for y in range(2026, 2036):
            f = get_forecast_for_orp(export_orp, y)
            if f:
                future_exp.append({
                    "year": y,
                    "total_pop": f["total_pop"],
                    "pop_65plus": f["pop_65plus"],
                    "pop_75plus": f["pop_75plus"],
                    "net_migration": f["net_migration"]
                })
        df_exp_dem = pd.concat([pd.DataFrame(hist_exp), pd.DataFrame(future_exp)], ignore_index=True)
        csv_dem = df_exp_dem.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="📥 Stáhnout demografii (CSV)",
            data=csv_dem,
            file_name=f"demografie_projekce_{export_orp}.csv",
            mime="text/csv",
            key="btn_download_dem"
        )

    # Export 2: Social Services registry
    with col_d2:
        st.markdown("""
        <div class="metric-card" style="padding: 15px !important; margin: 0px !important;">
            <div style="font-weight: 600; color: #ffffff; margin-bottom: 10px;">Registr sociálních služeb</div>
            <p style="font-size: 0.8rem; color: #8c96bc; min-height: 50px;">Seznam aktuálních poskytovatelů péče s kapacitami a GPS v aktivním území.</p>
        </div>
        """, unsafe_allow_html=True)

        # Filter services
        if selected_orp != "Celý kraj":
            filtered_serv = [s for s in services if s["orp"] == selected_orp]
        else:
            filtered_serv = services
        df_serv = pd.DataFrame(filtered_serv)
        csv_serv = df_serv.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="📥 Stáhnout registr služeb (CSV)",
            data=csv_serv,
            file_name=f"socialni_sluzby_{selected_orp}.csv",
            mime="text/csv",
            key="btn_download_services"
        )

    # Export 3: Calculations summary (JSON)
    with col_d3:
        st.markdown("""
        <div class="metric-card" style="padding: 15px !important; margin: 0px !important;">
            <div style="font-weight: 600; color: #ffffff; margin-bottom: 10px;">Kompletní predikční data</div>
            <p style="font-size: 0.8rem; color: #8c96bc; min-height: 50px;">Kompletní modelové výstupy deficitů pro všechny ORP v roce {pred_year} (JSON format).</p>
        </div>
        """, unsafe_allow_html=True)

        json_pred = json.dumps(predictions_val, ensure_ascii=False, indent=2)

        st.download_button(
            label="📥 Stáhnout analýzu deficitů (JSON)",
            data=json_pred,
            file_name=f"predikce_kapacit_{pred_year}.json",
            mime="application/json",
            key="btn_download_json"
        )


# ----------------- TAB 4: DATA ČSSZ -----------------
with tab_cssz:
    st.markdown("<h4 style='color: #ffffff; font-weight: 600; margin-bottom: 15px;'>Údaje ČSSZ: Důchody a Nemocenské dávky</h4>", unsafe_allow_html=True)
    st.markdown("<p style='color: #c4ccdf; font-size: 0.95rem;'>Tato sekce obsahuje agregovaná (ukázková) data České správy sociálního zabezpečení (ČSSZ) pro vybrané území.</p>", unsafe_allow_html=True)

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        st.markdown("### 🧓 Starobní důchody (Odhad)")
        if selected_orp == "Celý kraj":
            total_recipients = sum(v["recipients"] for v in cssz_data.values())
            avg_pension = int(sum(v["average_pension"] * v["recipients"] for v in cssz_data.values()) / total_recipients)
            render_metric_card("Průměrná výše důchodu", f"{avg_pension:,}".replace(",", " ") + " Kč", "Mírný nárůst", "up")
            render_metric_card("Počet příjemců starobního důchodu", f"{total_recipients:,}".replace(",", " "), "Dle dat ČSSZ", "none")
        else:
            orp_cssz = cssz_data[selected_orp]
            render_metric_card(f"Průměrný důchod v ORP {selected_orp}", f"{orp_cssz['average_pension']:,}".replace(",", " ") + " Kč", "Ukázková data", "none")
            render_metric_card("Počet příjemců", f"{orp_cssz['recipients']:,}".replace(",", " "), "Stabilní", "none")

    with col_c2:
        st.markdown("### 🤒 Nemocenské a další dávky")
        if selected_orp == "Celý kraj":
            avg_duration = sum(v["avg_sickness_duration_days"] for v in cssz_data.values()) // len(cssz_data)
            total_days = sum(v["sickness_days_total"] for v in cssz_data.values())
            render_metric_card("Průměrná doba trvání PNP", f"{avg_duration} dní", "Dle dat ČSSZ", "down")
            render_metric_card("Celkový počet proplacených dnů", f"{total_days:,}".replace(",", " "), "Za celý kraj", "none")
        else:
            orp_cssz = cssz_data[selected_orp]
            render_metric_card(f"Průměrná doba trvání PNP v ORP {selected_orp}", f"{orp_cssz['avg_sickness_duration_days']} dní", "V souladu s krajem", "none")
            render_metric_card("Podíl práce neschopných (PNP)", f"{orp_cssz['sickness_ratio_pct']} %", "Stabilní podíl", "up")

    with col_c3:
        st.markdown("### 💼 Sociální pojištění a udržitelnost")
        if selected_orp == "Celý kraj":
            total_recipients = sum(v["recipients"] for v in cssz_data.values())
            # Dynamically calculate active contributors from downloaded demographics and indicators data
            total_active = 0
            for orp, v in cssz_data.items():
                orp_dem = demographics_data[orp][-1]
                orp_unemp = indicators[orp]["unemployment_rate"]
                # 77% economic activity rate, minus the unemployed
                orp_active = int(orp_dem["pop_15_64"] * 0.77 * (1 - orp_unemp / 100))
                total_active += orp_active
            
            ratio = round(total_active / total_recipients, 2) if total_recipients > 0 else 0.0
            render_metric_card("Výdělečně činní (plátci pojistného)", f"{total_active:,}".replace(",", " "), "Vypočteno z dat ČSÚ (aktivní 15-64 let)", "none")
            render_metric_card("Počet pracujících na 1 důchodce", f"{ratio:.2f}", "Udržitelnost systému (poměr)", "down" if ratio < 2.0 else "none")
        else:
            orp_cssz = cssz_data[selected_orp]
            recipients = orp_cssz["recipients"]
            # Dynamically calculate active contributors from downloaded demographics and indicators data for selected ORP
            orp_dem = demographics_data[selected_orp][-1]
            orp_unemp = indicators[selected_orp]["unemployment_rate"]
            active = int(orp_dem["pop_15_64"] * 0.77 * (1 - orp_unemp / 100))
            
            ratio = round(active / recipients, 2) if recipients > 0 else 0.0
            render_metric_card(f"Výdělečně činní v ORP {selected_orp}", f"{active:,}".replace(",", " "), "Vypočteno z dat ČSÚ (aktivní 15-64 let)", "none")
            render_metric_card("Počet pracujících na 1 důchodce", f"{ratio:.2f}", f"Poměr pro ORP {selected_orp}", "down" if ratio < 2.0 else "none")

    st.info("💡 Toto je ukázková vizualizace sekce pro data ČSSZ integrovaná z back-endu.")

# Custom page footer matching style.css definitions
st.markdown("""
<div class="app-footer">
    Prediktivní Sociální Atlas Ústeckého kraje &copy; 2026 &bull; Vytvořeno pro podporu strategického rozvoje sociálních služeb.
</div>
""", unsafe_allow_html=True)
