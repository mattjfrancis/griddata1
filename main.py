import time
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Energy Grid Battery Simulator", layout="wide")

st.title("🔋 Dispatch Strategy Simulator")
st.markdown("""
Simulate how a battery dispatches based on:
- energy **price**
- **carbon intensity**
- **user demand**
- **tariff avoidance**
- multiple **dispatch strategies**

And view detailed **cost**, **carbon**, and **usage** insights.
""")

# Sidebar: Region and Battery Settings
st.sidebar.header("🌍 Region Settings")
region = st.sidebar.selectbox("Select Region", ["UK", "Germany", "Texas", "California", "France"])

region_profiles = {
    "UK": {"price_base": 120, "carbon_base": 250, "price_amp": 60, "carbon_amp": 100, "noise": 15},
    "Germany": {"price_base": 90, "carbon_base": 300, "price_amp": 50, "carbon_amp": 80, "noise": 15},
    "Texas": {"price_base": 60, "carbon_base": 400, "price_amp": 80, "carbon_amp": 120, "noise": 20},
    "California": {"price_base": 100, "carbon_base": 200, "price_amp": 70, "carbon_amp": 60, "noise": 10},
    "France": {"price_base": 80, "carbon_base": 100, "price_amp": 40, "carbon_amp": 30, "noise": 5},
}

profile = region_profiles[region]

st.sidebar.header("🔋 Battery Settings")
battery_capacity_kWh = st.sidebar.slider("Battery Capacity (kWh)", 5, 100, 20)
power_rating_kW = st.sidebar.slider("Power Rating (kW)", 1, 50, 5)
passive_discharge = st.sidebar.slider("Passive Discharge Rate (%/hr)", 0.0, 2.0, 0.2) / 100

# Tariff threshold
st.sidebar.header("💰 Tariff Avoidance")
tariff_threshold = st.sidebar.slider("High Tariff Threshold (£/MWh)", 150, 300, 200)

# Load Profile
st.sidebar.header("⚡ User Load Profile")
morning_demand = st.sidebar.slider("6am–12pm Demand (kW)", 0.0, 10.0, 2.0)
afternoon_demand = st.sidebar.slider("12pm–6pm Demand (kW)", 0.0, 10.0, 3.0)
evening_demand = st.sidebar.slider("6pm–12am Demand (kW)", 0.0, 10.0, 5.0)
night_demand = st.sidebar.slider("12am–6am Demand (kW)", 0.0, 10.0, 1.0)

# Strategy Select
st.sidebar.header("🧠 Strategy Selection")
strategy_choice = st.sidebar.selectbox("Choose Dispatch Strategy", [
    "Blended (Price + Carbon)",
    "Tariff Avoidance Only",
    "Price Arbitrage",
    "Carbon Minimizer"
])

# Config
battery_config = {
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.9,
    "step_size": power_rating_kW / battery_capacity_kWh / 2,
    "passive_discharge": passive_discharge,
    "tariff_threshold": tariff_threshold
}

def generate_daily_cycle(amplitude, base, noise, phase_shift=0):
    intervals = np.arange(96)
    hours = intervals / 4
    cycle = base + amplitude * np.sin((hours - phase_shift) * np.pi / 12)
    noise_component = np.random.normal(0, noise, size=96)
    return np.clip(cycle + noise_component, 0, None)

def generate_user_demand():
    profile = []
    for interval in range(96):
        hour = interval / 4
        if 6 <= hour < 12:
            demand = morning_demand
        elif 12 <= hour < 18:
            demand = afternoon_demand
        elif 18 <= hour < 24:
            demand = evening_demand
        else:
            demand = night_demand
        # Scale for 15-minute demand (kWh)
        demand_kWh = demand * 0.25
        profile.append(demand_kWh / battery_capacity_kWh)
    return profile

if "last_region" not in st.session_state or st.session_state["last_region"] != region:
    st.session_state["prices"] = generate_daily_cycle(profile["price_amp"], profile["price_base"], profile["noise"], phase_shift=18)
    st.session_state["carbon"] = generate_daily_cycle(profile["carbon_amp"], profile["carbon_base"], profile["noise"], phase_shift=16)
    st.session_state["timestamps"] = pd.date_range("2025-01-01", periods=96, freq="15min")
    st.session_state["last_region"] = region

