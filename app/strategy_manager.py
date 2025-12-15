
import asyncio
import time
import random
import logging
import math
import pandas as pd
import requests
import os
from avellaneda_bot import AvellanedaGridBot
from avellaneda_utils import get_gateio_kline
from dotenv import load_dotenv

load_dotenv()

# ==================== 策略配置 ====================
EPOCH_DURATION = 3600  # 每個週期的持續時間 (秒) - 例如 1 小時
UCB_C = 2.0            # UCB 探索參數
COIN_POOL = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX"] # 候選幣種池

# 設定 Logger
logger = logging.getLogger("StrategyManager")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ==================== 檢測 Testnet ====================
GATEIO_TESTNET_KEY = os.getenv("GATEIO_TESTNET_KEY")
GATEIO_TESTNET_SECRET = os.getenv("GATEIO_TESTNET_SECRET")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

USE_TESTNET = False
if GATEIO_TESTNET_KEY and GATEIO_TESTNET_SECRET:
    API_KEY = GATEIO_TESTNET_KEY
    API_SECRET = GATEIO_TESTNET_SECRET
    USE_TESTNET = True
    logger.info(">>> DETECTED TESTNET KEYS - RUNNING IN SANDBOX MODE <<<")
else:
    logger.info(">>> USING MAINNET KEYS <<<")

# ==================== 1. AI 選幣 (基於波動率與成交量) ====================
class CoinSelector:
    def __init__(self, coins):
        self.coins = coins

    def get_market_metrics(self):
        """
        獲取候選幣種的市場指標 (波動率, 成交量)
        這裡作為 'AI 排序' 的代理邏輯
        """
        metrics = []
        for coin in self.coins:
            pair = f"{coin}_USDT"
            try:
                # 獲取最近 24H 數據
                df = get_gateio_kline(pair, interval="1h", limit=24)
                if df.empty:
                    continue
                
                # 計算波動率 (標準差)
                df['log_ret'] = math.log(df['close'] / df['close'].shift(1))
                volatility = df['log_ret'].std()
                
                # 計算成交量 (簡單加總)
                volume = df['close'] * df['volume_base'] # 近似成交額
                total_volume = volume.sum()
                
                metrics.append({
                    "coin": coin,
                    "volatility": volatility,
                    "volume": total_volume
                })
            except Exception as e:
                logger.error(f"獲取 {coin} 數據失敗: {e}")
        
        return pd.DataFrame(metrics)

    def select_best_coin(self):
        """
        選擇最佳幣種
        策略: 選擇波動率最高 且 成交量足夠 的幣種 (適合網格/AS策略)
        """
        logger.info("正在進行選幣分析 (AI Sorting Proxy)...")
        metrics_df = self.get_market_metrics()
        
        if metrics_df.empty:
            logger.warning("無法獲取市場數據，隨機選擇默認幣種 XRP")
            return "XRP"
            
        # 簡單評分: 波動率 * 1000 + 成交量(對數)
        # 我們希望波動率大 (有價差賺)，流動性好 (成交量高)
        metrics_df['score'] = metrics_df['volatility'] * 10000 + dataframe_log_volume(metrics_df) 
        
        best_coin_row = metrics_df.sort_values('score', ascending=False).iloc[0]
        best_coin = best_coin_row['coin']
        
        logger.info(f"選幣結果: {best_coin} (Vol: {best_coin_row['volatility']:.4f})")
        return best_coin

def dataframe_log_volume(df):
    # 輔助函數: 處理 log volume 避免 0
    return df['volume'].apply(lambda x: math.log(x) if x > 0 else 0)


