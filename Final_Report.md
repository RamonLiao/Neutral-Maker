# 量化交易策略專案結案報告 (Final Report)

**專案名稱**: Avellaneda-Stoikov 雙向對沖做市策略 (AS-Hedge)
**報告對象**: 專案指導委員會 (Steering Committee)
**日期**: 2025-12-12
**狀態**: 已上線 (Production Ready)

---

## 1. 執行摘要 (Executive Summary)

本專案旨在構建一套適用於加密貨幣永續合約的**高頻做市 (Market Making) 機器人**。我們成功突破了傳統網格策略「單邊被套」的痛點，開發出基於 **Avellaneda-Stoikov 模型** 的改良版「**雙重思維 (Dual Mindset)**」架構。

該系統在單一幣種 (如 XRP) 上同時運行長線與短線邏輯，利用 **資金費率 (Funding Rate) 套利** 與 **RSI 領先指標** 進行動態對沖。實測顯示，系統能有效在震盪行情中捕捉微小價差 (0.02%)，並在趨勢行情中利用反向倉位提供利潤保護。

---

## 2. 技術架構突破 (Technical Innovations)

### 2.1 雙重思維引擎 (Dual Mindset Engine)
傳統機器人多為單線程邏輯，難以同時處理多空雙向的複雜狀態。我們引入了 `Asyncio` 並行架構：
*   **並行運算**: 「做多大腦」與「做空大腦」在微秒級同步執行，互不阻塞。
*   **獨立決策**: 兩套思維擁有獨立的參數與風控標準，真正實現了「左右互搏」的自我對沖效果。

### 2.2 隧道鉗制技術 (Tunnel Clamp)
為解決 Avellaneda 模型在極端行情下報價過寬的問題，我們開發了「隧道鉗制」算法：
*   **首單鉗制**: 強制首單掛在 `Mid Price ± 0.02%` 的極窄區間內。
*   **Maker Guard**: 智能計算 0.01% 的最小安全距離，確保始終以 Maker (掛單) 身份成交，賺取返佣或降低費率。

---

## 3. 核心策略邏輯 (Core Strategy Logic)

本策略融合了學術模型與實戰經驗，形成三大核心支柱：

### 3.1 資金費率收割 (FR Farming)
*   **邏輯**: 機器人實時監控交易所的預測資金費率 (Predicted Funding Rate)。
*   **行動**:
    *   若 `FR > 0` (多頭付費): 系統自動調整目標庫存 (Target Inventory) 為 **空頭 (Short)**。
    *   若 `FR < 0` (空頭付費): 系統自動偏向持有 **多頭 (Long)**。
*   **效益**: 讓持倉成為「正期望值」資產，時間成為朋友而非敵人。

### 3.2 RSI 趨勢預判 (Leading Indicators)
*   **邏輯**: 傳統 Avellaneda 僅依賴價格斜率 (滯後指標)。我們引入 5分鐘 RSI (相對強弱指標) 作為領先指標。
*   **行動**:
    *   `RSI > 70` (超買): 預判回調，Avellaneda 中樞價格下移，提前佈局空單。
    *   `RSI < 30` (超賣): 預判反彈，中樞價格上移，提前佈局多單。

### 3.3 動態網格 (Dynamic Grid)
*   **結構**: 採用 "Tight Head, Wide Tail" (緊頭寬尾) 配置。
    *   **第 1 層**: 0.02% 價差 (高頻刷單)。
    *   **第 2 層**: 0.05% 價差 (覆蓋 5m K線波動)。

---

## 4. 風險管理 (Risk Management)

| 風險維度 | 應對機制 |
| :--- | :--- |
| **庫存積壓** | 透過 `Inventory Risk` 參數 ($\gamma$)，當庫存過高時呈指數級擴大報價價差，強迫平倉。 |
| **單邊趨勢** | 5m Trend Alpha + RSI 雙重濾網。逆勢時自動減少掛單密度，順勢時加強進場。 |
| **系統崩潰** | WebSocket 心跳檢測 (Keepalive) + API 重試機制 (Retry Logic) + 零價防護 (Zero-Price Guard)。 |
| **手續費磨損** | Maker Guard 嚴格限制，絕不主動吃單 (Taker)，確保費率優勢。 |

---

## 5. 未來展望 (Roadmap)

基於目前的穩定架構，下一階段的迭代方向如下：

1.  **AI 選幣引擎 (Coin Selector)**:
    *   開發 `scanner.py`，自動掃描全市場波動率與流動性，動態切換至在此刻最適合做市的幣種 (如 DOGE, SUI 等)。
2.  **強化學習參數優化 (RL Optimization)**:
    *   引入 UCB (Upper Confidence Bound) 算法，讓機器人在實盤中自動試錯，動態尋找最佳的 `Gamma` 與 `K` 值。
3.  **多交易所套利 (Cross-Exchange)**:
    *   將策略擴展至 Binance 與 Bybit，進行跨交易所的 Funding Rate 套利。

---

**結論**:
AS-Hedge 機器人已完成從「基礎網格」到「智能對沖系統」的蛻變。它不僅能捕捉震盪利潤，更具備了利用市場機制 (費率) 獲利的被動收入能力。系統架構穩健，具備極高的擴展性。

**報告人**: Antigravity (Google Deepmind)
