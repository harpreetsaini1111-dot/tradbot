from SmartApi import SmartConnect
import pyotp
import config
import pandas as pd
import time

# ---------------- LOGIN ----------------
def login():
    obj = SmartConnect(api_key=config.API_KEY)
    totp = pyotp.TOTP(config.TOTP_SECRET).now()
    obj.generateSession(config.CLIENT_ID, config.PASSWORD, totp)
    print("✅ LOGIN SUCCESS")
    return obj

# ---------------- DATA ----------------
def get_price(obj):
    data = obj.ltpData("NSE", config.SYMBOL, config.TOKEN)
    return data['data']['ltp']

# ---------------- INDICATORS ----------------
prices = []

def indicators(price):
    prices.append(price)

    df = pd.DataFrame(prices, columns=["close"])

    df["EMA"] = df["close"].ewm(span=10).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    return df.iloc[-1]

# ---------------- STRATEGY ----------------
def trend_strategy(ind):
    if pd.isna(ind["RSI"]):
        return "HOLD"

    price = ind["close"]
    ema = ind["EMA"]
    rsi = ind["RSI"]

    if rsi < 25:
        return "HOLD"

    if 25 <= rsi < 35:
        return "BUY"

    if price > ema and 55 < rsi < 70:
        return "BUY"

    if rsi > 80:
        return "SELL"

    if price < ema and 45 < rsi < 55:
        return "SELL"

    return "HOLD"

# ---------------- POSITION MANAGEMENT ----------------
position = None
entry_price = None
last_trade_time = 0

COOLDOWN = 30
STOPLOSS = 5
TARGET = 10

def manage(signal, price):
    global position, entry_price, last_trade_time

    current_time = time.time()

    # cooldown
    if current_time - last_trade_time < COOLDOWN:
        return None

    # entry
    if signal == "BUY" and position is None:
        position = "LONG"
        entry_price = price
        last_trade_time = current_time
        print(f"🟢 BUY @ {price}")
        return "BUY"

    # exit
    if position == "LONG":

        # target
        if price >= entry_price + TARGET:
            print(f"💰 TARGET HIT @ {price}")
            position = None
            last_trade_time = current_time
            return "SELL"

        # stoploss
        if price <= entry_price - STOPLOSS:
            print(f"🛑 STOPLOSS HIT @ {price}")
            position = None
            last_trade_time = current_time
            return "SELL"

        # signal exit
        if signal == "SELL":
            print(f"🔴 EXIT SIGNAL @ {price}")
            position = None
            last_trade_time = current_time
            return "SELL"

    return None

# ---------------- EXECUTION ----------------
def execute(obj, action):
    if action:
        print(f"🚀 EXECUTE: {action}")

        # ENABLE THIS ONLY WHEN READY
        """
        order = {
            "variety": "NORMAL",
            "tradingsymbol": config.SYMBOL,
            "symboltoken": config.TOKEN,
            "transactiontype": action,
            "exchange": "NSE",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "quantity": config.QTY
        }
        obj.placeOrder(order)
        """

# ---------------- MAIN ----------------
def main():
    obj = login()

    while True:
        price = get_price(obj)
        ind = indicators(price)

        signal = trend_strategy(ind)
        action = manage(signal, price)

        print(f"Price: {price:.2f} | EMA: {ind['EMA']:.2f} | RSI: {ind['RSI']:.2f} | Signal: {signal}")

        execute(obj, action)

        time.sleep(5)

if __name__ == "__main__":
    main()