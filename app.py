import streamlit as st
import time
from SmartApi import SmartConnect
import pyotp
import config
import pandas as pd
import os
import json

# ================= LOGIN =================
@st.cache_resource
def login():
    obj = SmartConnect(api_key=config.API_KEY)
    totp = pyotp.TOTP(config.TOTP_SECRET).now()
    obj.generateSession(config.CLIENT_ID, config.PASSWORD, totp)
    return obj

obj = login()

# ================= UI =================
st.set_page_config(layout="wide")
st.title("💰 INVESTMENT BOT (FINAL PRO VERSION)")

# ================= LOAD STOCKS =================
@st.cache_data
def load_nifty50():
    df = pd.read_csv("MW-NIFTY-50-10-Apr-2026.csv")
    df.columns = df.columns.str.strip()
    stocks = df["SYMBOL"].dropna().unique().tolist()
    stocks = [s for s in stocks if s != "NIFTY 50"]
    return sorted(stocks)

stocks = load_nifty50()

# ================= SEARCH =================
search = st.sidebar.text_input("🔍 Search")
filtered = [s for s in stocks if search.upper() in s]
selected_stock = st.sidebar.selectbox("Select Stock", filtered)

# ================= MODE =================
paper_mode = st.sidebar.toggle("Paper Trading", True)
live_mode = st.sidebar.toggle("Live Trading", False)

if paper_mode and live_mode:
    st.error("❌ Cannot enable both")
    st.stop()

# ================= STRATEGY STORAGE =================
STRATEGY_FILE = "strategies.json"

def load_strategies():
    if os.path.exists(STRATEGY_FILE):
        with open(STRATEGY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_strategies(data):
    with open(STRATEGY_FILE, "w") as f:
        json.dump(data, f, indent=4)

strategies = load_strategies()

# ================= STRATEGY UI =================
st.sidebar.subheader("📂 Strategy Manager")

strategy_names = list(strategies.keys())
selected_strategy = st.sidebar.selectbox("Load Strategy", ["None"] + strategy_names)
new_strategy_name = st.sidebar.text_input("Save Strategy As")

buy_price = st.sidebar.number_input("Buy Below Price", value=0.0)
buy_qty = st.sidebar.number_input("Buy Qty", value=5)
dip_percent = st.sidebar.number_input("Dip %", value=3.0)
target_price = st.sidebar.number_input("Target Price", value=0.0)

# LOAD STRATEGY
if selected_strategy != "None":
    s = strategies[selected_strategy]
    buy_price = s["buy_price"]
    buy_qty = s["buy_qty"]
    dip_percent = s["dip_percent"]
    target_price = s["target_price"]

# SAVE STRATEGY
if st.sidebar.button("💾 Save Strategy"):
    if new_strategy_name:
        strategies[new_strategy_name] = {
            "buy_price": buy_price,
            "buy_qty": buy_qty,
            "dip_percent": dip_percent,
            "target_price": target_price
        }
        save_strategies(strategies)
        st.sidebar.success("Saved!")

# ================= TOKEN CACHE =================
TOKEN_FILE = "tokens.json"

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=4)

token_cache = load_tokens()

def get_token(symbol):

    if symbol in token_cache:
        return token_cache[symbol]

    try:
        data = obj.searchScrip("NSE", symbol)

        for i in data.get("data", []):
            if i["tradingsymbol"] == symbol + "-EQ":

                token_cache[symbol] = i["symboltoken"]
                save_tokens(token_cache)

                return i["symboltoken"]

    except Exception as e:
        st.warning(f"Token fetch error: {e}")

    return None

symbol = selected_stock + "-EQ"
token = get_token(selected_stock)

if token is None:
    st.error("Token fetch failed")
    st.stop()

exchange = "NSE"

# ================= SESSION =================
if "portfolio" not in st.session_state:
    st.session_state.portfolio = {}

if "last_buy_price" not in st.session_state:
    st.session_state.last_buy_price = None

# ================= PRICE =================
def get_price():
    try:
        return obj.ltpData(exchange, symbol, token)["data"]["ltp"]
    except:
        return None

price = get_price()
st.subheader(f"{symbol} | Price: {price}")

# ================= PORTFOLIO =================
def update_portfolio(symbol, qty, price):

    if price is None:
        return

    if symbol not in st.session_state.portfolio:
        st.session_state.portfolio[symbol] = {"qty": 0, "invested": 0}

    st.session_state.portfolio[symbol]["qty"] += qty
    st.session_state.portfolio[symbol]["invested"] += qty * price

# ================= ORDER =================
def place_order(side, quantity):

    current_price = get_price()

    if current_price is None:
        st.error("Price unavailable")
        return

    # PAPER MODE
    if paper_mode:
        st.info(f"🧪 PAPER {side} {quantity} @ {current_price}")

        if side == "BUY":
            update_portfolio(symbol, quantity, current_price)
            st.session_state.last_buy_price = current_price

        elif side == "SELL":
            if symbol in st.session_state.portfolio:
                st.session_state.portfolio[symbol]["qty"] = max(
                    0,
                    st.session_state.portfolio[symbol]["qty"] - quantity
                )
        return

    # LIVE MODE
    if live_mode:
        try:
            obj.placeOrder({
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": side,
                "exchange": exchange,
                "ordertype": "MARKET",
                "producttype": "DELIVERY",
                "duration": "DAY",
                "quantity": quantity
            })
            st.success(f"{side} EXECUTED")
        except Exception as e:
            st.error(e)

# ================= MANUAL =================
st.subheader("🖱️ Manual Control")

manual_qty = st.number_input("Manual Qty", value=1)

c1, c2 = st.columns(2)

if c1.button("BUY"):
    place_order("BUY", manual_qty)

if c2.button("SELL"):
    total = st.session_state.portfolio.get(symbol, {}).get("qty", 0)

    if total > 0:
        place_order("SELL", total)
    else:
        st.warning("No holdings")

# ================= STRATEGY =================
if price:

    if buy_price > 0 and price <= buy_price:
        place_order("BUY", buy_qty)

    if st.session_state.last_buy_price:
        drop = ((st.session_state.last_buy_price - price) / st.session_state.last_buy_price) * 100

        if drop >= dip_percent:
            place_order("BUY", buy_qty)

    if target_price > 0 and price >= target_price:
        total = st.session_state.portfolio.get(symbol, {}).get("qty", 0)

        if total > 0:
            place_order("SELL", total)

# ================= PORTFOLIO =================
st.subheader("📊 Portfolio")

data = []
total_val = 0
total_inv = 0

for sym, val in st.session_state.portfolio.items():

    tok = get_token(sym.replace("-EQ",""))

    try:
        cp = obj.ltpData("NSE", sym, tok)["data"]["ltp"]
    except:
        cp = 0

    value = val["qty"] * cp

    data.append({
        "Stock": sym,
        "Qty": val["qty"],
        "Invested": val["invested"],
        "Value": value
    })

    total_val += value
    total_inv += val["invested"]

df = pd.DataFrame(data)

if not df.empty:
    st.dataframe(df)
    st.metric("Invested", total_inv)
    st.metric("Value", total_val)
    st.metric("PnL", total_val - total_inv)
else:
    st.write("No holdings")

# ================= REFRESH =================
time.sleep(10)
st.rerun()