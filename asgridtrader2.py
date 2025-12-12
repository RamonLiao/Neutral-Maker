import numpy as np
import pandas as pd

class ASGridTrader:
    """
    Avellaneda-Stoikov 網格交易器 for 合約（Perpetual Futures）。
    整合趨勢跟隨、庫存對沖、UCB優化和領先指標。
    """
    
    def __init__(self, initial_capital=10000, gamma=0.1, k=1.5, eta=0.001, 
                 inventory_target=0, hedge_threshold=0.2, ucb_arms=[0.05, 0.1, 0.15], fee_rate=0.001):
        """
        初始化交易器。
        - initial_capital: 初始保證金 (A)。
        - gamma: AS模型風險厭惡參數 (風險越高，報價越保守)。
        - k: AS模型訂單流強度參數。
        - eta: 市場強度參數 (訂單簿深度)。
        - inventory_target: 目標庫存 (中性為0)。
        - hedge_threshold: 對沖閾值 (e.g., 0.2 表示庫存偏離20%時觸發)。
        - ucb_arms: UCB優化候選間距比率 (用於動態優化grid_spacing)。
        - fee_rate: 手續費率 (e.g., 0.001 for 0.1%)。
        """
        self.capital = initial_capital
        self.gamma = gamma
        self.k = k
        self.eta = eta
        self.inventory_target = inventory_target
        self.hedge_threshold = hedge_threshold
        self.fee_rate = fee_rate  # 新增手續費率
        self.ucb_arms = ucb_arms  # UCB臂：不同間距比率
        
        # UCB變數：追蹤每個臂的回報和次數
        self.ucb_rewards = np.zeros(len(ucb_arms))
        self.ucb_counts = np.zeros(len(ucb_arms))
        self.t = 0  # 總試驗次數
        
        # 交易狀態
        self.inventory = 0  # 當前庫存 (正: long, 負: short)
        self.position_size = 0.01  # 固定合約大小 (BTC單位)
        self.trades = []  # 交易記錄
        
        # 領先指標：簡單移動平均 (SMA) 用於趨勢預測
        self.prices_history = []  # 價格歷史 (用於計算SMA)
        self.sma_window = 20  # SMA窗口
    
    def calculate_as_quotes(self, mid_price, sigma, dt=1/252, inventory=0):
        """
        Avellaneda-Stoikov模型：計算最佳買賣報價。
        公式:
        - reservation_price = mid_price - gamma * sigma^2 * dt * (inventory - inventory_target)
        - bid = reservation_price - (1/2) * gamma * sigma^2 * dt
        - ask = reservation_price + (1/2) * gamma * sigma^2 * dt
        其中 sigma: 波動率, dt: 時間步長。
        返回: (bid_price, ask_price)
        """
        reservation = mid_price - self.gamma * (sigma ** 2) * dt * (inventory - self.inventory_target)
        half_spread = 0.5 * self.gamma * (sigma ** 2) * dt
        bid = reservation - half_spread
        ask = reservation + half_spread
        return max(0, bid), ask  # 防止負價
    
    def update_grid_spacing_ucb(self, recent_profit):
        """
        UCB參數優化：優化網格間距比率。
        UCB公式: arm = argmax( mean_reward[i] + sqrt( log(t) / counts[i] ) )
        - recent_profit: 上次交易利潤 (用於更新回報)。
        - 更新 self.optimal_spacing_ratio (用於動態間距)。
        """
        self.ucb_counts[self.arm_idx] += 1  # 更新當前臂次數
        self.ucb_rewards[self.arm_idx] += recent_profit  # 更新回報
        self.t += 1
        
        if self.t % 10 == 0:  # 每10步優化一次
            ucb_values = (self.ucb_rewards / self.ucb_counts) + np.sqrt(np.log(self.t) / (self.ucb_counts + 1e-5))
            self.arm_idx = np.argmax(ucb_values)  # 選擇最佳臂
        return self.ucb_arms[self.arm_idx]
    
    def get_leading_indicator(self, current_price):
        """
        領先指標：使用SMA預測趨勢。
        - 若 current_price > SMA: 牛市信號 (上移網格)。
        - 若 current_price < SMA: 熊市信號 (下移網格)。
        返回: trend_signal (1: 上漲, -1: 下跌, 0: 中性)
        """
        self.prices_history.append(current_price)
        if len(self.prices_history) > self.sma_window:
            sma = np.mean(self.prices_history[-self.sma_window:])
            if current_price > sma * 1.01:  # 1% 以上為牛
                return 1
            elif current_price < sma * 0.99:  # 1% 以下為熊
                return -1
        return 0
    
    def manage_inventory_hedge(self, current_price, funding_rate=0.0001):
        """
        庫存管理：多空對沖 + FR偏向 + GLFT控制。
        - 若 |inventory| > threshold: 開反向倉位對沖。
        - FR偏向: 若 funding_rate > 0, 偏好短對沖 (賺正費率)。
        - GLFT模擬: 假設流動性足夠 (簡單閾值控制)，實際可整合訂單簿深度。
        返回: hedge_action ('long', 'short', None)
        """
        inv_ratio = abs(self.inventory) / (self.capital * self.position_size)  # 庫存比率
        if inv_ratio > self.hedge_threshold:
            if self.inventory > 0:  # long過多，考慮短對沖
                if funding_rate > 0:  # FR正，偏好短
                    return 'short'
                else:
                    return 'long'  # FR負，偏好長 (支付費率少)
            elif self.inventory < 0:  # short過多，考慮長對沖
                if funding_rate < 0:  # FR負，偏好長
                    return 'long'
                else:
                    return 'short'
        return None
    
    def execute_trade(self, action, price, size):
        """
        執行單筆交易 (買/賣)。
        - action: 'buy' (long) or 'sell' (short)。
        - 更新 inventory, capital (模擬保證金變化), trades。
        - 加入手續費: 交易價值 * fee_rate，從capital扣除。
        """
        trade_value = size * price
        fee = trade_value * self.fee_rate  # 計算手續費
        
        if action == 'buy':
            self.inventory += size
            self.capital -= (trade_value * 0.01) + fee  # 保證金 + 手續費
        elif action == 'sell':
            self.inventory -= size
            self.capital += (trade_value * 0.01) - fee  # 釋放保證金 - 手續費 (假設釋放後扣費)
        self.trades.append({'action': action, 'price': price, 'size': size, 'fee': fee})
    
    def run_simulation(self, prices, sigma=0.02, funding_rate=0.0001):
        """
        運行模擬：生成AS網格交易信號。
        - prices: 價格序列 (np.array)。
        - sigma: 波動率 (用於AS報價)。
        - 每步: 計算報價 → 檢查穿越 (買一賣一) → 趨勢跟隨調整 → 庫存對沖 → UCB優化。
        返回: (final_capital, trades_df)
        """
        self.arm_idx = 0  # 初始UCB臂
        optimal_ratio = self.ucb_arms[0]
        mid_price = prices[0]
        
        for t, price in enumerate(prices[1:], 1):
            # 領先指標：趨勢跟隨
            trend = self.get_leading_indicator(price)
            if trend != 0:
                mid_price += trend * optimal_ratio * mid_price  # 上/下移中價 (跟隨趨勢)
            
            # AS報價 (買一賣一)
            bid, ask = self.calculate_as_quotes(mid_price, sigma, inventory=self.inventory)
            
            # 簡單網格邏輯：若穿越bid買, 穿越ask賣 (間距基於optimal_ratio)
            profit = 0
            if price <= bid:  # 買入信號
                self.execute_trade('buy', price, self.position_size)
            elif price >= ask:  # 賣出信號
                self.execute_trade('sell', price, self.position_size)
                profit = (ask - bid) * self.position_size  # 簡單價差利潤
            # UCB優化間距 (基於利潤)
            optimal_ratio = self.update_grid_spacing_ucb(profit)
            
            # 庫存對沖
            hedge = self.manage_inventory_hedge(price, funding_rate)
            if hedge:
                self.execute_trade(hedge, price, self.position_size * 0.5)  # 半倉對沖
        
        # 最終資本：capital + 庫存價值 (簡化，忽略未實現PnL)
        final_capital = self.capital + self.inventory * prices[-1] * 0.01
        trades_df = pd.DataFrame(self.trades)
        return final_capital, trades_df

# 範例運行
if __name__ == "__main__":
    # 生成隨機價格路徑 (模擬BTC)
    np.random.seed(42)
    prices = [50000]
    for _ in range(1000):
        change = np.random.normal(0, 0.02 * prices[-1])
        prices.append(prices[-1] + change)
    prices = np.array(prices)
    
    # 初始化並運行
    trader = ASGridTrader()
    final_capital, trades_df = trader.run_simulation(prices)
    
    print(f"初始資本: 10000")
    print(f"最終資本: {final_capital:.2f}")
    print(f"交易記錄:\n{trades_df.head()}")
