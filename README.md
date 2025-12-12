# Avellaneda-Stoikov Market Making Bot (Enhanced)

這是一個增強版的 **Avellaneda-Stoikov 做市商機器人**，專為 **Gate.io 永續合約 (Perpetual Futures)** 設計。它結合了動態參數調整、趨勢跟隨、資金費率套利以及 UCB 參數優化策略。

> **最新更新**: 支援 **1-Minute High Frequency Scalping (極速超短線)** 模式，與多層網格掛單。

---

## 🌟 核心功能 (Key Features)

1.  **1m 極速超短線 (HF Scalping)**:
    *   **1分鐘 K線**: 使用 1m K線數據進行更高頻的波動率計算。
    *   **微秒級反應**: `AVG_T_END` 設為 0.02 (約 1.2 分鐘)，對庫存極度敏感。
    *   **極致價差**: 默認 0.01% (`0.0001`) 價差，捕捉極微小的市場波動。

2.  **多層掛單 (Multi-Layer Grid)**:
    *   不再只掛單一買/賣單。
    *   **5層防護**: 機器人會在最優價後方連續掛出 5 層補倉單，利用「網格效應」在價格來回震盪時吸籌與出貨。

3.  **動態 Avellaneda 模型**:
    *   自動計算市場波動率 ($\sigma$, Sigma) 和流動性參數 ($\eta$, Eta)。
    *   根據動態市場狀況調整最佳買賣價差 (Spread)。

4.  **趨勢感知 & 資金費率對沖**:
    *   利用 EMA 判斷趨勢，利用 Funding Rate 進行套利對沖。

---

## 📂 檔案結構

*   **`avellaneda_bot.py`**: **核心主程序 (建議直接運行此檔案)**。
*   **`bot.py`**: 底層 Gate.io 接口。
*   **`avellaneda_utils.py`**: 工具庫 (1m K線, 波動率計算)。
*   **`strategy_manager.py`**: 高階管理器 (選幣與自動優化)。
*   **`.env`**: API Key 配置。

---

## 🚀 新手入門教程 (Step-by-Step)

### 1. 安裝環境
確保安裝了 Python 3.8+，然後安裝依賴：
```bash
pip install -r requirements.txt
```

### 2. 配置測試網 API (強烈推薦)
在專案目錄建立 `.env` 檔案：
```env
GATEIO_TESTNET_KEY=你的測試網API_KEY
GATEIO_TESTNET_SECRET=你的測試網API_SECRET
```
*機器人檢測到這個 Key 會自動開啟測試模式。*

### 3. 啟動機器人 (超短線模式)
直接運行：
```bash
python avellaneda_bot.py
```

**你將會看到：**
*   `Multi-Layer Mode`: 顯示 5 層掛單，Spread 0.01%。
*   `AVE_SIGMA`: 基於 1m K線計算的實時波動率。
*   機器人會在當前價格上下密集掛單 (每 0.01% 一檔)，並在成交後迅速掛出止盈。

---

## ⚙️ 參數詳解 (進階調整)

在 `avellaneda_bot.py` 開頭可以調整：

| 參數 | 當前設定 (HF) | 說明 |
| :--- | :--- | :--- |
| **`ORDER_LAYERS`** | `5` | **掛單層數**。設定 5 表示會在買/賣方向各掛 5 張單。 |
| **`LAYER_SPREAD`** | `0.0001` (0.01%) | **每層間距**。越小越適合手術刀式超短線，越大適合震盪大行情。 |
| **`AVE_T_END`** | `0.02` | **時間視野**。0.02 表示機器人只在乎未來 1 分鐘的風險，會極快地平倉。 |
| **`AVE_GAMMA`** | `0.5` | **風險厭惡**。降低到 0.5 讓機器人報價更貼近市價 (更易成交)。 |

## ⚠️ 風險提示

*   **API 頻率**: 1m 模式下交易頻率極高，請留意 Gate.io API Rate Limit。
*   **手續費**: 極窄價差 (0.01%) 需要你的手續費率極低 (或有 Rebate)，否則可能被手續費吃光利潤。
