# Avellaneda-Stoikov Strategic Hedge Bot (AS-Hedge)

這是一個高度進階的 **Avellaneda-Stoikov 對沖做市機器人**，專為 **Gate.io 永續合約** 設計。
它採用獨特的「**雙重思維 (Dual Mindset)**」架構，在單一幣種上同時運行多空策略，利用資金費率 (Funding Rate) 套利與 RSI 趨勢預測來實現市場中性收益。

> **核心哲學**: 讓利潤奔跑的 Short 倉位為暫時虧損的 Long 倉位提供對沖，並賺取 Funding Fee。

---

## 🌟 核心策略架構 (Technical Architecture)

### 1. 雙重思維引擎 (Dual Mindset Engine)
*   **平行執行**: 利用 `asyncio.gather` 讓「做多大腦」與「做空大腦」在毫秒級同步運算，互不干擾。
*   **獨立風控**: 多空雙方各自擁有獨立的止盈 (TP) 與止損 (SL) 邏輯。

### 2. 智能對沖 (Smart Hedging & FR Farming)
*   **資金費率偏向 (FR Bias)**: 機器人實時監控 Gate.io 預測資金費率。
    *   若 FR > 0 (做多付費): 機器人自動偏向 **持有空單** (Target Inventory = Short)，以賺取資金費。
    *   若 FR < 0 (做空付費): 機器人自動偏向 **持有多單**。
*   **庫存偏離 (Inventory Skew)**: 利用 Avellaneda 公式，根據 FR 方向自動調整報價中樞，誘使市場成交有利方向。

### 3. 領先指標預測 (Leading Indicators)
*   **RSI 趨勢預測**:
    *   **超買 (>70)**: 預判回調，網格整體下移 (偏空報價)。
    *   **超賣 (<30)**: 預判反彈，網格整體上移 (偏多報價)。
*   **5m 趨勢跟隨**: 疊加 5分鐘價格斜率 (Alpha)，順勢而為。

### 4. 隧道鉗制網格 (Tunnel Clamp Grid)
針對高頻刷單 (Scalping) 優化的特殊網格結構：
*   **緊湊頭部 (Tight Head)**: 首單強制鉗制在 **0.02%** 價差內 (`MAX_ENTRY_SPREAD`)，確保極高成交率。
*   **寬尾部 (Wide Tail)**: 後續網格間距 **0.05%** (`LAYER_SPREAD`)，以 2 層結構覆蓋 5m K線波動範圍。
*   **Maker Guard**: 0.01% 安全距離，確保始終掛單 (Maker) 賺取返佣或降低費率。

---

## 📂 檔案結構

*   **`avellaneda_bot.py`**: **[入口]** 策略主程序。包含雙重思維、網格邏輯與下單執行。
*   **`avellaneda_utils.py`**: **[大腦]** 運算單元。負責計算 RSI、獲取 Real FR、波動率 (Sigma) 與趨勢 (Alpha)。
*   **`bot.py`**: **[驅動]** 底層接口。處理 Gate.io WebSocket 連線、Hedge Mode 設定與帳戶同步。
*   **`.env`**: API Key 配置 (支援 Testnet/Mainnet 自動切換)。

---

## 🚀 快速開始

### 1. 安裝依賴
```bash
pip install ccxt websockets python-dotenv numpy pandas
```

### 2. 配置 API
建立 `.env` 檔案：
```env
# 測試網 (優先使用)
GATEIO_TESTNET_KEY=你的Key
GATEIO_TESTNET_SECRET=你的Secret

# 主網 (若無測試網Key則使用)
API_KEY=你的主網Key
API_SECRET=你的主網Secret
```

### 3. 啟動策略
```bash
python avellaneda_bot.py
```

---

## ⚠️ 風險提示 (Risk Warning)

1.  **槓桿風險**: 預設 20x 槓桿。雖有對沖機制，但在極端單邊行情下仍需注意爆倉風險。
2.  **API 限制**: 高頻模式下請求量大，請留意 Gate.io Rate Limit。
3.  **單幣對沖**: 本策略在同一幣種上對沖，若幣價發生 50% 以上瞬間崩盤，雙向持倉可能同時面臨巨大波動。
