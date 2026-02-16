import threading
import time
import pandas as pd
import json
import plotly.utils
import plotly.graph_objs as go
from flask import Flask, render_template, jsonify
from strategies import MeanReversionStrategy

app = Flask(__name__)

# Initialize Strategy
bot = MeanReversionStrategy()
bot.fetch_data(days=60) # Initial Fetch
bot.run() # Initial Backtest

# Global state for the frontend
live_status = "Waiting for next candle..."

def live_runner():
    """Background thread to handle Forward Testing / Live Mode."""
    global live_status
    while True:
        try:
            # 1. Fetch just the latest candles (lightweight)
            latest = bot.exchange.fetch_ohlcv(bot.symbol, bot.timeframe, limit=5)
            last_candle = latest[-2] # The last CLOSED candle
            current_candle = latest[-1] # The UNFINISHED candle
            
            last_closed_time = pd.to_datetime(last_candle[0], unit='ms')
            
            # 2. Check if we have a NEW closed candle
            if last_closed_time > bot.df.index[-1]:
                live_status = f"New Candle Closed: {last_closed_time}. Updating..."
                
                # Update DataFrame
                new_row = {
                    'open': last_candle[1], 'high': last_candle[2], 
                    'low': last_candle[3], 'close': last_candle[4], 
                    'volume': last_candle[5]
                }
                # Create a DataFrame for the new row and concatenate
                new_df_row = pd.DataFrame([new_row], index=[last_closed_time])
                bot.df = pd.concat([bot.df, new_df_row])
                
                # Re-calc indicators (optimization: only for new row if possible)
                bot.prepare_indicators()
                
                # Apply Strategy on the new closed candle
                # We re-run the logic for the last step
                row = bot.df.iloc[-1]
                
                # Check Exits on previous candle logic
                if bot.position != 0:
                    is_exit, exit_price, pnl = bot.check_exit(row)
                    if is_exit:
                        bot.position = 0
                        # Record trade (simplified for live view)
                
                # Check Entries
                if bot.position == 0:
                    sig = bot.strategy(row)
                    if sig != 0:
                        bot.position = sig
                        bot.entry_price = row['close']
                        bot.entry_time = last_closed_time
                
                live_status = "Strategy Updated. Waiting..."
            else:
                # Handle Unfinished Candle (Live Price Update only)
                current_price = current_candle[4]
                live_status = f"Live: {current_price} | Pos: {bot.position}"

        except Exception as e:
            print(f"Live Error: {e}")
        
        time.sleep(10) # Check every 10 seconds

# Start Background Thread
t = threading.Thread(target=live_runner)
t.daemon = True
t.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    # Prepare Plotly JSON
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
        'trades': bot.trades[::-1], # Reverse order
        'live_status': live_status,
        'price_plot': json.loads(json.dumps(price_fig, cls=plotly.utils.PlotlyJSONEncoder)),
        'equity_plot': json.loads(json.dumps(equity_fig, cls=plotly.utils.PlotlyJSONEncoder))
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
