import ccxt
import pandas as pd
import numpy as np

def get_gateio_kline(coin_name, interval="1h", limit=100):
    exchange = ccxt.gate()
    symbol = f"{coin_name}/USDT"
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching kline: {e}")
        return None

def auto_calculate_params(coin_name, taker_fee_rate=0.0005):
    """
    1. Volatility (Sigma): 1h Timeframe
    2. Trend (Alpha) & Bounds: 1m Timeframe (High/Low of previous candle)
    """
    try:
        # 1. Fetch 1H Data for Volatility
        df_1h = get_gateio_kline(coin_name, interval="1h", limit=336)
        if df_1h is None or df_1h.empty:
            return 0.01, 0.01, 0.0, 0.0, 0, 0
            
        returns = np.log(df_1h['close'] / df_1h['close'].shift(1))
        sigma_1h = returns.std()
        
        # 2. Fetch 1M Data for Trend & Bounds (Tighter)
        df_1m = get_gateio_kline(coin_name, interval="1m", limit=60)
        if df_1m is None or df_1m.empty:
             last_price = df_1h['close'].iloc[-1]
             return sigma_1h, 0.01, 0.0, 0.0, last_price*1.01, last_price*0.99

        # Trend Alpha (1M)
        short_window = 6
        if len(df_1m) > short_window:
            alpha_1m = (df_1m['close'].iloc[-1] - df_1m['close'].iloc[-short_window]) / short_window
        else:
            alpha_1m = 0
            
        # Target Bounds (Previous 1m Candle)
        prev_candle = df_1m.iloc[-2]
        high_1m = prev_candle['high']
        low_1m = prev_candle['low']
        
        eta = max(sigma_1h, 0.001)
        funding_rate = 0.0001
        
        return sigma_1h, eta, alpha_1m, funding_rate, high_1m, low_1m

    except Exception as e:
        print(f"Param Calc Error: {e}")
        return 0.01, 0.01, 0.0, 0.0, 0, 0
