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

    elif endpoint == "/api/orp/cssz/quantiles":
        filepath = os.path.join(data_dir, "cssz_national_quantiles.json")
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

# Robustní detekce kliknutí na polygon v mapě
def get_clicked_orp_name(map_output):
    if not map_output:
        return None

    click_info = map_output.get("last_active_drawing") or map_output.get("last_object_clicked")
    if not click_info:
        return None

    if isinstance(click_info, dict):
        properties = click_info.get("properties")
        if isinstance(properties, dict):
            name = properties.get("name")
            if name:
                return name
        feature_id = click_info.get("id")
        if feature_id and isinstance(feature_id, str) and not feature_id.startswith("marker"):
            return feature_id
    return None

# Helper to calculate bounds from GeoJSON geometry
def get_feature_bounds(geometry):
    if not geometry or "coordinates" not in geometry:
        return None

    coords = geometry["coordinates"]
    all_lats = []
    all_lons = []

    def extract_coords(coord_array):
        for item in coord_array:
            if isinstance(item[0], (int, float)):
                all_lons.append(item[0])
                all_lats.append(item[1])
            else:
                extract_coords(item)

    extract_coords(coords)

    if all_lats and all_lons:
        return [[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]]
    return None

import streamlit.components.v1 as components

# Sync theme with localStorage via URL query parameters
# Render a tiny invisible iframe to read/write theme from/to parent's localStorage
theme_init_js = """
<script>
    try {
        const savedTheme = window.parent.localStorage.getItem('theme');
        const urlParams = new URLSearchParams(window.parent.location.search);
        const urlTheme = urlParams.get('theme');

        if (savedTheme && savedTheme !== urlTheme) {
            urlParams.set('theme', savedTheme);
            window.parent.location.search = urlParams.toString();
        } else if (!savedTheme && urlTheme) {
            window.parent.localStorage.setItem('theme', urlTheme);
        }
    } catch (e) {
        console.error("Failed to sync localStorage theme:", e);
    }
</script>
"""
components.html(theme_init_js, height=0, width=0)

# Retrieve theme from query parameters (fallback to dark)
url_theme = st.query_params.get("theme", "dark")
if "theme" not in st.session_state:
    st.session_state.theme = url_theme

# Dynamic Theme Configuration via Streamlit's Internal Config API
try:
    if st.session_state.theme == "light":
        st._config.set_option("theme.base", "light")
        st._config.set_option("theme.backgroundColor", "#f5f7fa")
        st._config.set_option("theme.secondaryBackgroundColor", "#ffffff")
        st._config.set_option("theme.textColor", "#1a202c")
    else:
        st._config.set_option("theme.base", "dark")
        st._config.set_option("theme.backgroundColor", "#0d0f14")
        st._config.set_option("theme.secondaryBackgroundColor", "#121621")
        st._config.set_option("theme.textColor", "#ffffff")
    st._config.set_option("theme.primaryColor", "#ff4b4b")
except Exception as e:
    pass

# Helper to load and inject custom stylesheet with dynamic theme overrides
def local_css(file_name):
    with open(file_name, encoding="utf-8") as f:
        css_content = f.read()

    # Append light mode CSS variables if theme is light
    if st.session_state.theme == "light":
        light_overrides = """
        :root {
            --app-bg: #f5f7fa;
            --app-bg-gradient: radial-gradient(at 10% 20%, rgba(66, 133, 244, 0.06) 0px, transparent 50%),
                               radial-gradient(at 90% 80%, rgba(220, 53, 69, 0.04) 0px, transparent 50%);
            --card-bg: rgba(255, 255, 255, 0.85);
            --card-border: rgba(0, 0, 0, 0.08);
            --card-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.04);
            --card-hover-border: rgba(66, 133, 244, 0.25);
            --card-hover-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.08), 0 0 15px rgba(66, 133, 244, 0.03);

            --white-spot-bg: rgba(220, 53, 69, 0.04);
            --white-spot-border: rgba(220, 53, 69, 0.15);
            --white-spot-hover-border: rgba(220, 53, 69, 0.35);
            --white-spot-hover-shadow: 0 12px 40px 0 rgba(220, 53, 69, 0.08);

            --header-title-gradient: linear-gradient(135deg, #1b2a4a 30%, #475a80 100%);
            --header-subtitle-color: #4b5563;

            --metric-value-color: #1a202c;
            --metric-label-color: #4b5563;

            --sidebar-bg: #ffffff;
            --sidebar-border: rgba(0, 0, 0, 0.06);
            --sidebar-text-primary: #1a202c;
            --sidebar-text-muted: #6b7280;
            --sidebar-hr: rgba(0, 0, 0, 0.06);

            --tab-bg: rgba(0, 0, 0, 0.02);
            --tab-border: rgba(0, 0, 0, 0.04);
            --tab-text: #4b5563;
            --tab-selected-bg: rgba(0, 0, 0, 0.05);
            --tab-selected-text: #111827;

            --footer-color: #718096;
            --footer-border: rgba(0, 0, 0, 0.05);

            --code-bg: rgba(0, 0, 0, 0.04);
        }
        """
        css_content += "\n" + light_overrides
    st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)

