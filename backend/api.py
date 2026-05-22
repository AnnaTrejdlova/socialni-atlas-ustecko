import os
import json
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.forecasting import (
    calculate_capacity_deficit,
    get_white_spots,
    DATA_DIR,
    load_json_file
)

app = FastAPI(
    title="Predictive Social Atlas API",
    description="Backend API for the Ústí nad Labem Region Social Atlas and Demographic Predictions",
    version="1.0.0"
)

# Enable CORS for frontend cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "Prediktivní Sociální Atlas Ústeckého kraje",
        "endpoints": [
            "/api/orp/geojson",
            "/api/orp/indicators",
            "/api/orp/demographics",
            "/api/social-services",
            "/api/predictions",
            "/api/white-spots"
        ]
    }

@app.get("/api/orp/geojson")
def get_geojson():
    """Return the simplified GeoJSON boundaries for the 16 Ústí Region ORPs."""
    data = load_json_file("orp_usti.geojson")
    if not data:
        raise HTTPException(status_code=404, detail="File orp_usti.geojson not found.")
    return data

@app.get("/api/orp/indicators")
def get_indicators():
    """Return current social distress indicators per ORP."""
    data = load_json_file("social_indicators.json")
    if not data:
        raise HTTPException(status_code=404, detail="File social_indicators.json not found.")
    return data

@app.get("/api/orp/demographics")
def get_demographics_historical():
    """Return historical demographics (2018-2025) per ORP."""
    data = load_json_file("demographics_historical.json")
    if not data:
        raise HTTPException(status_code=404, detail="File demographics_historical.json not found.")
    return data

@app.get("/api/orp/cssz")
def get_cssz_data():
    """Return mocked CSSZ pension data per ORP."""
    data = load_json_file("cssz_data.json")
    if not data:
        raise HTTPException(status_code=404, detail="File cssz_data.json not found.")
    return data

@app.get("/api/social-services")
def get_social_services():
    """Return the registry of social services (GPS, capacity, types)."""
    data = load_json_file("social_services.json")
    if not data:
        raise HTTPException(status_code=404, detail="File social_services.json not found.")
    return data

@app.get("/api/predictions")
def get_predictions(
    year: int = Query(2030, ge=2026, le=2035),
    capacity_deficit_threshold: float = Query(20.0, description="Deficit threshold above which ORP triggers stress alert (colored red)")
):
    """
    Get demographic forecasts and capacity deficit analysis for all ORPs
    for a given year and deficit threshold.
    """
    try:
        indicators = load_json_file("social_indicators.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    predictions = {}
    for orp in indicators.keys():
        deficit_info = calculate_capacity_deficit(orp, year)

        # Determine stress alert
        stress_alert = False
        if deficit_info["deficit_percent"] >= capacity_deficit_threshold:
            stress_alert = True

        predictions[orp] = {
            "orp": orp,
            "year": year,
            **deficit_info,
            "stress_alert": stress_alert,
            # Merging social distress indicators for overlay
            "unemployment_rate": indicators[orp]["unemployment_rate"],
            "exekuce_rate": indicators[orp]["exekuce_rate"],
            "excluded_localities_ratio": indicators[orp]["excluded_localities_ratio"]
        }

    return predictions

@app.get("/api/white-spots")
def get_white_spots_list(
    year: int = Query(2030, ge=2026, le=2035)
):
    """Get the ranked white spots (underserved areas of high social distress) for a given year."""
    return get_white_spots(year)
