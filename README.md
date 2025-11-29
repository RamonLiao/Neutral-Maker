### 1\. `requirements.txt`

這是運行機器人所需的 Python 依賴庫。

```text
ccxt>=4.0.0
websockets>=11.0
asyncio
```

-----

### 2\. `README.md`

這份文檔詳細說明了如何安裝、配置以及 Avellaneda 策略的參數意義。

````markdown
# Avellaneda-Stoikov Market Making Bot for Gate.io

這是一個基於 **Avellaneda-Stoikov 做市商模型 (Market Making)** 的高頻交易機器人，專為 **Gate.io 合約交易 (USDT-Margined)** 設計。

與傳統網格不同，此機器人會根據當前的**持倉庫存 (Inventory)** 和**市場波動率 (Volatility)** 動態調整買賣價格，目標是賺取買賣價差 (Spread) 的同時，將庫存風險降至最低。

## 📂 檔案結構

確保你的目錄中包含以下兩個核心檔案：
1. **`bot.py`**: 基礎網格類別與 Gate.io API/WebSocket 連接層。
2. **`avellaneda_bot.py`**: 包含 Avellaneda 策略邏輯的主程序 (入口)。

## 🚀 快速開始

### 1. 安裝環境
確保你的電腦已安裝 Python 3.8 或更高版本。

安裝依賴庫：
```bash
pip install -r requirements.txt
````

### 2\. 配置 API Key

打開 `avellaneda_bot.py`，找到以下部分並填入你的 Gate.io API 資訊：

```python
# avellaneda_bot.py

API_KEY = "你的_API_KEY" 
API_SECRET = "你的_API_SECRET"
COIN_NAME = "XRP"      # 交易幣種 (例如 XRP, BTC, ETH)
INITIAL_QUANTITY = 1   # 每次下單的合約張數
LEVERAGE = 20          # 槓桿倍數
```

> ⚠️ **注意**：請確保 API Key 權限已開啟 **合約交易 (Futures)** 的讀寫權限。

### 3\. 啟動機器人

在終端機 (Terminal) 執行以下命令：

```bash
python avellaneda_bot.py
```

-----

## ⚙️ 策略參數詳解 (Avellaneda Parameters)

在 `avellaneda_bot.py` 中，你可以調整以下參數來改變機器人的行為風格：

| 參數變數 | 建議值 | 說明 |
| :--- | :--- | :--- |
| **`AVE_GAMMA`** | `10.0` | **風險厭惡係數 (Risk Aversion)**。<br>數值越大，機器人越討厭持倉。當有庫存時，它會更激進地降價拋售或提價回補，以盡快回到 0 持倉。 |
| **`AVE_SIGMA`** | `0.005` | **波動率估計 (Volatility)**。<br>數值越大，計算出的買賣價差 (Spread) 會越寬，以保護利潤；數值過小可能導致價差過窄，容易成交但利潤薄。 |
| **`AVE_ETA`** | `100.0` | **交易成本與流動性係數**。<br>影響基礎價差的寬度。通常不需要頻繁調整。 |
| **`AVE_T_END`** | `1` | **時間週期 (小時)**。<br>模型用於計算的時間窗口，通常設為 1 (代表以1小時為基準計算風險衰減)。 |

## 📊 策略邏輯簡述

機器人不再參考固定的 `Grid Spacing`，而是計算兩個關鍵數值：

1.  **公允價格 (Reserve Price, $r$)**：

      * 這不是市場中間價，而是你的「心理價位」。
      * 如果你持有**多單**，$r$ 會低於市場價 (急著賣)。
      * 如果你持有**空單**，$r$ 會高於市場價 (急著買)。

2.  **最優價差 (Optimal Spread, $\delta$)**：

      * 根據波動率 ($\sigma$) 和風險係數 ($\gamma$) 計算出的買賣單距離。

**機器人行為：**

  * 它會不斷撤銷舊訂單。
  * 根據最新的 $r$ 和 $\delta$ 重新掛出 `Best Bid` ($r - \delta$) 和 `Best Ask` ($r + \delta$)。
  * 目標是保持 **Delta Neutral (中性持倉)**。

## ⚠️ 風險提示 (Disclaimer)

  * **高頻撤單**：此策略會頻繁撤單和掛單，請留意交易所的 API Rate Limit (頻率限制)。
  * **趨勢風險**：Avellaneda 模型適合震盪行情。在單邊暴漲或暴跌的趨勢中，做市商策略可能會面臨持續的逆勢持倉虧損。
  * **本軟件按「現狀」提供**，不保證獲利。使用者需自行承擔交易風險。建議先在模擬盤或使用極小資金進行測試。

## 📝 日誌 (Logging)

運行過程中會自動生成 `log/` 文件夾，你可以在 `avellaneda_bot.log` 中查看詳細的計算數據 (R值, Delta值, 持倉量等)。

```

### 下一步建議
1.  將這兩個檔案保存在與代碼相同的資料夾中。
2.  在終端機執行 `pip install -r requirements.txt` 安裝依賴。
3.  記得在 `avellaneda_bot.py` 中填入你的 API Key 才能開始運行。
```