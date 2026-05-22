import json
import os
import numpy as np

# Load local seed datasets
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

_cache = {}

def load_json_file(filename):
    """
    Load JSON files with in-memory caching to avoid redundant disk reads.
    """
    if filename not in _cache:
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            return {}
        with open(filepath, "r", encoding="utf-8") as f:
            _cache[filename] = json.load(f)
    return _cache[filename]

def get_forecast_for_orp(orp_name, target_year):
    """
    Project demographics for a specific ORP and target year using linear regression
    on historical data (2018-2025).
    """
    demographics = load_json_file("demographics_historical.json")
    if orp_name not in demographics:
        return None
    
    history = demographics[orp_name]
    years = np.array([h["year"] for h in history])
    
    total_pops = np.array([h["total_pop"] for h in history])
    pop_65 = np.array([h["pop_65plus"] for h in history])
    pop_75 = np.array([h["pop_75plus"] for h in history])
    migration = np.array([h["net_migration"] for h in history])
    
    # Fit linear models
    coeff_total = np.polyfit(years, total_pops, 1)
    coeff_65 = np.polyfit(years, pop_65, 1)
    coeff_75 = np.polyfit(years, pop_75, 1)
    coeff_mig = np.polyfit(years, migration, 1)
    
    # Predict target year
    pred_total = max(100, int(np.polyval(coeff_total, target_year)))
    pred_65 = max(0, int(np.polyval(coeff_65, target_year)))
    pred_75 = max(0, int(np.polyval(coeff_75, target_year)))
    pred_mig = int(np.polyval(coeff_mig, target_year))
    
    # Keep constraint: 75plus <= 65plus <= total
    pred_65 = min(pred_65, pred_total)
    pred_75 = min(pred_75, pred_65)
    
    return {
        "year": target_year,
        "total_pop": pred_total,
        "pop_65plus": pred_65,
        "pop_75plus": pred_75,
        "net_migration": pred_mig,
        # Reference historical 2025 values to compute growth
        "hist_2025_pop_75plus": history[-1]["pop_75plus"],
        "hist_2025_pop_65plus": history[-1]["pop_65plus"],
        "hist_2025_total_pop": history[-1]["total_pop"]
    }

def calculate_capacity_deficit(orp_name, target_year):
    """
    Compare predicted demand (modeled as a fraction of forecasted 75+ senior population)
    against current stationary capacities.
    """
    services = load_json_file("social_services.json")
    indicators = load_json_file("social_indicators.json")
    
    # 1. Sum up stationary care capacity (Senior Homes) in this ORP
    # Types: "Stationary Care (Home for Seniors)"
    current_capacity = sum(
        s["capacity"] for s in services 
        if s["orp"] == orp_name and "Stationary Care" in s["type"]
    )
    
    # Get demographic predictions
    forecast = get_forecast_for_orp(orp_name, target_year)
    if not forecast:
        return {"current_capacity": 0, "predicted_demand": 0, "deficit_percent": 0.0}
    
    # 2. Estimate predicted demand
    # Baseline model: In 2025, demand matches 105% of capacity (5% waitlist/shortage)
    # If an ORP has zero capacity (like Podbořany), we assume a baseline demand ratio 
    # of 8% of the 75+ population (average across Ústí region)
    if current_capacity > 0:
        base_demand_ratio = (current_capacity * 1.05) / forecast["hist_2025_pop_75plus"]
    else:
        base_demand_ratio = 0.08  # standard 8% coefficient
        
    predicted_demand = int(base_demand_ratio * forecast["pop_75plus"])
    
    # 3. Calculate Deficit
    if current_capacity > 0:
        deficit_percent = ((predicted_demand - current_capacity) / current_capacity) * 100.0
    else:
        # If no stationary care exists, but there is demand, deficit is 100%
        deficit_percent = 100.0 if predicted_demand > 0 else 0.0
        
    return {
        "current_capacity": current_capacity,
        "predicted_demand": predicted_demand,
        "deficit_percent": round(deficit_percent, 1),
        "total_pop": forecast["total_pop"],
        "pop_65plus": forecast["pop_65plus"],
        "pop_75plus": forecast["pop_75plus"],
        "net_migration": forecast["net_migration"]
    }

def get_white_spots(target_year):
    """
    Identifies and ranks ORPs where social distress is high, senior population is growing,
    but local social services capacity is low.
    """
    indicators = load_json_file("social_indicators.json")
    services = load_json_file("social_services.json")
    
    white_spots = []
    for orp, ind in indicators.items():
        # Get demographic forecast
        forecast = get_forecast_for_orp(orp, target_year)
        if not forecast:
            continue
            
        # Total local service capacity (stationary + field + shelter)
        total_capacity = sum(s["capacity"] for s in services if s["orp"] == orp)
        
        # Growth of 75+ seniors relative to 2025
        senior_growth = forecast["pop_75plus"] / forecast["hist_2025_pop_75plus"]
        
        # Social distress score
        distress_score = ind["unemployment_rate"] + ind["exekuce_rate"] + ind["excluded_localities_ratio"]
        
        # White Spot Index: high distress & high growth & low capacity
        # We add 10 to capacity in denominator to prevent division by zero and dampen smaller capacities
        white_spot_index = (distress_score * senior_growth * 100) / (total_capacity + 10)
        
        white_spots.append({
            "orp": orp,
            "white_spot_index": round(white_spot_index, 1),
            "unemployment_rate": ind["unemployment_rate"],
            "exekuce_rate": ind["exekuce_rate"],
            "total_capacity": total_capacity,
            "pop_75_growth_ratio": round((senior_growth - 1) * 100, 1) # percent growth
        })
        
    # Sort descending by index
    white_spots.sort(key=lambda x: x["white_spot_index"], reverse=True)
    return white_spots

if __name__ == "__main__":
    # Quick debug test
    print("Testing Bílina 2030 predictions:")
    print(calculate_capacity_deficit("Bílina", 2030))
    print("\nTesting White Spots for 2035:")
    print(get_white_spots(2035)[:3])
