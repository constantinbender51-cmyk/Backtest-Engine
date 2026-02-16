import os
import pandas as pd
from flask import Flask, render_template, jsonify, send_from_directory
from strategies import Strategy 

# Ensure static folder exists for the chart
if not os.path.exists('static'):
    os.makedirs('static')

app = Flask(__name__)

# --- INIT ---
bot = Strategy()
bot.run()
bot.report_trades() # <--- PRINTS TRADES TO CONSOLE
bot.plot_matplotlib('static/chart.png') # <--- GENERATES PLOT

@app.route('/')
def index():
    # Pass cache buster to force image refresh
    return render_template('index.html', cache_buster=os.urandom(4).hex())

@app.route('/data')
def data():
    return jsonify({
        'stats': bot.get_stats(),
        'trades': bot.trades[::-1], # Newest first
        'live_status': "Backtest Complete. Live Mode Disabled for Debug."
    })

@app.route('/chart')
def chart():
    return send_from_directory('static', 'chart.png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
