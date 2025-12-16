import asyncio
import time
import math
import logging
import os
from .bot import GridTradingBot, logger 
from .avellaneda_utils import auto_calculate_params
from dotenv import load_dotenv
from .ucb_manager import UCBManager

load_dotenv()

AVE_GAMMA = 0.5       
AVE_T_END = 0.02      
Taker_Fee_Rate = 0.0005 

ORDER_LAYERS = 1          # Single Layer (Strict 4-Order Limit)
LAYER_SPREAD = 0.0005     # 0.05% (Outer Entry)
TP_SPREAD = 0.0002        # 0.02% (Inner TP - Priority Close)
STOP_LOSS_SPREAD = 0.002  # 0.2% (Dynamic Baseline)
MAX_ENTRY_SPREAD = 0.0005 # 0.05% Max

API_KEY = os.getenv("GATEIO_TESTNET_KEY")
API_SECRET = os.getenv("GATEIO_TESTNET_SECRET")
USE_TESTNET = False
if API_KEY: USE_TESTNET = True
if not API_KEY:
    API_KEY = os.getenv("API_KEY")
    API_SECRET = os.getenv("API_SECRET")

COIN_NAME = "XRP" 
GRID_SPACING = 0.0006 
TAKE_PROFIT_SPACING = 0.0004
INITIAL_QUANTITY = 1
LEVERAGE = 20

