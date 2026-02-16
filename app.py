import threading
import time
import pandas as pd
import os
from flask import Flask, render_template, jsonify, send_from_directory
from strategies import Strategy 

# Ensure static folder exists for the chart
if not os.path.exists('static'):
    os.makedirs('static')

app = Flask(__name__)

# --- INIT ---
bot = Strategy()
print(f"--> Initializing Strategy on {bot.symbol}")

# Pre-load data and run initial backtest to populate history
bot.run() 
bot.report_trades()
bot.plot_matplotlib('static/chart.png')

# Global state
live_status = "Bot Active. Monitoring..."

def live_runner():
    global live_status
    print("--> Live Runner Started")
    
    while True:
        try:
            # 1. Fetch latest data (limit=5 to minimize bandwidth)
            # We enableRateLimit in engine.py, so this is safe
            latest = bot.exchange.fetch_ohlcv(bot.symbol, bot.timeframe, limit=5)
            
            # Get the second to last candle (the last 'closed' candle)
            last_closed_data = latest[-2] 
            last_closed_time = pd.to_datetime(last_closed_data[0], unit='ms')
            
            # 2. Check if we have a NEW candle
            if last_closed_time > bot.df.index[-1]:
                live_status = f"New Candle Closed: {last_closed_time}"
                print(f"[LIVE] {live_status}")
                
                # Append new data
                new_row = pd.DataFrame([{
                    'open': last_closed_data[1], 'high': last_closed_data[2], 
                    'low': last_closed_data[3], 'close': last_closed_data[4], 
                    'volume': last_closed_data[5]
                }], index=[last_closed_time])
                
                bot.df = pd.concat([bot.df, new_row])
                
                # Update Indicators
                bot.prepare_indicators()
                row = bot.df.iloc[-1]
                
                # Check Exits
                if bot.position != 0:
                    is_exit, price, pnl_pct = bot.check_exit(row)
                    if is_exit:
                        pnl_amt = bot.equity * pnl_pct
                        bot.equity += pnl_amt
                        bot.trades.append({
                            'entry_time': bot.entry_time,
                            'exit_time': last_closed_time,
                            'type': 'Long' if bot.position == 1 else 'Short',
                            'price_in': bot.entry_price,
                            'price_out': price,
                            'pnl': pnl_amt,
                            'pnl_pct': pnl_pct * 100
                        })
                        bot.position = 0
                        print(f"[TRADE] EXIT detected. PnL: {pnl_amt}")

                # Check Entries
                if bot.position == 0:
                    sig = bot.strategy(row)
                    if sig != 0:
                        bot.position = sig
                        bot.entry_price = row['close']
                        bot.entry_time = last_closed_time
                        print(f"[TRADE] ENTRY detected. Direction: {sig}")

                # RE-PLOT CHART because data changed
                bot.plot_matplotlib('static/chart.png')
                
            else:
                # Just updating status, no new candle yet
                current_price = latest[-1][4]
                live_status = f"Waiting... | Price: {current_price} | Pos: {bot.position}"

        except Exception as e:
            print(f"[ERROR] Live Loop: {e}")
            time.sleep(5)
        
        # Sleep to respect rate limits and CPU
        time.sleep(10)

# Start the thread
t = threading.Thread(target=live_runner)
t.daemon = True
t.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    return jsonify({
        'stats': bot.get_stats(),
        'trades': bot.trades[::-1],
        'live_status': live_status
    })

@app.route('/chart')
def chart():
    # Helper to serve the static file
    return send_from_directory('static', 'chart.png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