prices = st.session_state["prices"]
carbon = st.session_state["carbon"]
user_demand_profile = generate_user_demand()
time_range = st.session_state["timestamps"]

def update_soc(soc, action, config, demand_kWh):
    step = config["step_size"]
    soc -= config["passive_discharge"]
    soc -= demand_kWh
    soc = max(0.0, soc)
    if action == "charge":
        soc = min(1.0, soc + step * config["charge_efficiency"])
    elif action == "discharge":
        soc = max(0.0, soc - step / config["discharge_efficiency"])
    return soc

def dispatch_strategy(prices, carbon, user_demand, soc, config, strategy):
    schedule = []
    for t, (p, c, demand_kWh) in enumerate(zip(prices, carbon, user_demand)):
        if strategy == "Tariff Avoidance Only":
            action = "charge" if p < config["tariff_threshold"] and soc < 1.0 else "idle"
        elif strategy == "Price Arbitrage":
            action = "charge" if p < 80 and soc < 1.0 else "discharge" if p > 150 and soc > 0.2 else "idle"
        elif strategy == "Carbon Minimizer":
            action = "charge" if c < 200 and soc < 1.0 else "discharge" if c > 400 and soc > 0.2 else "idle"
        else:
            price_score = 1 - (p - min(prices)) / (max(prices) - min(prices))
            carbon_score = 1 - (c - min(carbon)) / (max(carbon) - min(carbon))
            blended_score = 0.5 * carbon_score + 0.5 * price_score
            if blended_score > 0.7 and soc < 1.0:
                action = "charge"
            elif blended_score < 0.3 and soc > 0.2:
                action = "discharge"
            else:
                action = "idle"

        schedule.append({
            "time": t,
            "timestamp": time_range[t],
            "action": action,
            "price": p,
            "carbon": c,
            "soc": soc,
            "user_demand_kWh": demand_kWh * battery_capacity_kWh,
            "grid_energy_kWh": 0
        })

        before_soc = soc
        soc = update_soc(soc, action, config, demand_kWh)
        after_soc = soc
        schedule[-1]["grid_energy_kWh"] = abs(after_soc - before_soc) * battery_capacity_kWh

    return pd.DataFrame(schedule)

soc_start = 0.5
df_schedule = dispatch_strategy(prices, carbon, user_demand_profile, soc_start, battery_config, strategy_choice)

# ======== Summary Stats ========
total_energy_used = df_schedule["grid_energy_kWh"].sum()
total_cost = (df_schedule["price"] * df_schedule["grid_energy_kWh"] / 1000).sum()
total_emissions = (df_schedule["carbon"] * df_schedule["grid_energy_kWh"] / 1000).sum()
high_tariff_intervals = df_schedule[df_schedule["price"] > tariff_threshold].shape[0]

st.subheader("📈 Strategy Summary")
st.markdown(f"""
**Strategy:** `{strategy_choice}`  
- 🔌 **Total Energy Drawn from Grid:** `{total_energy_used:.2f} kWh`  
- 💸 **Estimated Cost:** `£{total_cost:.2f}`  
- 🟢 **Estimated Carbon Emissions:** `{total_emissions:.2f} kg CO₂`  
- ⛔ **High Tariff Hours Avoided:** `{high_tariff_intervals}/24`
""")

# ======== Visualization ========
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 Simulation Results")
    fig, axs = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
    axs[0].plot(time_range, df_schedule["price"], label="Price (£/MWh)")
    axs[0].set_ylabel("Price")
    axs[0].legend()
    axs[1].plot(time_range, df_schedule["carbon"], label="Carbon Intensity (gCO₂/kWh)", color="green")
    axs[1].set_ylabel("Carbon")
    axs[1].legend()
    axs[2].plot(time_range, df_schedule["user_demand_kWh"], label="User Demand (kWh)", color="orange")
    axs[2].set_ylabel("Demand")
    axs[2].legend()
    axs[3].plot(time_range, df_schedule["soc"], label="State of Charge", color="purple")
    action_colors = df_schedule["action"].map({"charge": "blue", "discharge": "red", "idle": "gray"})
    action_vals = df_schedule["action"].map({"charge": 1, "discharge": -1, "idle": 0})
    axs[3].scatter(time_range, action_vals, color=action_colors, label="Action", zorder=3)
    axs[3].set_ylabel("SOC / Action")
    axs[3].legend()
    plt.xlabel("Time")
    plt.tight_layout()
    st.pyplot(fig)

