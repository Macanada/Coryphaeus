# keep_alive_ws.py
import asyncio
import json
import time
import logging
from datetime import datetime

class KeepAliveWS:
    def __init__(self, websocket, api_client=None, logger=None, interval=600, inactivity_mode=False, inactivity_timeout=600, verbose=False):
        self.websocket = websocket
        self.api_client = api_client  # Instância do BybitRestClient
        self.logger = logger or logging.getLogger(__name__)
        self.interval = interval
        self.inactivity_mode = inactivity_mode
        self.inactivity_timeout = inactivity_timeout
        self.verbose = verbose
        self._last_activity = time.time()
        self._running = False
        self._task = None
        self.wallet_subscribed = False

    def reset_timer(self):
        """Reset the activity timer"""
        self._last_activity = time.time()

    async def start(self):
        """Start the keep alive mechanism"""
        if self._running:
            return
        
        self._running = True
        self.logger.info("🫀 Iniciando KeepAlive WebSocket...")
        
        # Subscrever ao wallet stream para manter conexão ativa
        await self._subscribe_wallet_stream()
        
        self._task = asyncio.create_task(self._keep_alive_loop())

    async def stop(self):
        """Stop the keep alive mechanism"""
        if not self._running:
            return
            
        self._running = False
        
        # Desinscrever do wallet stream
        await self._unsubscribe_wallet_stream()
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        self.logger.info("🛑 KeepAlive WebSocket encerrado.")

    async def _subscribe_wallet_stream(self):
        """Subscribe to wallet stream to keep connection active"""
        try:
            if self.websocket and not self.websocket.closed:
                wallet_msg = {
                    "op": "subscribe",
                    "args": ["wallet"]
                }
                await self.websocket.send(json.dumps(wallet_msg))
                self.wallet_subscribed = True
                self.logger.info("💰 Subscrito ao wallet stream para manter conexão ativa")
        except Exception as e:
            self.logger.error(f"Erro ao subscrever wallet stream: {e}")

    async def _unsubscribe_wallet_stream(self):
        """Unsubscribe from wallet stream"""
        try:
            if self.websocket and not self.websocket.closed and self.wallet_subscribed:
                wallet_msg = {
                    "op": "unsubscribe",
                    "args": ["wallet"]
                }
                await self.websocket.send(json.dumps(wallet_msg))
                self.wallet_subscribed = False
                self.logger.info("💰 Desinscrito do wallet stream")
        except Exception as e:
            self.logger.error(f"Erro ao desinscrever wallet stream: {e}")

    async def _keep_alive_loop(self):
        """Main keep alive loop"""
        try:
            while self._running:
                await asyncio.sleep(self.interval)
                
                if not self._running:
                    break
                    
                # Verificar se WebSocket ainda está conectado
                if not self.websocket or self.websocket.closed:
                    self.logger.warning("WebSocket fechado, encerrando KeepAlive")
                    break
                
                # Se estiver em modo de inatividade, verificar tempo desde última atividade
                if self.inactivity_mode:
                    time_since_activity = time.time() - self._last_activity
                    
                    if time_since_activity >= self.inactivity_timeout:
                        # Em vez de fazer consulta REST, o wallet stream já mantém a conexão ativa
                        # Apenas enviar ping como fallback
                        await self._send_ping()
                        self.reset_timer()
                else:
                    # Modo normal: enviar ping periodicamente
                    await self._send_ping()
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Erro no loop KeepAlive: {e}")
        finally:
            self._running = False

    async def _send_ping(self):
        """Send ping to keep connection alive (fallback method)"""
        try:
            if self.websocket and not self.websocket.closed:
                ping_msg = {"op": "ping"}
                await self.websocket.send(json.dumps(ping_msg))
                
                # Aguardar pong com timeout
                try:
                    ping_msg = {"op": "ping"}
                    await self.websocket.send(json.dumps(ping_msg))
                    if self.verbose:
                        self.logger.info("🏓 Ping enviado")

#                    response = await asyncio.wait_for(self.websocket.recv(), timeout=10)
#                    pong_data = json.loads(response)
#                    if pong_data.get('op') == 'pong':
                        if self.verbose:
                            self.logger.info("🏓 Ping-pong bem-sucedido")
                except asyncio.TimeoutError:
                    self.logger.warning("⚠️ Timeout aguardando pong")
                except Exception as e:
                    self.logger.error(f"Erro processando pong: {e}")
        except Exception as e:
            self.logger.error(f"Erro enviando ping: {e}")