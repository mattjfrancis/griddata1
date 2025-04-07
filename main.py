
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import time
import requests

st.set_page_config(page_title="FlexKit Strategy Explorer", layout="wide")

# --- Helper Functions ---
def get_carbon_data():
    try:
        r = requests.get("https://api.carbonintensity.org.uk/intensity")
        data = r.json()["data"]
        base = data[0]["intensity"]["forecast"]
        carbon = base + 60 * np.cos(np.linspace(0, 2 * np.pi, 96)) + np.random.normal(0, 20, 96)
        return np.clip(carbon, 100, 500)
    except:
        return 250 + 60 * np.cos(np.linspace(0, 2 * np.pi, 96))

def get_price_data():
    return 100 + 40 * np.sin(np.linspace(0, 2 * np.pi, 96)) + np.random.normal(0, 10, 96)

def get_reg_price():
    return 0.3 + 0.2 * np.cos(np.linspace(0, 2 * np.pi, 96)) + np.random.normal(0, 0.05, 96)

def simulate_strategy(name, price, carbon, reg_price, battery_kWh, power_kW, soc_start, max_reg_share, participate):
    soc = soc_start
    steps = len(price)
    soc_series, actions, grid_energy, reg_revenue, carbon_offset = [], [], [], [], []

    for i in range(steps):
        p, c, r = price[i], carbon[i], reg_price[i]
        action = "idle"
        if name == "Price Arbitrage":
            if p < 90 and soc < 1.0:
                action = "charge"
            elif p > 130 and soc > 0.2:
                action = "discharge"
        elif name == "Carbon Minimizer":
            if c < 200 and soc < 1.0:
                action = "charge"
            elif c > 400 and soc > 0.2:
                action = "discharge"
        elif name == "Blended":
            score = 0.5 * (1 - (p - min(price))/(max(price)-min(price))) + 0.5 * (1 - (c - min(carbon))/(max(carbon)-min(carbon)))
            if score > 0.7 and soc < 1.0:
                action = "charge"
            elif score < 0.3 and soc > 0.2:
                action = "discharge"
        else:
            action = "idle"

        if action == "charge":
            soc += power_kW / battery_kWh / 4
            energy = power_kW / 4
            grid_energy.append(energy)
            carbon_offset.append(0)
            reg_revenue.append(0)
        elif action == "discharge":
            soc -= power_kW / battery_kWh / 4
            energy = power_kW / 4
            grid_energy.append(0)
            carbon_offset.append(energy * c / 1000)
            reg_revenue.append(0)
        else:
            grid_energy.append(0)
            carbon_offset.append(0)
            if participate:
                capacity = battery_kWh * max_reg_share
                reg_revenue.append(capacity * r / 4)
            else:
                reg_revenue.append(0)

        soc = np.clip(soc, 0.0, 1.0)
        soc_series.append(soc)
        actions.append(action)

    return pd.DataFrame({
        "Time": pd.date_range("2025-01-01", periods=steps, freq="15min"),
        "SOC": soc_series,
        "Action": actions,
        "Grid Energy (kWh)": grid_energy,
        "Reg Revenue (£)": reg_revenue,
        "CO2 Offset (kg)": carbon_offset
    })

# --- Forecast Data ---
carbon = get_carbon_data()
price = get_price_data()
reg_price = get_reg_price()
steps = len(price)

# --- Sidebar Settings ---
st.sidebar.header("Battery Settings")
battery_kWh = st.sidebar.slider("Battery Capacity", 10, 100, 30)
power_kW = st.sidebar.slider("Power Rating", 1, 20, 5)
soc_start = st.sidebar.slider("Start SOC", 0.0, 1.0, 0.5, 0.05)
participate = st.sidebar.checkbox("Enable Grid Support", True)
max_reg_share = st.sidebar.slider("Regulation Share", 0.0, 0.5, 0.1)
speed = st.sidebar.slider("Animation Speed", 0.01, 0.3, 0.05)

# --- Simulations ---
strategies = ["Price Arbitrage", "Carbon Minimizer", "Blended"]
results = {s: simulate_strategy(s, price, carbon, reg_price, battery_kWh, power_kW, soc_start, max_reg_share, participate) for s in strategies}

# --- Tabs ---
tab1, tab2 = st.tabs(["📊 Strategy Comparison", "📡 Dashboard"])

with tab1:
    st.header("Strategy Comparison")
    fig, ax = plt.subplots(figsize=(10, 5))
    for s in strategies:
        ax.plot(results[s]["Time"], results[s]["SOC"], label=s)
    ax.set_ylabel("State of Charge")
    ax.legend()
    st.pyplot(fig)

    fig2, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for s in strategies:
        ax1.plot(results[s]["Time"], results[s]["Reg Revenue (£)"].cumsum(), label=s)
        ax2.plot(results[s]["Time"], results[s]["CO2 Offset (kg)"].cumsum(), label=s)
    ax1.set_ylabel("Revenue (£)")
    ax2.set_ylabel("CO₂ Offset (kg)")
    ax2.set_xlabel("Time")
    ax1.legend()
    ax2.legend()
    st.pyplot(fig2)


# --- Animated Visualization ---
st.header("Animated SOC View (24h - 15min steps)")
plot = st.empty()
progress = st.progress(0)

for t in range(steps):
    fig, ax = plt.subplots(figsize=(10, 5))
    for s in strategies:
        ax.plot(results[s]["Time"][:t+1], results[s]["SOC"][:t+1], label=s)
    ax.axvline(results[strategies[0]]["Time"][t], color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("SOC")
    ax.legend()
    plot.pyplot(fig)
    progress.progress(t / (steps - 1))
    time.sleep(speed)

with tab2:

    st.header("Live Dashboard (Simulated)")
    for s in strategies:
        df = results[s]
        st.subheader(f"🔍 {s}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Energy", f"{df['Grid Energy (kWh)'].sum():.2f} kWh")
        col2.metric("Carbon Offset", f"{df['CO2 Offset (kg)'].sum():.2f} kg")
        col3.metric("Revenue", f"£{df['Reg Revenue (£)'].sum():.2f}")
 
