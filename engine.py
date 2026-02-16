import ccxt
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime

DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

class BacktestEngine:
    def __init__(self, symbol='BTC/USDT', timeframe='1h', initial_equity=10000):
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange = ccxt.binance()
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.df = pd.DataFrame()
        self.trades = []
        self.equity_curve = []
        
        # Risk Management Defaults
        self.sl_pct = 0.02
        self.tp_pct = 0.04
        self.trailing_sl_pct = None # Set to 0.0X to enable

        # State
        self.position = 0 # 1 (Long), -1 (Short), 0 (Flat)
        self.entry_price = 0.0
        self.entry_time = None
        self.highest_price = 0.0 # For trailing stop

    def fetch_data(self, days=30):
        """Fetches OHLC data from Binance and saves to disk."""
        print(f"Fetching {days} days of {self.symbol} data...")
        since = self.exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
        all_candles = []
        
        while since < self.exchange.milliseconds():
            candles = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, since=since, limit=1000)
            if not candles: break
            since = candles[-1][0] + 1
            all_candles.extend(candles)
            
        # Deduplicate and Save
        new_df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        new_df['timestamp'] = pd.to_datetime(new_df['timestamp'], unit='ms')
        new_df.set_index('timestamp', inplace=True)
        new_df = new_df[~new_df.index.duplicated(keep='first')]
        
        path = f"{DATA_DIR}/{self.symbol.replace('/','')}_{self.timeframe}.csv"
        new_df.to_csv(path)
        self.df = new_df
        return self.df

    def load_data(self):
        path = f"{DATA_DIR}/{self.symbol.replace('/','')}_{self.timeframe}.csv"
        if os.path.exists(path):
            self.df = pd.read_csv(path, index_col='timestamp', parse_dates=True)
        else:
            self.fetch_data()

    def strategy(self, row):
        """User overrides this method. Returns 1, -1, or 0."""
        return 0

    def check_exit(self, row):
        """Checks High/Low for SL/TP hits before Close."""
        if self.position == 0: return False, 0, 0

        price = row['close']
        pnl_pct = 0
        exit_price = price
        reason = None

        # Long Logic
        if self.position == 1:
            # Check Stop Loss (Low)
            sl_price = self.entry_price * (1 - self.sl_pct)
            if row['low'] <= sl_price:
                return True, sl_price, -self.sl_pct
            
            # Check Take Profit (High)
            tp_price = self.entry_price * (1 + self.tp_pct)
            if row['high'] >= tp_price:
                return True, tp_price, self.tp_pct
                
        # Short Logic
        elif self.position == -1:
            # Check Stop Loss (High)
            sl_price = self.entry_price * (1 + self.sl_pct)
            if row['high'] >= sl_price:
                return True, sl_price, -self.sl_pct
                
            # Check Take Profit (Low)
            tp_price = self.entry_price * (1 - self.tp_pct)
            if row['low'] <= tp_price:
                return True, tp_price, self.tp_pct

        return False, 0, 0

    def run(self):
        """Iterates through data to simulate trades."""
        self.load_data()
        self.trades = []
        self.equity = self.initial_equity
        self.equity_curve = [{'time': self.df.index[0], 'equity': self.equity}]
        self.position = 0

        # Iterate row by row
        for i in range(len(self.df)):
            row = self.df.iloc[i]
            timestamp = self.df.index[i]

            # 1. Check Stops/Exits on EXISTING position using current candle High/Low
            if self.position != 0:
                is_exit, exit_price, pnl_pct = self.check_exit(row)
                if is_exit:
                    pnl_amt = self.equity * pnl_pct
                    self.equity += pnl_amt
                    self.trades.append({
                        'entry_time': self.entry_time,
                        'exit_time': timestamp,
                        'type': 'Long' if self.position == 1 else 'Short',
                        'price_in': self.entry_price,
                        'price_out': exit_price,
                        'pnl': pnl_amt,
                        'pnl_pct': pnl_pct * 100
                    })
                    self.position = 0
            
            # 2. Update Equity Curve (Mark to Market for visualization)
            if self.position != 0:
                curr_pnl_pct = (row['close'] - self.entry_price) / self.entry_price
                if self.position == -1: curr_pnl_pct *= -1
                current_equity = self.equity * (1 + curr_pnl_pct)
            else:
                current_equity = self.equity
            
            self.equity_curve.append({'time': timestamp, 'equity': current_equity})

            # 3. Calculate Signal for NEXT candle (based on Close)
            # We don't trade on the same candle we get the signal unless we use Open
            # Standard backtest: Signal at Close -> Open next candle. 
            # Simplified here: Enter at Close of signal candle.
            
            if self.position == 0:
                sig = self.strategy(row)
                if sig != 0:
                    self.position = sig
                    self.entry_price = row['close']
                    self.entry_time = timestamp

    def get_stats(self):
        df_trades = pd.DataFrame(self.trades)
        if df_trades.empty: return {'Error': 'No Trades'}
        
        wins = df_trades[df_trades['pnl'] > 0]
        losses = df_trades[df_trades['pnl'] <= 0]
        
        return {
            'Net Profit': round(self.equity - self.initial_equity, 2),
            'Return %': round((self.equity - self.initial_equity) / self.initial_equity * 100, 2),
            'Total Trades': len(df_trades),
            'Win Rate': f"{round(len(wins)/len(df_trades)*100, 1)}%",
            'Avg Win': round(wins['pnl'].mean(), 2) if not wins.empty else 0,
            'Avg Loss': round(losses['pnl'].mean(), 2) if not losses.empty else 0,
            'Max Drawdown': 'N/A (To Implement)'
        }