# Load styling
css_path = os.path.join(os.path.dirname(__file__), "style.css")
if os.path.exists(css_path):
    local_css(css_path)

# Set dynamic themes for components
plotly_template = "plotly_white" if st.session_state.theme == "light" else "plotly_dark"
map_tiles = "cartodbpositron" if st.session_state.theme == "light" else "cartodbdarkmatter"
grid_color = "rgba(0,0,0,0.08)" if st.session_state.theme == "light" else "rgba(255,255,255,0.05)"
font_color = "#1a202c" if st.session_state.theme == "light" else "#ffffff"
legend_text_color = "#1a202c" if st.session_state.theme == "light" else "#ffffff"

# Fetch global datasets
try:
    indicators = fetch_data("/api/orp/indicators")
    services = fetch_data("/api/social-services")
    geojson_data = fetch_data("/api/orp/geojson")
    cssz_data = fetch_data("/api/orp/cssz")
    cssz_quantiles = fetch_data("/api/orp/cssz/quantiles")
    demographics_data = fetch_data("/api/orp/demographics")
except Exception as e:
    st.error(f"Nepodařilo se načíst základní data. Zkontrolujte prosím přítomnost souborů ve složce data/. Detaily: {e}")
    st.stop()

for feature in geojson_data.get("features", []):
    feature["id"] = feature["properties"]["name"]

# --- MECHANISMUS DIALOGU MEZI MAPOU A SIDEBAREM ---
if "selected_orp" not in st.session_state:
    st.session_state.selected_orp = "Celý kraj"

if "menu_version" not in st.session_state:
    st.session_state.menu_version = 0

orp_options = ["Celý kraj"] + sorted(list(indicators.keys()))

# ----------------- SIDEBAR PANEL -----------------
st.sidebar.markdown("""
<div style="text-align: center; padding-bottom: 10px;">
    <h2 style="color: var(--sidebar-text-primary); font-weight: 800; margin-bottom: 0px; font-size: 1.5rem;">NASTAVENÍ</h2>
    <span style="color: var(--sidebar-text-muted); font-size: 0.85rem;">PREDIKTIVNÍ ATLAS</span>
</div>
""", unsafe_allow_html=True)

try:
    current_index = orp_options.index(st.session_state.selected_orp)
except ValueError:
    current_index = 0

def on_sidebar_change():
    dynamic_key = f"orp_sidebar_select_v_{st.session_state.menu_version}"
    st.session_state.selected_orp = st.session_state[dynamic_key]

selected_orp = st.sidebar.selectbox(
    "Vyberte území (ORP):",
    orp_options,
    index=current_index,
    key=f"orp_sidebar_select_v_{st.session_state.menu_version}",
    on_change=on_sidebar_change
)

selected_orp = st.session_state.selected_orp

st.sidebar.markdown("<hr style='border-color: var(--sidebar-hr); margin: 15px 0px;'/>", unsafe_allow_html=True)

st.sidebar.subheader("Vrstvy mapy (Sociální Atlas)")
selected_indicator_label = st.sidebar.selectbox(
    "Zobrazovaný indikátor:",
    [
        "Počet důchodců",
        "Průměrná výše důchodu",
        "Exekuční srážky důchodců",
        "Nezaměstnanost",
        "Kriminalita"
    ]
)

