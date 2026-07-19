import requests, time, os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BINANCE_URL = "https://fapi.binance.com"
MIN_SCORE = 75

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"alive")

def run_server():
    try:
        port = int(os.getenv("PORT", 10000))
        HTTPServer(('0.0.0.0', port), H).serve_forever()
    except:
        pass

Thread(target=run_server, daemon=True).start()

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except:
        pass

def get_klines(symbol, limit=100):
    url = f"{BINANCE_URL}/fapi/v1/klines?symbol={symbol}&interval=15m&limit={limit}"
    return requests.get(url, timeout=10).json()

def get_tickers():
    return requests.get(f"{BINANCE_URL}/fapi/v1/ticker/24hr", timeout=10).json()

def get_orderbook(symbol):
    try:
        r = requests.get(f"{BINANCE_URL}/fapi/v1/depth?symbol={symbol}&limit=10", timeout=5).json()
        top = sum([float(b[1]) for b in r['bids'][:5]])
        nxt = sum([float(b[1]) for b in r['bids'][5:10]])
        if nxt == 0:
            return 1.0, False
        ratio = top / nxt
        return ratio, ratio < 0.9
    except:
        return 1.0, False

def calc_rsi(closes, period=14):
    gains = []
    losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(d if d > 0 else 0)
        losses.append(-d if d < 0 else 0)
    if len(gains) < period:
        return 50
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 70
    rs = ag / al
    return 100 - (100 / (1 + rs))

def scan_symbol(symbol, btc_change):
    try:
        k = get_klines(symbol, 100)
        if len(k) < 20:
            return
        o = [float(x[1]) for x in k]
        h = [float(x[2]) for x in k]
        c = [float(x[4]) for x in k]
        v = [float(x[5]) for x in k]
        if not (c[-1] > c[-2] > c[-3] and c[-1] > o[-1]):
            return
        hh = h[-1] > h[-2] and h[-2] > h[-3]
        vol_ratio = v[-1] / (sum(v[-10:-1]) / 9 + 1e-9)
        rsi_now = calc_rsi(c[-15:])
        rsi_prev = calc_rsi(c[-20:-5])
        rsi_div = (c[-1] > c[-5]) and (rsi_now < rsi_prev)
        body = abs(c[-1] - o[-1])
        upper = h[-1] - max(c[-1], o[-1])
        wick_ratio = upper / (body + 0.00001)
        if vol_ratio > 0.65 or not rsi_div or wick_ratio < 0.4 or not hh:
            return
        if btc_change > 1.2:
            return
        ob_ratio, thinning = get_orderbook(symbol)
        score = 0
        if vol_ratio < 0.5:
            score += 30
        elif vol_ratio < 0.65:
            score += 20
        if rsi_div:
            score += 25
        if wick_ratio > 0.6:
            score += 20
        else:
            score += 10
        if thinning:
            score += 15
        score += 10
        if score < MIN_SCORE:
            return
        entry = h[-1] * 1.002
        stop = entry * 1.015
        tp1 = c[-1] * 0.96
        tp2 = c[-1] * 0.92
        msg = f"🚨 PRE-DEATH: {symbol}\nScore: {score}/100 | Vol {vol_ratio:.2f}x | Wick {wick_ratio:.2f}x | OB {ob_ratio:.2f}x\nENTRY {entry:.4f}\nSTOP {stop:.4f}\nTP1 {tp1:.4f} | TP2 {tp2:.4f}\nBTC {btc_change:.2f}% - Dies in 1-3 candles"
        print(msg)
        send_telegram(msg)
    except Exception as e:
        print(f"{symbol} err {e}")

print("CLOUD STARTED")
send_telegram("✅ PRE-DEATH CATCHER is now LIVE in the cloud - scanning every 3 mins")

while True:
    try:
        btc_k = get_klines("BTCUSDT", 10)
        btc_c = [float(x[4]) for x in btc_k]
        btc_change = (btc_c[-1] - btc_c[-4]) / btc_c[-4] * 100
        tickers = get_tickers()
        sorted_t = sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
        scan_list = [t['symbol'] for t in sorted_t if 'USDT' in t['symbol']][:20]
        for sym in scan_list:
            scan_symbol(sym, btc_change)
            time.sleep(0.3)
        print("Scan done, sleeping 180s")
        time.sleep(180)
    except Exception as e:
        print(f"Loop err {e}")
        time.sleep(10)