with col2:
    st.subheader("📋 Dispatch Log")
    st.dataframe(df_schedule[["timestamp", "action", "price", "carbon", "user_demand_kWh", "grid_energy_kWh", "soc"]].style.format({
        "price": "£{:.0f}",
        "carbon": "{:.0f} g",
        "soc": "{:.2f}",
        "user_demand_kWh": "{:.2f}",
        "grid_energy_kWh": "{:.2f}"
    }))

# === Compare All Strategies ===
st.subheader("🧠 Strategy Comparison Overview")

def run_all_strategies():
    strategies = [
        "Blended (Price + Carbon)",
        "Tariff Avoidance Only",
        "Price Arbitrage",
        "Carbon Minimizer"
    ]
    comparison = []
    for strategy in strategies:
        df = dispatch_strategy(prices, carbon, user_demand_profile, soc_start, battery_config, strategy)
        total_energy = df["grid_energy_kWh"].sum()
        total_cost = (df["price"] * df["grid_energy_kWh"] / 1000).sum()
        total_emissions = (df["carbon"] * df["grid_energy_kWh"] / 1000).sum()
        high_tariff_hours = df[df["price"] > tariff_threshold].shape[0]
        comparison.append({
            "Strategy": strategy,
            "Energy (kWh)": round(total_energy, 2),
            "Cost (£)": round(total_cost, 2),
            "CO₂ (kg)": round(total_emissions, 2),
            "Tariff Hours Avoided": 24 - high_tariff_hours
        })
    return pd.DataFrame(comparison)

df_all_strategies = run_all_strategies()
best_by_cost = df_all_strategies["Cost (£)"].idxmin()
best_by_emissions = df_all_strategies["CO₂ (kg)"].idxmin()

df_all_strategies["🏆 Best (Cost)"] = ""
df_all_strategies.loc[best_by_cost, "🏆 Best (Cost)"] = "✅"
df_all_strategies["🏆 Best (Carbon)"] = ""
df_all_strategies.loc[best_by_emissions, "🏆 Best (Carbon)"] = "✅"

st.dataframe(df_all_strategies.style.format({
    "Cost (£)": "£{:.2f}",
    "CO₂ (kg)": "{:.2f}",
    "Energy (kWh)": "{:.2f}"
}).highlight_min(subset=["Cost (£)", "CO₂ (kg)"], color="lightgreen"))

st.caption("✅ This summary helps identify the most cost-effective and carbon-efficient strategy based on your grid conditions and load profile.")

st.subheader("🎞️ Battery Dispatch Animation")

if st.button("▶️ Play Animation"):
    placeholder = st.empty()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.set_title("Battery SOC Over Time")
    ax.set_ylabel("SOC")
    ax.set_ylim(0, 1)
    soc_vals = []
    action_colors = {"charge": "blue", "discharge": "red", "idle": "gray"}

    for i in range(len(df_schedule)):
        ax.clear()
        ax.set_title(f"Battery SOC - Time: {df_schedule['timestamp'][i].strftime('%H:%M')}")
        ax.set_ylabel("SOC")
        ax.set_ylim(0, 1)
        ax.set_xlim(0, len(df_schedule))
        ax.plot(range(i+1), df_schedule["soc"][:i+1], label="SOC", color="purple")
        ax.scatter(i, df_schedule["soc"][i], color=action_colors[df_schedule["action"][i]], label=df_schedule["action"][i], zorder=5)
        ax.legend()
        placeholder.pyplot(fig)
        time.sleep(0.1)  # Delay per frame
