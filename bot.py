"""
AS 網格交易機器人 - Gate.io 命令行版
無 GUI 版本，適合在服務器上運行
"""
import asyncio
import websockets
import json
import logging
import hmac
import hashlib
import time
import ccxt
import math
import os
import datetime
from dotenv import load_dotenv

load_dotenv()

# ==================== 配置 ====================
API_KEY = os.getenv("GATEIO_TESTNET_KEY")
API_SECRET = os.getenv("GATEIO_TESTNET_SECRET")

if not API_KEY:
    API_KEY = os.getenv("API_KEY", "")
if not API_SECRET:
    API_SECRET = os.getenv("API_SECRET", "")

COIN_NAME = "XRP"
GRID_SPACING = 0.006 
TAKE_PROFIT_SPACING = 0.004
INITIAL_QUANTITY = 1 
LEVERAGE = 20
WEBSOCKET_URL = "wss://fx-ws.gateio.ws/v4/ws/usdt"
POSITION_THRESHOLD = 500
POSITION_LIMIT = 100
# HF Scalping Settings
ORDER_COOLDOWN_TIME = 1  
SYNC_TIME = 1 
ORDER_FIRST_TIME = 1  
STRATEGY_THROTTLE_INTERVAL = 2 
REPORT_INTERVAL = 300 