class AvellanedaGridBot(GridTradingBot):
    
    def __init__(self, api_key, api_secret, coin_name, grid_spacing, initial_quantity, leverage, 
                 take_profit_spacing=None, gamma=AVE_GAMMA, eta=0.0, sigma=0.0, T_end=AVE_T_END,
                 trend_alpha=0.0, funding_rate=0.0, taker_fee_rate=0.0005, testnet=False,
                 order_layers=ORDER_LAYERS, layer_spread=LAYER_SPREAD):
        
        super().__init__(api_key, api_secret, coin_name, grid_spacing, initial_quantity, leverage, take_profit_spacing, testnet=testnet)
        
        self.gamma = gamma          
        self.eta = eta              
        self.sigma = sigma          
        self.T_end = T_end          
        self.trend_alpha = trend_alpha      
        self.funding_rate = funding_rate    
        self.taker_fee_rate = taker_fee_rate 
        
        self.high_1m = 0.0
        self.low_1m = 0.0
        self.rsi_val = 50.0
        
        # [NEW] UCB Attributes
        self.ucb_manager = UCBManager()
        self.last_equity = 0.0
        
        self.order_layers = order_layers
        self.layer_spread = layer_spread
        self.tp_spread = TP_SPREAD # Is 0.0002 (Inner)
        self.sl_spread = STOP_LOSS_SPREAD
        self.dynamic_refresh_time = 10 # Default 10s Baseline
        self.inventory = 0          
        self.best_bid = 0           
        self.best_ask = 0           
        
        logger.info(f"Avellaneda Strategic Bot (FR+RSI+Trend+UCB). Layers={order_layers}, MaxSpread={MAX_ENTRY_SPREAD}")

    async def _get_total_equity(self):
        """Helper to estimate Total Equity (Balance + Unlimited PnL)"""
        try:
             current_price = self.latest_price
             if not current_price: return 0.0
             
             unrealized_long = 0
             if self.long_position > 0:
                 unrealized_long = (current_price - self.long_entry_price) * self.long_position
                 
             unrealized_short = 0
             if self.short_position > 0:
                 unrealized_short = (self.short_entry_price - current_price) * self.short_position
                 
             return self.balance.get("USDT", {}).get("balance", 0) + unrealized_long + unrealized_short
        except:
             return 0.0

    async def update_parameters_periodically(self, interval=300):
        # Initial wait to let bot start and equity settle
        await asyncio.sleep(10)
        self.last_equity = await self._get_total_equity()
        logger.info(f"[UCB] Initial Equity Baseline: {self.last_equity:.4f}")

        while True:
            try:
                await asyncio.sleep(interval)
                loop = asyncio.get_running_loop()
                
                # 1. Calculate Reward (Change in Equity)
                current_equity = await self._get_total_equity()
                reward = current_equity - self.last_equity
                
                # 2. Update UCB Manager
                self.ucb_manager.update(reward)
                
                # 3. Select New Gamma
                self.gamma = self.ucb_manager.select_arm()
                self.last_equity = current_equity
                
                logger.info(f"[UCB] Interval Result: Reward={reward:.4f} | New Gamma={self.gamma}")

                # 4. Standard Param Update
                new_sigma, new_eta, new_alpha, new_funding, new_rsi, new_h, new_l = await loop.run_in_executor(
                    None, auto_calculate_params, self.coin_name, self.taker_fee_rate
                )
                self.sigma = new_sigma
                self.eta = new_eta
                self.trend_alpha = new_alpha 
                self.funding_rate = new_funding
                self.rsi_val = new_rsi
                self.high_1m = new_h
                self.low_1m = new_l
                
                # 5. Dynamic Parameter Adjustment (New)
                self._calculate_dynamic_params()
                
                logger.info(f"Brain Update: Sigma={self.sigma:.4f}, RSI={self.rsi_val:.1f}, FR={self.funding_rate:.6f}")
                logger.info(f"Dynamic Params: SL={self.sl_spread:.2%}, Refresh={self.dynamic_refresh_time}s")
            except Exception as e:
                logger.error(f"Brain Update Fail: {e}")
                await asyncio.sleep(60) 

    def _calculate_dynamic_params(self):
        """Calculate Dynamic Stop Loss and Refresh Time based on Volatility (Sigma)"""
        # Dynamic Stop Loss
        # Formula: SL = Sigma * 0.5 (Clamped 0.2% - 1.0%)
        # Logic: High Vol -> Wider SL (avoid wicks). Low Vol -> Tight SL (scalp).
        target_sl = self.sigma * 0.5
        self.sl_spread = max(0.002, min(target_sl, 0.01))
        
        # Dynamic Refresh Time
        # Formula: High Vol (>1%) -> 10s. Low Vol -> 30s.
        # Logic: Save API limits when calm.
        if self.sigma > 0.01:
            self.dynamic_refresh_time = 10
        else:
            self.dynamic_refresh_time = 30

    def _calculate_avellaneda_prices(self, price):
        # 1. THE BRAIN: Calculates the "Map"
        self.inventory = self.long_position - self.short_position
        
        # --- STRATEGY 1: Funding Rate Bias (Hedge Logic) ---
        target_inventory_bias = 0
        
        # Reduced Bias (from 5 to 1) to allow Dual Holding
        if self.funding_rate > 0.00005: 
             target_inventory_bias = -1 * self.initial_quantity * 5 # Mild Short Bias
        elif self.funding_rate < -0.00005:
             target_inventory_bias = self.initial_quantity * 5 # Mild Long Bias
             
        effective_inventory = self.inventory - target_inventory_bias

        T = self.T_end
        inv_term = (effective_inventory * self.gamma * (self.sigma**2) * T)
        
        # --- STRATEGY 2: Leading Indicator (RSI) ---
        # RSI > 70 => Overbought (Bias Down)
        # RSI < 30 => Oversold (Bias Up)
        rsi_bias = 0
        if self.rsi_val > 70:
             rsi_bias = -1 * (price * 0.002) # Shift down 0.2%
        elif self.rsi_val < 30:
             rsi_bias = (price * 0.002) # Shift up 0.2%
             
        # Trend Alpha Impact (5m Trend)
        trend_impact = self.trend_alpha * 2.0 
        
        self.reserve_price = price + trend_impact + rsi_bias - inv_term

        try:
            term1 = 0.5 * self.gamma * (self.sigma**2) * T
            safe_eta = max(self.eta, 0.001) 
            term2 = (1 / self.gamma) * math.log(1 + self.gamma / safe_eta)
            delta_pct = term1 + term2 
            
            # 1M Tightening
            if self.high_1m > 0 and self.low_1m > 0 and self.high_1m > self.low_1m:
                 half_candle_range = (self.high_1m - self.low_1m) * 0.5
                 delta_price = min(delta_pct * price, half_candle_range)
            else:
                 delta_price = delta_pct * price

            # SAFETY CLAMP (0.02% Limit)
            max_allowed_delta = price * MAX_ENTRY_SPREAD
            delta_price = min(delta_price, max_allowed_delta)

            min_delta = price * 0.0001
            delta = max(delta_price, min_delta)
            
        except:
            delta = self.grid_spacing * price * 0.5 
            
        self.best_bid = max(0.001, self.reserve_price - delta) # Ensure non-zero
        self.best_ask = max(0.001, self.reserve_price + delta) # Ensure non-zero
        
    def update_mid_price(self, side, price):
        self._calculate_avellaneda_prices(price)

    async def _long_mindset_logic(self, latest_price):
        """Long Mindset"""
        if self.long_position > 0:
            # Use Dynamic SL Spread
            sl_price = self.long_entry_price * (1 - self.sl_spread)
            if latest_price < sl_price:
                logger.warning(f"[LONG] STOP LOSS: {latest_price} < {sl_price} (SL={self.sl_spread:.2%})")
                await self.place_order('sell', latest_price*0.99, self.long_position, True, 'long')
                return 

        await self.cancel_orders_for_side('long', for_tp=False)
        
        # 1. Maker Guard (0.01% - Covers Fees)
        min_dist = latest_price * 0.0001
        safe_bid = min(self.best_bid, latest_price - min_dist)
        
        # 2. Tunnel Clamp (Ensure Bid is not too low)
        min_allowed_bid = latest_price * (1 - MAX_ENTRY_SPREAD)
        safe_bid = max(safe_bid, min_allowed_bid)
        
        base_bid = safe_bid
        for i in range(self.order_layers):
            p = base_bid * (1 - i * self.layer_spread)
            if p <= 0: continue 
            await self.place_order('buy', p, self.long_initial_quantity, False, 'long')

        await self.cancel_orders_for_side('long', for_tp=True)
        if self.long_position > 0:
            target_tp = self.long_entry_price * (1 + self.tp_spread)
            maker_tp = max(target_tp, latest_price * 1.0005)
            await self.place_order('sell', maker_tp, self.long_position, True, 'long')

    async def _short_mindset_logic(self, latest_price):
        """Short Mindset"""
        if self.short_position > 0:
            # Use Dynamic SL Spread
            sl_price = self.short_entry_price * (1 + self.sl_spread)
            if latest_price > sl_price:
                logger.warning(f"[SHORT] STOP LOSS: {latest_price} > {sl_price} (SL={self.sl_spread:.2%})")
                await self.place_order('buy', latest_price*1.01, self.short_position, True, 'short')
                return 

        await self.cancel_orders_for_side('short', for_tp=False)
        
        # 1. Maker Guard (0.01% - Covers Fees)
        min_dist = latest_price * 0.0001
        safe_ask = max(self.best_ask, latest_price + min_dist)
        
        # 2. Tunnel Clamp (Ensure Ask is not too high)
        max_allowed_ask = latest_price * (1 + MAX_ENTRY_SPREAD)
        safe_ask = min(safe_ask, max_allowed_ask)
        
        base_ask = safe_ask
        for i in range(self.order_layers):
            p = base_ask * (1 + i * self.layer_spread)
            if p <= 0: continue
            await self.place_order('sell', p, self.short_initial_quantity, False, 'short')

        await self.cancel_orders_for_side('short', for_tp=True)
        if self.short_position > 0:
            target_tp = self.short_entry_price * (1 - self.tp_spread)
            maker_tp = min(target_tp, latest_price * 0.9995)
            await self.place_order('buy', maker_tp, self.short_position, True, 'short')
    
    async def manage_grid_orders(self, latest_price):
        try:
            self.update_mid_price(None, latest_price)
            # Parallel Execution
            await asyncio.gather(
                self._long_mindset_logic(latest_price),
                self._short_mindset_logic(latest_price)
            )
        except Exception as e:
            logger.error(f"Dual-Mindset Error: {e}")

    async def adjust_grid_strategy(self):
        if not self.latest_price: return
        # Check Dynamic Refresh Throttle
        if time.time() - self.last_long_order_time > self.dynamic_refresh_time: 
            await self.manage_grid_orders(self.latest_price)
            self.last_long_order_time = time.time()

    async def run(self):
        logger.info("--- BOT STARTUP: Cleaning Stale Orders ---")
        try:
            # Try efficient single call
            await self.exchange.cancel_all_orders(self.ccxt_symbol)
            logger.info("All open orders cancelled.")
        except Exception as e:
            logger.warning(f"cancel_all_orders failed ({e}), switching to manual Loop...")
            try:
                orders = await self.exchange.fetch_open_orders(self.ccxt_symbol)
                for o in orders:
                    await self.exchange.cancel_order(o['id'], self.ccxt_symbol)
                logger.info(f"Manually cancelled {len(orders)} stale orders.")
            except Exception as e2:
                logger.error(f"Failed to clear orders: {e2}")
        
        asyncio.create_task(self.update_parameters_periodically())
        await super().run()

