import ccxt
import pandas as pd
import numpy as np
import os
import matplotlib
matplotlib.use('Agg') # Force non-interactive backend for server
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

class BacktestEngine:
    def __init__(self, symbol='BTC/USDT', timeframe='1h', initial_equity=10000):
        self.symbol = symbol
        self.timeframe = timeframe
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.df = pd.DataFrame()
        self.trades = []
        self.equity_curve = []
        
        # Risk Settings
        self.sl_pct = 0.02
        self.tp_pct = 0.04
        self.position = 0
        self.entry_price = 0.0
        self.entry_time = None

    def fetch_data(self, days=30):
        print(f"--> Fetching {days} days of data for {self.symbol}...")
        since = self.exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
        all_candles = []
        
        while since < self.exchange.milliseconds():
            try:
                candles = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, since=since, limit=1000)
                if not candles: break
                since = candles[-1][0] + 1
                all_candles.extend(candles)
            except Exception as e:
                print(f"[!] Fetch Error: {e}")
                break
            
        if not all_candles:
            raise ValueError("No data fetched from Exchange. Check internet or API restrictions.")

        new_df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        new_df['timestamp'] = pd.to_datetime(new_df['timestamp'], unit='ms')
        new_df.set_index('timestamp', inplace=True)
        # Drop duplicates and sort
        new_df = new_df[~new_df.index.duplicated(keep='first')].sort_index()
        
        path = f"{DATA_DIR}/{self.symbol.replace('/','')}_{self.timeframe}.csv"
        new_df.to_csv(path)
        self.df = new_df
        print(f"--> Data loaded: {len(self.df)} candles from {self.df.index[0]} to {self.df.index[-1]}")
        return self.df

    def load_data(self):
        path = f"{DATA_DIR}/{self.symbol.replace('/','')}_{self.timeframe}.csv"
        if os.path.exists(path):
            self.df = pd.read_csv(path, index_col='timestamp', parse_dates=True)
            print(f"--> Loaded cached data: {len(self.df)} rows.")
        else:
            self.fetch_data()

    def strategy(self, row):
        return 0

    def check_exit(self, row):
        if self.position == 0: return False, 0, 0
        
        # Long Logic
        if self.position == 1:
            sl = self.entry_price * (1 - self.sl_pct)
            tp = self.entry_price * (1 + self.tp_pct)
            if row['low'] <= sl: return True, sl, -self.sl_pct
            if row['high'] >= tp: return True, tp, self.tp_pct
                
        # Short Logic
        elif self.position == -1:
            sl = self.entry_price * (1 + self.sl_pct)
            tp = self.entry_price * (1 - self.tp_pct)
            if row['high'] >= sl: return True, sl, -self.sl_pct
            if row['low'] <= tp: return True, tp, self.tp_pct

        return False, 0, 0

    def run(self):
        if self.df.empty: self.load_data()
        
        self.trades = []
        self.equity = self.initial_equity
        self.equity_curve = [{'time': self.df.index[0], 'equity': self.equity}]
        self.position = 0

        print("--> Running Backtest...")
        for i in range(len(self.df)):
            row = self.df.iloc[i]
            ts = self.df.index[i]

            # Check Exit
            if self.position != 0:
                is_exit, price, pnl_pct = self.check_exit(row)
                if is_exit:
                    pnl_amt = self.equity * pnl_pct
                    self.equity += pnl_amt
                    self.trades.append({
                        'entry_time': self.entry_time,
                        'exit_time': ts,
                        'type': 'Long' if self.position == 1 else 'Short',
                        'price_in': self.entry_price,
                        'price_out': price,
                        'pnl': pnl_amt,
                        'pnl_pct': pnl_pct * 100
                    })
                    self.position = 0

            # Record Equity
            current_eq = self.equity
            if self.position != 0:
                move = (row['close'] - self.entry_price) / self.entry_price
                if self.position == -1: move *= -1
                current_eq = self.equity * (1 + move)
            
            self.equity_curve.append({'time': ts, 'equity': current_eq})

            # Check Entry
            if self.position == 0:
                sig = self.strategy(row)
                if sig != 0:
                    self.position = sig
                    self.entry_price = row['close']
                    self.entry_time = ts
    
    def report_trades(self):
        print("\n=== TRADE LOG ===")
        if not self.trades:
            print("No trades executed.")
            return

        print(f"{'TYPE':<6} | {'ENTRY TIME':<20} | {'EXIT TIME':<20} | {'PRICE IN':<10} | {'PRICE OUT':<10} | {'PNL':<10}")
        print("-" * 90)
        for t in self.trades:
            print(f"{t['type']:<6} | {str(t['entry_time']):<20} | {str(t['exit_time']):<20} | {t['price_in']:<10.2f} | {t['price_out']:<10.2f} | {t['pnl']:<10.2f}")
        print("-" * 90)
        stats = self.get_stats()
        print(f"Total Trades: {stats['Total Trades']} | Net Profit: {stats['Net Profit']} | Win Rate: {stats['Win Rate']}\n")

    def get_stats(self):
        if not self.trades: return {'Net Profit': 0, 'Win Rate': '0%', 'Total Trades': 0}
        df = pd.DataFrame(self.trades)
        wins = df[df['pnl'] > 0]
        return {
            'Net Profit': round(self.equity - self.initial_equity, 2),
            'Total Trades': len(df),
            'Win Rate': f"{round(len(wins)/len(df)*100, 1)}%"
        }

    def plot_matplotlib(self, filename='static/chart.png'):
        print("--> Generating Matplotlib Chart...")
        
        # Setup Data
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df.set_index('time', inplace=True)
        
        # Create Figure
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        
        # Plot 1: Price
        ax1.plot(self.df.index, self.df['close'], label='Price', color='black', alpha=0.6, linewidth=1)
        if 'sma_fast' in self.df.columns:
            ax1.plot(self.df.index, self.df['sma_fast'], label='Fast MA', color='blue', alpha=0.7)
        if 'sma_slow' in self.df.columns:
            ax1.plot(self.df.index, self.df['sma_slow'], label='Slow MA', color='orange', alpha=0.7)
        
        # Plot Entries/Exits on Price
        long_entries = [t['entry_time'] for t in self.trades if t['type'] == 'Long']
        long_entry_prices = [t['price_in'] for t in self.trades if t['type'] == 'Long']
        ax1.scatter(long_entries, long_entry_prices, marker='^', color='green', s=100, label='Buy', zorder=5)

        short_entries = [t['entry_time'] for t in self.trades if t['type'] == 'Short']
        short_entry_prices = [t['price_in'] for t in self.trades if t['type'] == 'Short']
        ax1.scatter(short_entries, short_entry_prices, marker='v', color='red', s=100, label='Sell', zorder=5)

        ax1.set_title(f"{self.symbol} Strategy Performance")
        ax1.set_ylabel("Price")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Plot 2: Equity
        ax2.plot(equity_df.index, equity_df['equity'], color='green', linewidth=2)
        ax2.fill_between(equity_df.index, equity_df['equity'], self.initial_equity, alpha=0.1, color='green')
        ax2.set_ylabel("Equity ($)")
        ax2.grid(True, alpha=0.3)

        # Format Date
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()
        print(f"--> Chart saved to {filename}")