script_name = os.path.splitext(os.path.basename(__file__))[0]
os.makedirs("log", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"log/{script_name}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger()


class CustomGate(ccxt.gate):
    def fetch(self, url, method='GET', headers=None, body=None):
        if headers is None: headers = {}
        headers['X-Gate-Channel-Id'] = 'laohuoji'
        headers['Accept'] = 'application/json'
        headers['Content-Type'] = 'application/json'
        return super().fetch(url, method, headers, body)


class GridTradingBot:
    def __init__(self, api_key, api_secret, coin_name, grid_spacing, initial_quantity, leverage, take_profit_spacing=None, testnet=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.coin_name = coin_name
        self.grid_spacing = grid_spacing
        self.take_profit_spacing = take_profit_spacing or grid_spacing
        self.initial_quantity = initial_quantity
        self.leverage = leverage
        self.testnet = testnet
        
        if self.testnet:
             self.ws_url = "wss://fx-ws-testnet.gateio.ws/v4/ws/usdt"
             logger.info("Running in TESTNET mode")
        else:
             self.ws_url = WEBSOCKET_URL
        
        self.ccxt_symbol = f"{coin_name}/USDT:USDT"
        self.ws_symbol = f"{coin_name}_USDT"
        
        self.exchange = self._initialize_exchange()
        self.price_precision = self._get_price_precision()

        self.long_initial_quantity = initial_quantity
        self.short_initial_quantity = initial_quantity
        self.long_position = 0
        self.short_position = 0
        self.long_entry_price = 0.0
        self.short_entry_price = 0.0
        
        self.last_long_order_time = 0
        self.last_short_order_time = 0
        self.buy_long_orders = 0
        self.sell_long_orders = 0
        self.sell_short_orders = 0
        self.buy_short_orders = 0
        self.last_position_update_time = 0
        self.last_orders_update_time = 0
        self.latest_price = 0
        self.best_bid_price = None
        self.best_ask_price = None
        
        self.balance = {} 
        self.start_balance_usdt = None
        self.start_time = time.time()
        self.trade_history = [] 
        self.total_fees_paid = 0.0
        self.last_strategy_run_time = 0.0

    def _initialize_exchange(self):
        exchange = CustomGate({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "options": {"defaultType": "future"},
        })
        if self.testnet:
            exchange.set_sandbox_mode(True)
        
        try:
            exchange.load_markets()
            try:
                exchange.set_position_mode(True, self.ccxt_symbol)
                logger.info("已設置為雙向持倉模式 (Hedge Mode)")
            except Exception as e:
                logger.warning(f"設置 Hedge Mode 失敗: {e}")
        except Exception as e:
            logger.error(f"初始化 Exchange 失敗: {e}")

        return exchange

    def _get_price_precision(self):
        markets = self.exchange.fetch_markets()
        symbol_info = next(market for market in markets if market["symbol"] == self.ccxt_symbol)
        return int(-math.log10(float(symbol_info["precision"]["price"])))

    def get_position(self):
        params = {'settle': 'usdt', 'type': 'swap'}
        positions = self.exchange.fetch_positions(params=params)
        long_position = 0
        short_position = 0
        long_entry = 0.0
        short_entry = 0.0

        for position in positions:
            if position['symbol'] == self.ccxt_symbol:
                contracts = float(position.get('contracts', 0))
                side = position.get('side', None)
                entry_price = float(position.get('entryPrice', 0))
                if side == 'long':
                    long_position = contracts
                    long_entry = entry_price
                elif side == 'short':
                    short_position = abs(contracts)
                    short_entry = entry_price

        return long_position, long_entry, short_position, short_entry

    def check_orders_status(self):
        orders = self.exchange.fetch_open_orders(self.ccxt_symbol)
        buy_long_orders_count = 0
        sell_long_orders_count = 0
        sell_short_orders_count = 0
        buy_short_orders_count = 0

        for order in orders:
            if not order.get('info') or 'left' not in order['info']: continue
            left = abs(float(order['info'].get('left', '0')))
            ro = order.get('reduceOnly')
            side = order.get('side')
            
            if ro and side == 'sell': sell_long_orders_count = left
            elif ro and side == 'buy': buy_short_orders_count = left
            elif not ro and side == 'buy': buy_long_orders_count = left
            elif not ro and side == 'sell': sell_short_orders_count = left

        return buy_long_orders_count, sell_long_orders_count, sell_short_orders_count, buy_short_orders_count

    async def run(self):
        self.long_position, self.long_entry_price, self.short_position, self.short_entry_price = self.get_position()
        logger.info(f"Init Positions: Long {self.long_position} (@{self.long_entry_price}), Short {self.short_position} (@{self.short_entry_price})")

        self.buy_long_orders, self.sell_long_orders, self.sell_short_orders, self.buy_short_orders = self.check_orders_status()
        
        asyncio.create_task(self.reporting_loop())

        while True:
            try:
                await self.connect_websocket()
            except Exception as e:
                logger.error(f"WebSocket Error: {e}")
                await asyncio.sleep(5)

    async def connect_websocket(self):
        # FIX: Keepalive settings
        async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as websocket:
            await self.subscribe_all(websocket)
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    channel = data.get("channel")

                    if channel == "futures.tickers":
                        await self.handle_ticker_update(message)
                    elif channel == "futures.positions":
                        await self.handle_position_update(message)
                    elif channel == "futures.orders":
                        await self.handle_order_update(message)
                    elif channel == "futures.usertrades":
                        await self.handle_usertrades_update(message) 
                    elif channel == "futures.book_ticker":
                        await self.handle_book_ticker_update(message)
                    elif channel == "futures.balances":
                        await self.handle_balance_update(message)
                except Exception as e:
                    logger.error(f"WS Msg Error: {e}")
                    break

    def _generate_sign(self, message):
        return hmac.new(self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha512).hexdigest()

    async def subscribe_all(self, websocket):
        for chan in ["futures.tickers", "futures.positions", "futures.orders", "futures.usertrades", "futures.book_ticker", "futures.balances"]:
            await self.send_sub(websocket, chan)

    async def send_sub(self, websocket, channel):
        t = int(time.time())
        msg = f"channel={channel}&event=subscribe&time={t}"
        sign = self._generate_sign(msg)
        payload = {
            "time": t, "channel": channel, "event": "subscribe",
            "payload": [self.ws_symbol] if channel != "futures.balances" else ["USDT"],
            "auth": {"method": "api_key", "KEY": self.api_key, "SIGN": sign},
        }
        await websocket.send(json.dumps(payload))

    async def handle_balance_update(self, message):
        data = json.loads(message)
        if data.get("event") == "update":
            for bal in data.get("result", []):
                curr = bal.get("currency", "")
                self.balance[curr] = {"balance": float(bal.get("balance",0)), "change": float(bal.get("change",0))}
                if curr == "USDT" and self.start_balance_usdt is None:
                    self.start_balance_usdt = float(bal.get("balance",0))

    async def handle_ticker_update(self, message):
        data = json.loads(message)
        if data.get("event") == "update":
            res = data["result"][0]
            if "mark_price" in res and res["mark_price"]:
                self.latest_price = float(res["mark_price"])
            else:
                self.latest_price = float(res["last"])

            if time.time() - self.last_strategy_run_time < STRATEGY_THROTTLE_INTERVAL: return 
            self.last_strategy_run_time = time.time()

            if time.time() - self.last_position_update_time > SYNC_TIME:
                self.long_position, self.long_entry_price, self.short_position, self.short_entry_price = self.get_position()
                self.last_position_update_time = time.time()

            if time.time() - self.last_orders_update_time > SYNC_TIME:
                self.buy_long_orders, self.sell_long_orders, self.sell_short_orders, self.buy_short_orders = self.check_orders_status()
                self.last_orders_update_time = time.time()

            await self.adjust_grid_strategy()

    async def handle_book_ticker_update(self, message):
        data = json.loads(message)
        if data.get("event") == "update":
            r = data["result"]
            if r:
                self.best_bid_price = float(r.get("b", 0))
                self.best_ask_price = float(r.get("a", 0))

    async def handle_position_update(self, message):
        data = json.loads(message)
        if data.get("event") == "update":
            for pos in data["result"]:
                if pos.get("mode") == "dual_long":
                    self.long_position = abs(float(pos.get("size", 0)))
                    self.long_entry_price = float(pos.get("entry_price", 0))
                else:
                    self.short_position = abs(float(pos.get("size", 0)))
                    self.short_entry_price = float(pos.get("entry_price", 0))

    async def handle_order_update(self, message):
        data = json.loads(message)
        if data.get("event") == "update":
            for o in data["result"]:
                if 'is_reduce_only' not in o: continue
                size = o.get('size', 0)
                ro = o.get('is_reduce_only', False)
                if size > 0:
                    if ro: self.buy_short_orders = abs(o.get('left', 0))
                    else: self.buy_long_orders = abs(o.get('left', 0))
                else:
                    if ro: self.sell_long_orders = abs(o.get('left', 0))
                    else: self.sell_short_orders = abs(o.get('left', 0))

    async def handle_usertrades_update(self, message):
        data = json.loads(message)
        if data.get("event") == "update":
            for t in data["result"]:
                self.trade_history.append(t)
                self.total_fees_paid += float(t.get("fee", 0))
                logger.info(f"Fill: {t['size']} @ {t['price']}")

    async def reporting_loop(self):
        while True:
            await asyncio.sleep(REPORT_INTERVAL)
            try: self._generate_report()
            except Exception as e: logger.error(f"Report Error: {e}")

    def _generate_report(self):
        dur = str(datetime.timedelta(seconds=int(time.time() - self.start_time)))
        trades = len(self.trade_history)
        cur_usdt = self.balance.get("USDT", {}).get("balance", 0)
        start = self.start_balance_usdt or cur_usdt
        pnl = cur_usdt - start
        
        logger.info("\n" + "="*40)
        logger.info(f"REPORT | Duration: {dur} | Trades: {trades}")
        logger.info(f"USDT: {start:.2f} -> {cur_usdt:.2f} (PnL: {pnl:+.2f})")
        logger.info("="*40 + "\n")

    def cancel_orders_for_side(self, position_side, for_tp=False):
        orders = self.exchange.fetch_open_orders(self.ccxt_symbol)
        for order in orders:
            is_reduce = order['reduceOnly']
            side = order['side']
            if position_side == 'long':
                if for_tp:
                    if is_reduce and side == 'sell': self.cancel_order(order['id'])
                else:
                    if not is_reduce and side == 'buy': self.cancel_order(order['id'])
            elif position_side == 'short':
                if for_tp:
                    if is_reduce and side == 'buy': self.cancel_order(order['id'])
                else:
                    if not is_reduce and side == 'sell': self.cancel_order(order['id'])

    def cancel_order(self, order_id):
        try: self.exchange.cancel_order(order_id, self.ccxt_symbol)
        except: pass

    def place_order(self, side, price, quantity, is_reduce_only=False, position_side=None):
        try:
            params = {'reduce_only': is_reduce_only}
            if position_side:
                params['positionSide'] = position_side.lower()
            self.exchange.create_order(self.ccxt_symbol, 'limit', side, quantity, price, params)
        except ccxt.BaseError as e:
            logger.error(f"Order Error ({side} @ {price}): {e}")

    # Abstract methods
    async def adjust_grid_strategy(self): pass