INDICATOR_MAPPING = {
    "Počet důchodců": ("cssz", "recipients", "osob", "recipients", cm.linear.Blues_09),
    "Průměrná výše důchodu": ("cssz", "average_pension", "Kč", "average_pension", cm.linear.Greens_09),
    "Exekuční srážky důchodců": ("indicators", "exekuce_rate", "%", "exekuce_rate", cm.linear.OrRd_09),
    "Nezaměstnanost": ("indicators", "unemployment_rate", "%", "unemployment_rate", cm.linear.YlOrRd_09),
    "Kriminalita": ("indicators", "crime_rate_per_1k", "případů", "crime_rate_per_1k", cm.linear.Purples_09)
}

selected_indicator_source, indicator_key, indicator_unit, indicator_title, colormap_fn = INDICATOR_MAPPING[selected_indicator_label]

def get_indicator_value(orp_name):
    if selected_indicator_source == "indicators":
        return indicators.get(orp_name, {}).get(indicator_key, 0.0)
    return cssz_data.get(orp_name, {}).get(indicator_key, 0.0)


def format_indicator_value(value):
    if value is None:
        return "0"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.1f}"
    if indicator_key in ("recipients", "average_pension"):
        try:
            return f"{int(value):,}".replace(",", " ")
        except Exception:
            return str(value)
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return str(value)


def format_value_with_unit(value):
    formatted = format_indicator_value(value)
    return f"{formatted} {indicator_unit}".strip()

st.sidebar.subheader("Zobrazit body zájmu (POI):")
show_stationary = st.sidebar.checkbox("Pobytová zařízení (red)", value=True)
show_field = st.sidebar.checkbox("Terénní služby (green)", value=True)
show_shelters = st.sidebar.checkbox("Azylové domy (blue)", value=False)

