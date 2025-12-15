import ccxt
import pandas as pd
import numpy as np
import time

def get_gateio_kline(coin_name, interval="1h", limit=100):
    exchange = ccxt.gate({'enableRateLimit': True, 'timeout': 5000}) # 5s timeout
    symbol = f"{coin_name}/USDT"
    
    for attempt in range(3):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Error fetching kline {interval} (Attempt {attempt+1}/3): {e}")
            time.sleep(2)
    return None

def get_funding_rate(coin_name):
    exchange = ccxt.gate({'enableRateLimit': True, 'timeout': 5000}) # 5s timeout
    symbol = f"{coin_name}/USDT"
    try:
        # Gate.io futures funding rate
        ticker = exchange.fetch_ticker(symbol)
        # Usually 'info' contains raw exchange data, typically 'funding_rate' field
        # CCXT unifies this in 'last' sometimes, but specifically for funding we might need fetch_funding_rate if supported
        # Retrying with fetch_funding_rate which is standard for Perps
        try:
            funding_info = exchange.fetch_funding_rate(symbol)
            return float(funding_info['fundingRate'])
        except:
             # Fallback to 0.0001 (0.01%) if fetch fails
             return 0.0001
    except Exception as e:
        print(f"Error fetching Funding Rate: {e}")
        return 0.0001

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    # Fill NaN with 50 (Neutral)
    return rsi.fillna(50)

def auto_calculate_params(coin_name, taker_fee_rate=0.0005):
    """
    Multi-Timeframe Strategy Param Calculation:
    1. Volatility (Sigma): 1h Timeframe
    2. Trend (Alpha) + RSI: 5m Timeframe (Leading Indicator)
    3. Bounds (High/Low): 1m Timeframe
    4. Funding Rate: Real-time
    """
    try:
        # 1. Macro Volatility (1H)
        df_1h = get_gateio_kline(coin_name, interval="1h", limit=336)
        if df_1h is None or df_1h.empty:
            return 0.01, 0.01, 0.0, 0.0, 50, 0, 0
            
        returns = np.log(df_1h['close'] / df_1h['close'].shift(1))
        sigma_1h = returns.std()
        
        # 2. Key Trend & RSI (5M)
        df_5m = get_gateio_kline(coin_name, interval="5m", limit=60)
        rsi_val = 50.0
        alpha_5m = 0.0
        
        if df_5m is not None and not df_5m.empty:
             # Alpha (Slope)
             short_window = 6
             if len(df_5m) > short_window:
                 alpha_5m = (df_5m['close'].iloc[-1] - df_5m['close'].iloc[-short_window]) / short_window
             
             # RSI
             rsi_series = calculate_rsi(df_5m['close'], 14)
             rsi_val = rsi_series.iloc[-1]

        # 3. Micro Bounds (1M)
        df_1m = get_gateio_kline(coin_name, interval="1m", limit=60)
        high_1m = 0
        low_1m = 0
        
        if df_1m is not None and not df_1m.empty:
            prev_candle = df_1m.iloc[-2]
            high_1m = prev_candle['high']
            low_1m = prev_candle['low']
        
        # 4. Funding Rate
        funding_rate = get_funding_rate(coin_name)
        
        eta = max(sigma_1h, 0.001)
        
        return sigma_1h, eta, alpha_5m, funding_rate, rsi_val, high_1m, low_1m

    except Exception as e:
        print(f"Param Calc Error: {e}")
        # Default safety values
        return 0.01, 0.01, 0.0, 0.0001, 50.0, 0, 0