async def main():
    global AVE_SIGMA, AVE_ETA, TREND_ALPHA, FUNDING_RATE, RSI, H1, L1
    try:
        AVE_SIGMA, AVE_ETA, TREND_ALPHA, FUNDING_RATE, RSI, H1, L1 = auto_calculate_params(COIN_NAME, Taker_Fee_Rate)
    except:
        AVE_SIGMA, AVE_ETA, TREND_ALPHA, FUNDING_RATE, RSI, H1, L1 = 0.01, 0.01, 0.0, 0.0, 50.0, 0, 0

    bot = AvellanedaGridBot(
        API_KEY, API_SECRET, COIN_NAME,
        GRID_SPACING, INITIAL_QUANTITY, LEVERAGE,
        TAKE_PROFIT_SPACING,
        gamma=AVE_GAMMA, eta=AVE_ETA, sigma=AVE_SIGMA, T_end=AVE_T_END,
        trend_alpha=TREND_ALPHA, funding_rate=FUNDING_RATE, taker_fee_rate=Taker_Fee_Rate,
        testnet=USE_TESTNET,
        order_layers=ORDER_LAYERS, layer_spread=LAYER_SPREAD
    )
    bot.high_1m = H1
    bot.low_1m = L1
    bot.rsi_val = RSI
    
    await bot.run()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    except Exception as e: logger.critical(f"FATAL: {e}")
