import threading
import time
import pandas as pd
import json
import plotly.utils
import plotly.graph_objs as go
from flask import Flask, render_template, jsonify
from strategies import Strategy 

app = Flask(__name__)

# --- INIT ---
bot = Strategy()
print(f"--> Running Strategy on {bot.symbol}")
bot.run()

# Global state
live_status = "Bot Initialized."

def live_runner():
    global live_status
    while True:
        try:
            latest = bot.exchange.fetch_ohlcv(bot.symbol, bot.timeframe, limit=5)
            last_candle = latest[-2] 
            last_closed_time = pd.to_datetime(last_candle[0], unit='ms')
            
            if last_closed_time > bot.df.index[-1]:
                live_status = f"New Candle: {last_closed_time}"
                
                # Update Data
                new_row = pd.DataFrame([{
                    'open': last_candle[1], 'high': last_candle[2], 
                    'low': last_candle[3], 'close': last_candle[4], 
                    'volume': last_candle[5]
                }], index=[last_closed_time])
                bot.df = pd.concat([bot.df, new_row])
                
                # Update Indicators & Signals
                bot.prepare_indicators()
                row = bot.df.iloc[-1]
                
                # Check Exits
                if bot.position != 0:
                    is_exit, _, _ = bot.check_exit(row)
                    if is_exit: bot.position = 0
                
                # Check Entries
                if bot.position == 0:
                    sig = bot.strategy(row)
                    if sig != 0:
                        bot.position = sig
                        bot.entry_price = row['close']
                        bot.entry_time = last_closed_time
            else:
                live_status = f"Live: {latest[-1][4]} | Pos: {bot.position}"

        except Exception as e:
            print(f"Live Error: {e}")
            time.sleep(5)
        
        time.sleep(10)

t = threading.Thread(target=live_runner)
t.daemon = True
t.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    # Plots
    price_fig = go.Figure(data=[go.Candlestick(
        x=bot.df.index,
        open=bot.df['open'], high=bot.df['high'],
        low=bot.df['low'], close=bot.df['close']
    )])
    price_fig.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=0, b=0), height=300)

    equity_df = pd.DataFrame(bot.equity_curve)
    equity_fig = go.Figure(data=[go.Scatter(x=equity_df['time'], y=equity_df['equity'], line=dict(color='#00ff00'))])
    equity_fig.update_layout(template='plotly_dark', margin=dict(l=0, r=0, t=0, b=0), height=200)

    return jsonify({
        'stats': bot.get_stats(),
        'trades': bot.trades[::-1],
        'live_status': live_status,
        'price_plot': json.loads(json.dumps(price_fig, cls=plotly.utils.PlotlyJSONEncoder)),
        'equity_plot': json.loads(json.dumps(equity_fig, cls=plotly.utils.PlotlyJSONEncoder))
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
