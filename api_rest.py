# api_rest.py
import requests
import hmac
import hashlib
import json
import time
import logging
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Tuple, Optional

# Constants
EXCHANGE_CONFIG = {
    'Bybit Demo': {'base_url': 'https://api-demo.bybit.com'},
    'Bybit Main': {'base_url': 'https://api.bybit.com'}
}
RECV_WINDOW = "5000"

class BybitRestClient:
    def __init__(self, config: Dict, logger: logging.Logger, error_logger: logging.Logger):
        self.base_url = EXCHANGE_CONFIG[config['exchange']]['base_url']
        self.api_key = config['api_key']
        self.api_secret = config['api_secret']
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.server_time_offset = 0
        self.logger = logger
        self.error_logger = error_logger

    def sync_server_time(self):
        try:
            response = self.session.get(f"{self.base_url}/v5/market/time")
            data = response.json()
            server_time_ms = int(data["result"]["timeNano"]) // 1_000_000
            local_time_ms = int(time.time() * 1000)
            self.server_time_offset = (server_time_ms - local_time_ms) / 1000
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ Offset de tempo ajustado: {self.server_time_offset:.3f} segundos\n")
        except Exception as e:
            self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao sincronizar horário: {e}")

    def _generate_signature(self, params: Dict, method: str, timestamp: str) -> str:
        param_str = '&'.join([f"{k}={str(v).replace(',', '%2C')}" for k, v in sorted(params.items())]) if method == "GET" else json.dumps(params)
        sign_str = timestamp + self.api_key + RECV_WINDOW + param_str
        return hmac.new(self.api_secret.encode('utf-8'), sign_str.encode('utf-8'), hashlib.sha256).hexdigest()

    def _get_auth_headers(self, params: Dict, method: str) -> Dict:
        timestamp = str(int(time.time() * 1000 + self.server_time_offset * 1000))
        signature = self._generate_signature(params, method, timestamp)
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            "X-BAPI-SIGN": signature
        }

    def validate_api_keys(self) -> Tuple[bool, str]:
        endpoint = "/v5/account/info"
        params = {}
        try:
            self.sync_server_time()
            response = self.session.get(self.base_url + endpoint, headers=self._get_auth_headers(params, "GET"), params=params)
            data = response.json()
            if data.get('retCode') == 0:
                return True, "✅ Conexão com chaves API bem sucedida!"
            else:
                return False, f"⚠️ Falha na validação das chaves API: {data.get('retMsg', 'Erro desconhecido')}"
        except Exception as e:
            return False, f"⚠️ Erro ao validar chaves API: {str(e)}"

    def get_balances(self) -> Tuple[Decimal, Decimal, bool]:
        endpoint = "/v5/account/wallet-balance"
        try:
            self.sync_server_time()
            params_usdt = {"accountType": "UNIFIED", "coin": "USDT"}
            response_usdt = self.session.get(self.base_url + endpoint, headers=self._get_auth_headers(params_usdt, "GET"),
                                             params=params_usdt)
            data_usdt = response_usdt.json()
            if data_usdt.get('retCode') != 0:
                self.error_logger.error(f"Erro USDT: {data_usdt.get('retMsg')}")
                return Decimal('0'), Decimal('0'), False
            usdt_balance = Decimal(data_usdt['result']['list'][0]['coin'][0]['walletBalance'])

            params_btc = {"accountType": "UNIFIED", "coin": "BTC"}
            response_btc = self.session.get(self.base_url + endpoint, headers=self._get_auth_headers(params_btc, "GET"),
                                            params=params_btc)
            data_btc = response_btc.json()
            if data_btc.get('retCode') != 0:
                self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Erro BTC: {data_btc.get('retMsg')}")
                return Decimal('0'), Decimal('0'), False
            btc_balance = Decimal(data_btc['result']['list'][0]['coin'][0]['walletBalance'])

            self.logger.info(f"\n💰 Saldos Atuais:\nBTC: {btc_balance:.8f}\nUSDT: {usdt_balance:.2f}\n")
            return btc_balance, usdt_balance, True
        except Exception as e:
            self.error_logger.error(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Erro ao obter saldos: {str(e)}")
            return Decimal('0'), Decimal('0'), False

    def place_order(self, side: str, qty: str, order_type: str, price: str, fee: float) -> Optional[str]:
        endpoint = "/v5/order/create"
        params = self._create_order_params(side, qty, order_type, price, fee)
        if params is None:
            return None
        data = self._send_order_request(params, endpoint)
        return self._process_order_response(data, side, params)

    def _create_order_params(self, side: str, qty: str, order_type: str, price: str, fee: float) -> Optional[Dict]:
        is_rebuy = side.lower() == "buy"  # Simplified for this module
        actual_qty_usdt = Decimal(str(qty))
        params = {
            "category": "spot",
            "symbol": "BTCUSDT",
            "side": side.capitalize(),
            "orderType": order_type,
            "timeInForce": "GTC" if order_type == "Limit" else "IOC",
            "orderFilter": "Order"
        }
        if side.lower() == "buy":
            if order_type == "Market":
                params["qty"] = f"{actual_qty_usdt:.2f}"
                self.logger.info(f"🛒 Enviando ordem de compra a mercado. Quantidade: {actual_qty_usdt:.2f} USDT\n")
            elif order_type == "Limit" and price:
                try:
                    price_decimal = Decimal(str(price)).quantize(Decimal('1'), rounding=ROUND_DOWN)
                    if price_decimal > 0:
                        actual_qty_btc = actual_qty_usdt / price_decimal
                        params["qty"] = f"{actual_qty_btc:.6f}"
                        params["price"] = str(int(price_decimal))
                        self.logger.info(f"🔍 Convertendo {actual_qty_usdt:.2f} USDT para {actual_qty_btc:.6f} BTC a {price_decimal:.0f} USDT/BTC")
                    else:
                        self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Preço da ordem limite inválido!")
                        return None
                except Exception as e:
                    self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Erro ao calcular qty BTC para ordem limite: {e}")
                    return None
        elif side.lower() == "sell" and price:
            price_decimal = Decimal(str(price)).quantize(Decimal('1'), rounding=ROUND_DOWN)
            params["qty"] = qty
            params["price"] = str(int(price_decimal))
            usdt_value = Decimal(qty) * price_decimal
            self.logger.info(f"📈 Calculando ordem de venda limite: Quantidade: {qty} BTC, Preço: {price_decimal:.0f} USDT/BTC, Valor: {usdt_value:.2f} USDT")
        if "qty" not in params:
            self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Erro ao criar parâmetros da ordem: quantidade ausente!")
            return None
        return params

    def _send_order_request(self, params: Dict, endpoint: str) -> Optional[Dict]:
        try:
            response = self.session.post(self.base_url + endpoint, json=params, headers=self._get_auth_headers(params, "POST"))
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Erro na requisição para {endpoint}: {str(e)}")
            return None

    def _process_order_response(self, data: Optional[Dict], side: str, params: Dict) -> Optional[str]:
        if data is None:
            self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha na ordem {side}: Resposta nula da API.")
            return None
        if data.get('retCode') == 0:
            order_id = data['result']['orderId']
            executed_qty = data['result'].get('cumExecQty', params.get('qty', 'N/A'))
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Ordem {side} enviada! ID: {order_id} | Qty: {executed_qty} | Price: {params.get('price', 'Mercado')}")
            return order_id
        else:
            self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha na ordem {side}: {data.get('retMsg')}\n")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        endpoint = "/v5/order/cancel"
        params = {"category": "spot", "symbol": "BTCUSDT", "orderId": order_id}
        try:
            response = self.session.post(self.base_url + endpoint, json=params,
                                         headers=self._get_auth_headers(params, "POST"))
            data = response.json()
            if data.get('retCode') == 0 or data.get('retCode') == 110001:
                self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Ordem {order_id} cancelada com sucesso!\n")
                return True
            else:
                self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Falha ao cancelar ordem {order_id}: {data.get('retMsg')}")
                return False
        except Exception as e:
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Erro ao cancelar ordem {order_id}: {str(e)}")
            return False

    def get_order_details(self, order_id: str, max_retries: int = 3) -> Dict:
        # Primeiro tenta buscar em ordens ativas
        realtime_endpoint = "/v5/order/realtime"
        history_endpoint = "/v5/order/history"
        params = {"category": "spot", "orderId": order_id}
        
        for attempt in range(max_retries):
            try:
                # Primeiro tenta ordens ativas
                response = self.session.get(self.base_url + realtime_endpoint, 
                                        headers=self._get_auth_headers(params, "GET"), params=params)
                data = response.json()
                
                # Se não encontrar em ordens ativas, tenta no histórico
                if not (data.get('retCode') == 0 and data.get('result', {}).get('list')):
                    response = self.session.get(self.base_url + history_endpoint, 
                                            headers=self._get_auth_headers(params, "GET"), params=params)
                    data = response.json()
                
                self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Resposta da API para ordem {order_id} (tentativa {attempt + 1}):")
                
                if data.get('retCode') == 0 and data.get('result', {}).get('list'):
                    order = data['result']['list'][0]
                    price = Decimal(order.get('avgPrice', '0') or '0')
                    qty = Decimal(order.get('cumExecQty', '0') or '0')
                    
                    if price == 0 or qty == 0:
                        if attempt < max_retries - 1:
                            self.logger.info(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Dados inválidos recebidos, tentando novamente em 1 segundo...")
                            time.sleep(1)
                            continue
                            
                    return {"price": price, "qty": qty, "status": order.get('orderStatus', 'Unknown')}
                    
                if attempt < max_retries - 1:
                    self.logger.info(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Resposta inválida, tentando novamente em 1 segundo...")
                    time.sleep(1)
                    continue
                    
                self.logger.info(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Ordem não encontrada ou resposta inválida após {max_retries} tentativas")
                return {"price": 0, "qty": 0, "status": "Unknown"}
                
            except Exception as e:
                self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Erro ao obter detalhes da ordem (tentativa {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                    
        return {"price": 0, "qty": 0, "status": "Unknown"}