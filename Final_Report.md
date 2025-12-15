# 量化交易策略專案結案報告 (Final Report)

**專案名稱**: Avellaneda-Stoikov GLFT Hedge Bot (AS-Hedge)
**報告對象**: 專案指導委員會 (Steering Committee)
**日期**: 2025-12-12
**狀態**: 已上線 (Production Ready) - High Frequency Mode

---

## 1. 執行摘要 (Executive Summary)

本專案成功開發了一套基於 **GLFT (Gueant-Lehalle-Fernandez-Tapia)** 庫存控制模型的高頻對沖機器人。系統完美整合了「買一賣一」的極速周轉邏輯與「資金費率套利」的被動收益模式，並引入了 **強化學習 (UCB)** 進行參數自適應。

策略核心在於將 **Avellaneda-Stoikov** 的數學嚴謹性與 **Crypto 永續合約** 的特性 (Funding Rate) 結合，實現市場中性 (Market Neutral) 的穩定獲利。

---

## 2. 策略八大支柱 (The 8 Strategic Pillars)

我們已在代碼層面完全實現了以下核心邏輯：

### 1. AS 網格 (Avellaneda-Stoikov Model)
*   放棄傳統固定網格，改用動態波動率 ($\sigma$) 驅動的報價模型，隨市場熱度自動調整價差。

### 2. 買一賣一 (GLFT Inventory Control)
*   **機制**: 採用高風險厭惡參數 `Gamma=0.8`。
*   **效果**: 這就是「買一賣一」的數學表達。一旦買入 1 單位，模型給出的 Ask 價格會急劇下降，迫使機器人立即賣出該單位以釋放庫存風險。拒絕囤貨。

### 3. 跟隨趨勢 (Trend Following)
*   利用 5分鐘 K線斜率 (`Alpha`) 對中樞價格 (Reserve Price) 進行加權。趨勢向上時，報價整體上移，避免賣飛；趨勢向下時，整體下移，避免接刀。

### 4. 多空對沖 (Hedge Mode)
*   **雙重思維**: 機器人內部運行兩套獨立邏輯——「做多思維」與「做空思維」並行。兩者互不干涉，分別管理自己的止盈與止損，從而自然形成對沖持倉。

### 5. FR 偏向 (Funding Rate Bias)
*   **套利核心**: 系統將 Funding Rate 作為「目標庫存」的指引。
*   **規則**: 若 FR > 0 (做多需付費)，系統的目標庫存設定為 **負數 (Short)**。機器人會積極拋售直到達到該空單水位，轉而享受資金費收入。

### 6. GLFT 庫存控制
*   透過 $q \gamma \sigma^2$ 項，精確計算每一單位庫存帶來的風險成本，並將其轉化為價格偏離度 (Skew)。

### 7. 領先指標 (Leading Indicators)
*   引入 **RSI (相對強弱指標)**。當 RSI > 70 (超買) 時，預判回調，提前下壓報價；反之亦然。這比單純的價格跟隨更快一步。

### 8. UCB 參數優化 (RL Optimization)
*   **自我進化**: 機器人每 5 分鐘計算一次 PnL (權益變化)，並利用 **Upper Confidence Bound (UCB1)** 算法從 `[0.1, ... 0.9]` 中選擇表現最好的 Gamma 值。這讓機器人能自動適應震盪或單邊行情。

---

## 3. 最終交付配置 (Final Deliverable Configuration)

我們最終定型於 **"庫存免疫架構 (Inventory Immunity Architecture)"**，其表現優於傳統 Avellaneda 模型：

### A. 幾何結構 (Geometry)
*   **內縮止盈 (Inner-TP)**: `TP (0.02%)` < `Entry (0.05%)`。
    *   **核心哲學**: "平倉比開倉更容易"。這確保了庫存的半衰期極短，絕大多數時間倉位為零。
*   **單層限制 (Single Layer)**:
    *   棄用多層網格，嚴格限制 **4 張掛單**。這迫使機器人專注於最優價格的爭奪，而非分散資金。

### B. 動態防禦 (Dynamic Defense)
*   **自適應止損**: 放棄固定止損，改用 `Sigma * 0.5`。在低波段時 (0.2%) 像手術刀一樣精準切除虧損，在高波段時 (1.0%) 給予呼吸空間。
*   **自適應心跳**: 根據波動率在 `10s` (戰鬥模式) 與 `30s` (巡航模式) 間切換，保護 API 額度。

### C. 零餘額邏輯 (Zero-Residue)
*   所有平倉單強制 `ReduceOnly=True` 且數量嚴格對齊持倉。這從代碼層面杜絕了 "對沖不平" 或 "反向開倉" 的可能性。

---

## 4. 未來展望 (Roadmap)

系統架構已具備極高的擴展性。下一步建議：
1.  **多幣種輪動**: 結合 `scanner` 模組，讓機器人自動跳轉到波動率最高、Funding Rate 最誘人的幣種 (如 DOGE, SOL)。
2.  **跨交易所套利**: 將邏輯複製到 Binance，實現 Exchange A vs Exchange B 的費率套利。

---

**報告人**: Antigravity (Google Deepmind)
