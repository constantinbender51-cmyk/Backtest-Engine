from engine import BacktestEngine

class MeanReversionStrategy(BacktestEngine):
    def __init__(self):
        super().__init__(symbol='ETH/USDT', timeframe='1h')
        self.sl_pct = 0.02
        self.tp_pct = 0.06
        
        # Strategy specific variables
        self.window = 20

    def strategy(self, row):
        """
        Input: row (pandas Series with open, high, low, close, volume)
        Output: 1 (Buy), -1 (Sell), 0 (Hold)
        """
        # We need historical context, so we look at self.df up to this timestamp
        # Note: In a loop, this is slow. For production, pre-calculate indicators in 'run'
        
        # Simplified "Vectorized" approach:
        # We pre-calculate indicators once in run() for speed, then access them here.
        # But for this specific simplistic request, we access the row's pre-calc columns.
        
        if row['rsi'] < 30:
            return 1 # Long
        elif row['rsi'] > 70:
            return -1 # Short
        return 0

    def prepare_indicators(self):
        """Helper to add indicators before loop."""
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df['rsi'] = 100 - (100 / (1 + rs))

    def run(self):
        self.load_data()
        self.prepare_indicators() # Pre-calc logic
        super().run() # Run the loop
