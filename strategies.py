from engine import BacktestEngine
import pandas as pd

class Strategy(BacktestEngine):
    def __init__(self):
        # We hardcode the settings for the one strategy we want to run
        super().__init__(symbol='BTC/USDT', timeframe='4h')
        self.sl_pct = 0.05
        self.tp_pct = 0.15
        self.fast_window = 50
        self.slow_window = 200

    def prepare_indicators(self):
        self.df['sma_fast'] = self.df['close'].rolling(window=self.fast_window).mean()
        self.df['sma_slow'] = self.df['close'].rolling(window=self.slow_window).mean()

    def strategy(self, row):
        if pd.isna(row['sma_slow']): return 0
        if row['sma_fast'] > row['sma_slow']: return 1
        elif row['sma_fast'] < row['sma_slow']: return -1
        return 0

    def check_exit(self, row):
        # 1. Standard TP/SL
        is_exit, price, pnl = super().check_exit(row)
        if is_exit: return True, price, pnl
        
        # 2. Trend Reversal Exit (SMA Cross back)
        if self.position == 1 and row['sma_fast'] < row['sma_slow']:
            return True, row['close'], (row['close'] - self.entry_price) / self.entry_price
            
        if self.position == -1 and row['sma_fast'] > row['sma_slow']:
            return True, row['close'], (self.entry_price - row['close']) / self.entry_price
            
        return False, 0, 0

    def run(self):
        # Self-managed data fetching
        self.fetch_data(days=365)
        self.prepare_indicators()
        super().run()