# ==================== 2. UCB 參數優化 ====================
class UCBOptimizer:
    def __init__(self):
        # 定義參數臂 (Arm): 不同 Gamma (風險厭惡) 和 Trend Window (趨勢窗口) 的組合
        self.arms = [
            {"id": 0, "gamma": 0.5, "window": 12}, # 激進: 低厭惡，短趨勢
            {"id": 1, "gamma": 1.0, "window": 24}, # 中性: 標準厭惡，日趨勢
            {"id": 2, "gamma": 2.0, "window": 48}, # 保守: 高厭惡，長趨勢
            {"id": 3, "gamma": 0.8, "window": 6},  # 短線頻繁
        ]
        self.counts = {arm["id"]: 0 for arm in self.arms}
        self.values = {arm["id"]: 0.0 for arm in self.arms} # 平均獎勵 (PnL)
        self.total_counts = 0

    def select_arm(self):
        """選擇下一個週期的參數組合"""
        for arm in self.arms:
            if self.counts[arm["id"]] == 0:
                return arm
        
        # UCB1 算法
        best_arm = None
        max_ucb = -float('inf')
        
        for arm in self.arms:
            arm_id = arm["id"]
            average_reward = self.values[arm_id]
            confidence = UCB_C * math.sqrt(math.log(self.total_counts) / self.counts[arm_id])
            ucb_score = average_reward + confidence
            
            if ucb_score > max_ucb:
                max_ucb = ucb_score
                best_arm = arm
                
        logger.info(f"UCB 選擇參數: {best_arm}")
        return best_arm

    def update(self, arm_id, reward):
        """更新 UCB 統計數據"""
        self.counts[arm_id] += 1
        n = self.counts[arm_id]
        value = self.values[arm_id]
        # 更新平均值
        new_value = ((n - 1) / n) * value + (1 / n) * reward
        self.values[arm_id] = new_value
        self.total_counts += 1
        
        logger.info(f"UCB 更新: Arm {arm_id}, Reward {reward:.2f}, New Avg {new_value:.2f}")


# ==================== 3. 策略管理器 (主循環) ====================
class StrategyManager:
    def __init__(self):
        self.coin_selector = CoinSelector(COIN_POOL)
        self.optimizer = UCBOptimizer()
        
    async def fetch_total_usdt_balance(self, exchange):
        """獲取帳戶總權益 (USDT)"""
        try:
            # 必須在線程池中運行，因為 ccxt 通常是同步的 (除非配置了 async)
            # bot.py 使用了 ccxt.gate，這是同步版本
            loop = asyncio.get_running_loop()
            balance = await loop.run_in_executor(None, exchange.fetch_balance, {'type': 'future', 'settle': 'usdt'})
            # Gate.io futures balance structure
            if 'USDT' in balance:
                return float(balance['USDT']['total'])
            else:
                return 0.0
        except Exception as e:
            logger.error(f"獲取餘額失敗: {e}")
            return 0.0

    async def run_bot_epoch(self, coin, params_arm):
        """
        運行一個 Epoch 的機器人
        """
        gamma = params_arm["gamma"]
        logger.info(f"啟動機器人 Epoch: Coin={coin}, Gamma={gamma}")
        
        bot = AvellanedaGridBot(
            API_KEY, API_SECRET, coin,
            grid_spacing=0.001, initial_quantity=1, leverage=10, 
            gamma=gamma,
            testnet=USE_TESTNET
        )
        
        # 1. 記錄初始權益
        balance_start = await self.fetch_total_usdt_balance(bot.exchange)
        logger.info(f"Epoch 開始餘額: {balance_start}")

        # 2. 啟動機器人
        bot_task = asyncio.create_task(bot.run())
        
        try:
            await asyncio.sleep(EPOCH_DURATION)
        except asyncio.CancelledError:
            pass
        finally:
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                logger.info("機器人 Epoch 結束 (已停止)")
                
        # 3. 計算 PnL
        balance_end = await self.fetch_total_usdt_balance(bot.exchange)
        pnl = balance_end - balance_start
        
        logger.info(f"Epoch 結束 PnL: {pnl:.4f} (End Balance: {balance_end})")
        return pnl

    async def main_loop(self):
        logger.info("=== 策略管理器啟動 ===")
        while True:
            # 1. 選幣
            coin = self.coin_selector.select_best_coin()
            
            # 2. 優化參數 (UCB)
            arm = self.optimizer.select_arm()
            
            # 3. 運行 Epoch
            reward = await self.run_bot_epoch(coin, arm)
            
            # 4. 更新優化器
            self.optimizer.update(arm["id"], reward)
            
            # 休息一下再開始下一輪
            await asyncio.sleep(10)

if __name__ == "__main__":
    manager = StrategyManager()
    try:
        asyncio.run(manager.main_loop())
    except KeyboardInterrupt:
        pass
