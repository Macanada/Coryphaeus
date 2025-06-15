
# websocket_monitor.py (refatorado)
import asyncio
import json
import time
import hmac
import hashlib
import logging
from datetime import datetime
from websockets import connect
import websockets.exceptions
from typing import Dict
from exchange.core.keep_alive_ws import KeepAliveWS

EXCHANGE_CONFIG = {
    'Bybit Demo': {'ws_url': 'wss://stream-demo.bybit.com/v5/private'},
    'Bybit Main': {'ws_url': 'wss://stream.bybit.com/v5/private'}
}

class BybitWebSocketMonitor:
    def __init__(self, trader, config: Dict, logger: logging.Logger, error_logger: logging.Logger):
        self.trader = trader
        self.ws_url = EXCHANGE_CONFIG[config['exchange']]['ws_url']
        self.api_key = config['api_key']
        self.api_secret = config['api_secret']
        self.logger = logger
        self.error_logger = error_logger
        self.ws = None
        self.ws_connected = False
        self.keep_alive = None

    async def connect_websocket(self) -> bool:
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚡ Connecting to WebSocket: {self.ws_url}")
        try:
            self.ws = await connect(self.ws_url)
            self.ws_connected = True

            expires = int((time.time() + 5) * 1000)
            sign_payload = f"GET/realtime{expires}"
            signature = hmac.new(self.api_secret.encode('utf-8'), sign_payload.encode('utf-8'), hashlib.sha256).hexdigest()

            auth_msg = {"op": "auth", "args": [self.api_key, expires, signature]}
            await self.ws.send(json.dumps(auth_msg))
            auth_response = await self.ws.recv()
            auth_data = json.loads(auth_response)
            if not auth_data.get('success', False):
                self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ WebSocket authentication failed: {auth_response}")
                return False

            self.logger.info(f"🔑 WebSocket authentication successful.")

            subscribe_msg = {"op": "subscribe", "args": ["order", "execution"]}
            await self.ws.send(json.dumps(subscribe_msg))
            await self.ws.recv()
            self.logger.info("📡 WebSocket subscription successful.")

            if self.keep_alive:
                await self.keep_alive.stop()

            self.keep_alive = KeepAliveWS(
                self.ws,
                logger=self.logger,
                interval=60,
                inactivity_mode=True,
                inactivity_timeout=400,
                verbose=False
            )
            asyncio.create_task(self.keep_alive.start())

            return True

        except Exception as e:
            self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ WebSocket connection failed: {e}")
            self.ws_connected = False
            self.ws = None
            return False

    async def monitor_cycle(self):
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Monitoring cycle #{self.trader.cycle_id} with {len(self.trader.cycle_buys)} buys...")
        self.trader.order_event.clear()

        while not self.trader.order_event.is_set() and self.trader.running:
            try:
                
                if not self.ws or self.ws.closed:
                    self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ WebSocket disconnected. Reconnecting...")
                    self.ws_connected = False
                    if not await self.connect_websocket():
                        self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Failed to reconnect. Ending cycle...")
                        self.trader.order_event.set()
                        return

                msg = await asyncio.wait_for(self.ws.recv(), timeout=5)

                if self.keep_alive:
                    self.keep_alive.reset_timer()

                data = json.loads(msg)

                if data.get('topic') == 'wallet':
                    # Verificar se há recompra pendente por saldo insuficiente
                    if self.trader.paused_for_insufficient_balance:
                        # Tentar executar recompra pendente se há saldo suficiente
                        if await self.trader.try_execute_pending_rebuy():
                            # Se a recompra foi executada com sucesso, continuar monitoramento normal
                            pass
                    
                    if self.keep_alive and self.keep_alive.verbose:
                        self.logger.info("💰 Wallet update received (used to keep connection alive)")
                    continue

                if data.get('topic') == 'order':
                    for order in data.get('data', []):
                        order_id = order.get('orderId')
                        status = order.get('orderStatus')

                        if order_id not in [self.trader.current_sell_id, self.trader.current_rebuy_id]:
                            continue

                        self.logger.debug(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📊 Order {order_id} updated: Status {status}")

                        if status == 'Filled':
                            if order_id == self.trader.current_sell_id:
                                await self.trader.on_sell_filled()
                                self.trader.order_event.set()
                                break
                            elif order_id == self.trader.current_rebuy_id:
                                await self.trader.order_status(order)
                                break

                        elif status in ['Cancelled', 'Rejected']:
                            if order_id == self.trader.current_sell_id:
                                self.trader.current_sell_id = None
                            elif order_id == self.trader.current_rebuy_id:
                                self.trader.current_rebuy_id = None

                            if order_id in self.trader.active_orders:
                                del self.trader.active_orders[order_id]

            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔌 WebSocket connection closed. Attempting to reconnect...")
                self.ws_connected = False
                if not await self.connect_websocket():
                    self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Failed to reconnect. Ending cycle...")
                    self.trader.order_event.set()
                    return
            except Exception as e:
                self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🛑 Monitoring error: {e}")
                await asyncio.sleep(1)