st.sidebar.markdown("<hr style='border-color: var(--sidebar-hr); margin: 15px 0px;'/>", unsafe_allow_html=True)
st.sidebar.markdown("""
<div class="metric-card" style="padding: 15px !important; margin: 0px !important;">
    <div style="font-size: 0.75rem; color: var(--metric-label-color); font-weight: 600; text-transform: uppercase;">Aktivní území</div>
    <div style="font-size: 1.15rem; color: var(--metric-value-color); font-weight: 800; margin-top: 5px;">""" + selected_orp + """</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("<hr style='border-color: var(--sidebar-hr); margin: 15px 0px;'/>", unsafe_allow_html=True)

# Theme toggle button in sidebar header
col_theme_lbl, col_theme_sw = st.sidebar.columns([3, 1])
with col_theme_lbl:
    st.markdown("<div style='padding-top: 5px; font-size: 0.8rem; font-weight: 800; color: var(--sidebar-text-muted); text-transform: uppercase;'>REŽIM VZHLEDU</div>", unsafe_allow_html=True)
with col_theme_sw:
    is_light = st.toggle("☀️", value=(st.session_state.theme == "light"), key="theme_toggle", label_visibility="collapsed")
    new_theme = "light" if is_light else "dark"
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.query_params["theme"] = new_theme

        # Write back to localStorage using a tiny helper component
        components.html(f"""
        <script>
            try {{
                window.parent.localStorage.setItem('theme', '{new_theme}');
            }} catch (e) {{
                console.error(e);
            }}
        </script>
        """, height=0, width=0)
        st.rerun()

# ----------------- MAIN APP CONTENT -----------------

st.markdown("""
<div style="text-align: center; margin-top: 10px; margin-bottom: 30px;">
    <h1 class="header-title" style="font-size: 2.8rem; margin-bottom: 0px; text-transform: uppercase;">Prediktivní Sociální Atlas</h1>
    <h3 class="header-subtitle" style="font-size: 1.15rem; margin-top: 5px;">Ústecký kraj &bull; Systém podpory rozhodování a modelování budoucích kapacit sociálních služeb</h3>
</div>
""", unsafe_allow_html=True)

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
tab_atlas, tab_predictions = st.tabs([
    "📂 SOCIÁLNÍ ATLAS (Současnost)",
    "📈 PREDIKTIVNÍ MODEL (2026–2035)"
])

# ----------------- TAB 1: SOCIÁLNÍ ATLAS -----------------
with tab_atlas:
    st.markdown("<h4 style='color: var(--text-color); font-weight: 600; margin-bottom: 15px;'>Současná sociální a demografická situace</h4>", unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    if selected_orp == "Celý kraj":
        total_pop_2025 = sum(dem[2025-2018]["total_pop"] for dem in fetch_data("/api/orp/demographics").values())
        values = [get_indicator_value(orp_name) for orp_name in indicators.keys()]
        avg_indicator = round(np.mean(values), 1)
        max_orp = max(indicators.keys(), key=lambda orp_name: get_indicator_value(orp_name))
        min_orp = min(indicators.keys(), key=lambda orp_name: get_indicator_value(orp_name))
        max_value = get_indicator_value(max_orp)
        min_value = get_indicator_value(min_orp)
        range_indicator = round(max_value - min_value, 1)

        if selected_indicator_source == "cssz" and indicator_key == "recipients":
            total_recipients = sum(cssz_data.get(orp_name, {}).get("recipients", 0) for orp_name in cssz_data.keys())
            total_active = 0
            for orp_name in cssz_data.keys():
                orp_dem = demographics_data.get(orp_name, [])
                orp_last = orp_dem[-1] if orp_dem else {}
                orp_unemp = indicators.get(orp_name, {}).get("unemployment_rate", 0.0)
                orp_active = int(orp_last.get("pop_15_64", 0) * 0.77 * (1 - orp_unemp / 100))
                total_active += orp_active
            ratio = round(total_active / total_recipients, 2) if total_recipients > 0 else 0.0

            with col1:
                render_metric_card("Důchodci celkem", f"{total_recipients:,}".replace(",", " ") + f" {indicator_unit}", "Celkový počet příjemců důchodů v kraji", "none")
            with col2:
                render_metric_card("Nejvyšší ORP", f"{max_orp}: {format_value_with_unit(max_value)}", "Nejvyšší počet důchodců", "up")
            with col3:
                render_metric_card("Nejnižší ORP", f"{min_orp}: {format_value_with_unit(min_value)}", "Nejnižší počet důchodců", "down")
            with col4:
                render_metric_card("Počet pracujících na 1 důchodce", f"{ratio:.2f}", "Vypočteno z dat ČSÚ (15-64 let)", "none")
        else:
            with col1:
                render_metric_card(f"Průměr {selected_indicator_label}", format_value_with_unit(avg_indicator), "Současný krajský průměr", "none")
            with col2:
                render_metric_card("Nejvyšší ORP", f"{max_orp}: {format_value_with_unit(max_value)}", "Nejvyšší hodnota v kraji", "up")
            with col3:
                render_metric_card("Nejnižší ORP", f"{min_orp}: {format_value_with_unit(min_value)}", "Nejnižší hodnota v kraji", "down")
            with col4:
                render_metric_card(f"Rozpětí {selected_indicator_label}", format_value_with_unit(range_indicator), f"Rozdíl mezi {max_orp} a {min_orp}", "none")
    else:
        hist_dem = fetch_data("/api/orp/demographics")[selected_orp]
        pop_2025 = hist_dem[-1]["total_pop"]
        orp_last = hist_dem[-1] if hist_dem else {}
        orp_unemp = indicators.get(selected_orp, {}).get("unemployment_rate", 0.0)
        indicator_value = get_indicator_value(selected_orp)
        avg_indicator = round(np.mean([get_indicator_value(orp_name) for orp_name in indicators.keys()]), 1)
        diff_value = round(indicator_value - avg_indicator, 1)
        diff_direction = "up" if diff_value > 0 else "down" if diff_value < 0 else "none"
        diff_text = f"{format_value_with_unit(abs(diff_value))} {'nad' if diff_value > 0 else 'pod' if diff_value < 0 else 've shodě s'} průměrem kraje"
        orp_capacity = sum(s["capacity"] for s in services if s["orp"] == selected_orp)

        with col1:
            render_metric_card(selected_indicator_label, format_value_with_unit(indicator_value), f"ORP {selected_orp}", diff_direction)
        with col2:
            render_metric_card(f"Krajský průměr {selected_indicator_label}", format_value_with_unit(avg_indicator), "Průměr celého kraje", "none")
        with col3:
            render_metric_card("Rozdíl proti průměru kraje", format_value_with_unit(abs(diff_value)), diff_text, diff_direction)
        with col4:
            if selected_indicator_source == "cssz" and indicator_key == "recipients":
                recipients = cssz_data.get(selected_orp, {}).get("recipients", 0)
                orp_active = int(orp_last.get("pop_15_64", 0) * 0.77 * (1 - orp_unemp / 100))
                ratio = round(orp_active / recipients, 2) if recipients > 0 else 0.0
                render_metric_card("Počet pracujících na 1 důchodce", f"{ratio:.2f}", "Vypočteno z dat ČSÚ (15-64 let)", "down" if ratio < 2.0 else "none")
            else:
                render_metric_card("Populace 2025", f"{pop_2025:,}".replace(",", " "), "Dle dat ČSÚ", "none")

    st.markdown("<br/>", unsafe_allow_html=True)

    col_map, col_chart = st.columns([5, 4])

    with col_map:
        st.markdown(f"<div style='font-size: 0.9rem; color: var(--metric-label-color); margin-bottom: 10px; font-weight: 600;'>KARTOGRAFICKÉ ZOBRAZENÍ: {selected_indicator_label}</div>", unsafe_allow_html=True)

        m = folium.Map(location=[50.55, 13.90], zoom_start=9, tiles=map_tiles)

        if selected_orp != "Celý kraj":
            for feature in geojson_data.get("features", []):
                if feature["properties"]["name"] == selected_orp:
                    bounds = get_feature_bounds(feature["geometry"])
                    if bounds:
                        m.fit_bounds(bounds, padding=(0.05, 0.05))
                    break

        map_geo = copy.deepcopy(geojson_data)
        values = [get_indicator_value(orp_name) for orp_name in indicators.keys()]
        min_val, max_val = min(values), max(values)

        colormap = colormap_fn.scale(min_val, max_val)
        colormap.caption = f"{selected_indicator_label}"
        colormap.add_to(m)

        # Style the map legend text and lines dynamically inside the iframe based on theme
        legend_css = f"""
        <style>
            .legend text {{
                fill: {legend_text_color} !important;
                font-family: 'Outfit', sans-serif !important;
                font-size: 12px !important;
                font-weight: 600 !important;
            }}
            .legend line {{
                stroke: {legend_text_color} !important;
            }}
        </style>
        """
        m.get_root().header.add_child(folium.Element(legend_css))

        for feature in map_geo.get("features", []):
            name = feature["properties"]["name"]
            val = get_indicator_value(name)
            feature["properties"]["indicator_val"] = val
            feature["properties"]["indicator_label"] = selected_indicator_label

        def style_fn(feature):
            val = feature["properties"].get("indicator_val", 0.0)
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
            data=map_geo,
            style_function=style_fn,
            highlight_function=highlight_fn,
            tooltip=tooltip_widget,
            popup=folium.GeoJsonPopup(fields=["name"], labels=False),
            name="ORP Hranice"
        ).add_to(m)

        fg_stationary = folium.FeatureGroup(name="Pobytová zařízení (DS)", show=show_stationary)
        fg_field = folium.FeatureGroup(name="Terénní služby", show=show_field)
        fg_shelters = folium.FeatureGroup(name="Azylové domy", show=show_shelters)

        for s in services:
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

        map_output = st_folium(m, height=450, width='stretch', key="atlas_map")

        clicked_name = get_clicked_orp_name(map_output)
        if clicked_name and clicked_name in indicators.keys():
            if clicked_name != st.session_state.selected_orp:
                st.session_state.selected_orp = clicked_name
                st.session_state.menu_version += 1
                st.rerun()

    with col_chart:
        st.markdown("<div style='font-size: 0.9rem; color: var(--metric-label-color); margin-bottom: 10px; font-weight: 600;'>POROVNÁNÍ NAPŘÍČ OBLASTMI</div>", unsafe_allow_html=True)

        comp_list = []
        for orp_name in indicators.keys():
            comp_list.append({
                "ORP": orp_name,
                "Hodnota": get_indicator_value(orp_name),
                "Skupina": "Vybraná oblast" if orp_name == selected_orp else "Ostatní ORP"
            })
        df_comp = pd.DataFrame(comp_list).sort_values(by="Hodnota", ascending=True)

        fig_comp = px.bar(
            df_comp,
            x="Hodnota",
            y="ORP",
            orientation="h",
            color="Skupina",
            color_discrete_map={"Vybraná oblast": "#ff4b4b", "Ostatní ORP": "#e4e6eb" if st.session_state.theme == "light" else "#282c3c"},
            labels={"Hodnota": f"{selected_indicator_label} [{indicator_unit}]", "ORP": ""},
            height=430
        )
        fig_comp.update_layout(
            template=plotly_template,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=font_color),
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor=grid_color),
            yaxis=dict(gridcolor=grid_color)
        )
        st.plotly_chart(fig_comp, width='stretch')

# ----------------- TAB 2: PREDIKTIVNÍ MODEL -----------------
with tab_predictions:

    col_layout_left, col_layout_right = st.columns([1, 2.5])

    with col_layout_left:
        st.markdown("""
        <div style='background: var(--card-bg); padding: 20px; border-radius: 12px; border: 1px solid var(--card-border);'>
            <h5 style='color: #4285f4; margin-top: 0px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;'>🎛️ Ovládací pult simulací</h5>
            <hr style='border-color: var(--sidebar-hr); margin: 10px 0 20px 0;'/>
        </div>
        """, unsafe_allow_html=True)

        pred_year = st.slider("Cílový rok projekce:", min_value=2026, max_value=2035, value=2030, step=1)
        deficit_threshold = st.slider("Kritický kapacitní deficit (%):", min_value=0.0, max_value=50.0, value=20.0, step=5.0)

        st.markdown("<br/><b style='color:var(--metric-label-color); font-size:0.8rem; text-transform:uppercase;'>Zásahy a investice:</b>", unsafe_allow_html=True)
        sim_new_beds = st.number_input("Přidat nová lůžka:", min_value=0, max_value=500, value=0, step=10, key="sim_beds")
        sim_field_boost = st.slider("Posílit terénní služby:", min_value=0, max_value=30, value=0, step=5, key="sim_field",
                                    help="O kolik % klesne tlak na lůžka díky silnější pečovatelské službě doma.")

        # NOVINKA: Čistá grafická legenda pro predikční mapu vložená přímo pod ovladače
        st.markdown("""
        <br/>
        <div style='background: var(--tab-bg); padding: 15px; border-radius: 8px; border: 1px solid var(--tab-border); margin-top: 15px;'>
            <b style='color:var(--text-color); font-size:0.8rem; text-transform:uppercase; letter-spacing:0.5px;'>🗺️ Legenda rizik mapy</b>
            <hr style='border-color: var(--sidebar-hr); margin: 8px 0;'/>
            <div style='display: flex; align-items: center; margin-bottom: 8px;'>
                <div style='width: 12px; height: 12px; background-color: #2ec4b6; border-radius: 50%; margin-right: 10px;'></div>
                <span style='color: var(--text-color); font-size: 0.85rem;'><strong>Bezpečný stav</strong> (Dostatek kapacit)</span>
            </div>
            <div style='display: flex; align-items: center; margin-bottom: 8px;'>
                <div style='width: 12px; height: 12px; background-color: #ff9f1c; border-radius: 50%; margin-right: 10px;'></div>
                <span style='color: var(--text-color); font-size: 0.85rem;'><strong>Mírný deficit</strong> (Do limitu alarmu)</span>
            </div>
            <div style='display: flex; align-items: center;'>
                <div style='width: 12px; height: 12px; background-color: #dc3545; border-radius: 50%; margin-right: 10px;'></div>
                <span style='color: var(--text-color); font-size: 0.85rem;'><strong>Kritický stav</strong> (Překročen nastavený limit)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col_layout_right:
        predictions_raw = fetch_data("/api/predictions", {"year": pred_year, "capacity_deficit_threshold": deficit_threshold})

        predictions_val = copy.deepcopy(predictions_raw)
        for orp_key, o_data in predictions_val.items():
            is_target = (selected_orp == "Celý kraj" or orp_key == selected_orp)
            if is_target:
                o_data["current_capacity"] += sim_new_beds
                o_data["predicted_demand"] = max(0, int(o_data["predicted_demand"] * (1 - (sim_field_boost / 100.0))))

            new_gap = o_data["predicted_demand"] - o_data["current_capacity"]
            if o_data["current_capacity"] > 0:
                o_data["deficit_percent"] = round((new_gap / o_data["current_capacity"]) * 100.0, 1)
            else:
                o_data["deficit_percent"] = 100.0 if new_gap > 0 else 0.0

            o_data["stress_alert"] = o_data["deficit_percent"] >= deficit_threshold

        col_p1, col_p2, col_p3 = st.columns(3)

        if selected_orp == "Celý kraj":
            total_capacity_sim = sum(p["current_capacity"] for p in predictions_val.values())
            total_demand_sim = sum(p["predicted_demand"] for p in predictions_val.values())
            weighted_deficit_pct = round(((total_demand_sim - total_capacity_sim) / total_capacity_sim) * 100.0, 1) if total_capacity_sim > 0 else 0

            with col_p1:
                render_metric_card("Simulovaná poptávka", f"{total_demand_sim:,}".replace(",", " ") + " lůžek", "Po započtení terénu")
            with col_p2:
                render_metric_card("Simulovaná kapacita", f"{total_capacity_sim:,}".replace(",", " ") + " lůžek", f"Včetně +{sim_new_beds} lůžek")
            with col_p3:
                render_metric_card("Výsledný deficit kraje", f"{weighted_deficit_pct} %", "Stav celého kraje", "none", "glow-alert" if weighted_deficit_pct >= deficit_threshold else "")
        else:
            orp_pred = predictions_val[selected_orp]
            with col_p1:
                render_metric_card("Simulovaná poptávka", f"{orp_pred['predicted_demand']} lůžek", f"ORP {selected_orp}")
            with col_p2:
                render_metric_card("Simulovaná kapacita", f"{orp_pred['current_capacity']} lůžek", f"Původní: {predictions_raw[selected_orp]['current_capacity']}")
            with col_p3:
                render_metric_card("Deficit oblasti", f"{orp_pred['deficit_percent']} %", "Po simulaci investice", "none", "glow-alert" if orp_pred["stress_alert"] else "")

        st.markdown("<br/>", unsafe_allow_html=True)

        col_inner_map, col_inner_chart = st.columns([1.2, 1])

        with col_inner_map:
            m_pred = folium.Map(location=[50.55, 13.90], zoom_start=9, tiles=map_tiles)
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
                    fill_col = "#dc3545"
                elif deficit > 0:
                    fill_col = "#ff9f1c"
                else:
                    fill_col = "#2ec4b6"

                return {
                    "fillColor": fill_col,
                    "color": "#ffffff" if is_selected else "#444444",
                    "weight": 3 if is_selected else 1.2,
                    "fillOpacity": 0.7 if is_selected else 0.5,
                }

            tooltip_pred = folium.GeoJsonTooltip(
                fields=["name", "current_capacity", "predicted_demand", "deficit_percent"],
                aliases=["ORP:", "Kapacita lůžek:", "Očekávaná poptávka:", "Kapacitní deficit (%):"]
            )

            folium.GeoJson(
                data=pred_geo,
                style_function=pred_style_fn,
                tooltip=tooltip_pred,
                name="Predikce Deficitu"
            ).add_to(m_pred)

            map_pred_output = st_folium(m_pred, height=400, width='stretch', key="prediction_map")

            clicked_name = get_clicked_orp_name(map_pred_output)
            if clicked_name and clicked_name in indicators.keys():
                if clicked_name != st.session_state.selected_orp:
                    st.session_state.selected_orp = clicked_name
                    st.session_state.menu_version += 1
                    st.rerun()

        with col_inner_chart:
            active_orp = selected_orp if selected_orp != "Celý kraj" else "Ústí nad Labem"
            hist_data = fetch_data("/api/orp/demographics")[active_orp]

            from backend.forecasting import get_forecast_for_orp
            future_list = []
            for y in range(2026, 2036):
                forecast = get_forecast_for_orp(active_orp, y)
                if forecast:
                    future_list.append({
                        "year": y,
                        "total_pop": forecast["total_pop"],
                        "pop_65plus": forecast["pop_65plus"],
                        "pop_75plus": forecast["pop_75plus"]
                    })

            df_hist = pd.DataFrame(hist_data)
            df_fut = pd.DataFrame(future_list)
            df_all = pd.concat([df_hist, df_fut], ignore_index=True)

            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(x=df_all["year"], y=df_all["total_pop"], name="Celková populace", line=dict(color="#4285f4", width=3)))
            fig_trend.add_trace(go.Scatter(x=df_all["year"], y=df_all["pop_65plus"], name="Senioři 65+", line=dict(color="#ff9f1c", width=2, dash="dash")))
            fig_trend.add_trace(go.Scatter(x=df_all["year"], y=df_all["pop_75plus"], name="Senioři 75+", line=dict(color="#dc3545", width=2, dash="dot")))

            base_capacity = sum(s["capacity"] for s in services if s["orp"] == active_orp)
            sim_cap_line = base_capacity + sim_new_beds
            fig_trend.add_trace(go.Scatter(x=[2026, 2035], y=[sim_cap_line, sim_cap_line], name="Simulovaná kapacita lůžek", line=dict(color="#2ec4b6", width=2, dash="dashdot")))

            fig_trend.update_layout(
                template=plotly_template, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=font_color),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=10, r=10, t=40, b=10), height=400
            )
            fig_trend.update_xaxes(gridcolor=grid_color)
            fig_trend.update_yaxes(gridcolor=grid_color)
            st.plotly_chart(fig_trend, width='stretch')

    st.markdown("<hr style='border-color: var(--sidebar-hr); margin: 30px 0px;'/>", unsafe_allow_html=True)

    # 3. White Spots Index Ranking
    st.markdown(f"<h5 style='color: var(--text-color); font-weight: 600; margin-bottom: 15px;'>Identifikace \"Bílých míst\" (Nepokrytá území s vysokým rizikem v roce {pred_year})</h5>", unsafe_allow_html=True)

    # Toggle to show White Spot analysis
    show_white_spots = st.checkbox("Zobrazit detailní analýzu Bílých míst (White Spots Index)", value=True)

    if show_white_spots:
        white_spots = fetch_data("/api/white-spots", {"year": pred_year})
        df_ws = pd.DataFrame(white_spots)

        col_ws_chart, col_ws_desc = st.columns([5, 4])

        with col_ws_chart:
            fig_ws = px.bar(
                df_ws,
                x="white_spot_index",
                y="orp",
                orientation="h",
                color="white_spot_index",
                color_continuous_scale="Reds",
                labels={"white_spot_index": "Index Bílého místa (WSI)", "orp": ""},
                height=380
            )
            fig_ws.update_layout(
                template=plotly_template,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=font_color),
                margin=dict(l=10, r=10, t=10, b=10),
                coloraxis_showscale=False
            )
            fig_ws.update_xaxes(gridcolor=grid_color)
            fig_ws.update_yaxes(gridcolor=grid_color)
            st.plotly_chart(fig_ws, width='stretch')

        with col_ws_desc:
            st.markdown("""
            <div class="metric-card white-spot-card" style="margin-top: 15px;">
                <div style="font-weight: 800; font-size: 1.1rem; color: #ff6b6b; margin-bottom: 10px;">Metodika White Spot Indexu (WSI)</div>
                <p style="font-size: 0.9rem; color: var(--text-color); line-height: 1.5; margin-bottom: 10px;">
                    <strong>Index bílých míst (WSI)</strong> identifikuje regiony, které vyžadují naléhavou pozornost. Index kombinuje sociální stres (nezaměstnanost, exekuce, vyloučené lokality) a očekávané tempo stárnutí ku lokální kapacitě služeb.
                </p>
                <div style="background: var(--code-bg); padding: 12px; border-radius: 8px; border: 1px solid var(--tab-border); font-family: monospace; font-size: 0.85rem; color: #ffbe0b;">
                    WSI = (Socioekonomický stres * Růst populace 75+) * 100 / (Kapacita služeb + 10)
                </div>
            </div>
            """, unsafe_allow_html=True)

        df_table = df_ws.copy()
        df_table.columns = ["ORP", "Index Bílého místa (WSI)", "Nezaměstnanost (%)", "Exekuce (%)", "Celková kapacita (lůžka/klienti)", "Růst seniorů 75+ (%)"]
        st.dataframe(df_table, width='stretch', hide_index=True)

# Custom page footer matching style.css definitions
st.markdown("""
<div class="app-footer">
    Prediktivní Sociální Atlas Ústeckého kraje &copy; 2026 &bull; Vytvořeno pro podporu strategického rozvoje sociálních služeb.
</div>
""", unsafe_allow_html=True)