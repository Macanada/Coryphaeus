# main.py
import asyncio
import os
import logging
import json
import sys
from datetime import datetime
from decimal import Decimal, getcontext, ROUND_DOWN
from typing import Dict
from api_rest import BybitRestClient
from websocket_monitor import BybitWebSocketMonitor
from menu import get_strategy_config

# Configura a precisão global para Decimal
getcontext().prec = 28

# Configuração do logging
main_file_name = os.path.splitext(os.path.basename(__file__))[0]
logging.basicConfig(level=logging.INFO, format='%(message)s', encoding='utf-8')  # Remove %(asctime)s
trade_logger = logging.getLogger('trade_log')
trade_logger.setLevel(logging.INFO)
trade_handler = logging.FileHandler(f'{main_file_name}_trade_log.txt', encoding='utf-8')
trade_formatter = logging.Formatter('%(message)s')  # No timestamp
trade_handler.setFormatter(trade_formatter)
trade_logger.addHandler(trade_handler)
error_logger = logging.getLogger('error_log')
error_handler = logging.FileHandler(f'{main_file_name}_error_log.txt', encoding='utf-8')
error_handler.setLevel(logging.DEBUG)
error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s\n%(exc_info)s')
error_handler.setFormatter(error_formatter)
error_logger.addHandler(error_handler)

class TradeLoggerWriter:
    def write(self, message):
        if message.strip():
            trade_logger.info(message.strip())  # Strip to avoid extra newlines
    def flush(self):
        pass
sys.stdout = TradeLoggerWriter()

class BybitTrader:
    def __init__(self, **config):
        self.logger = trade_logger
        self.error_logger = error_logger
        self.logger.info(f"\n{'='*50}\n🚀 Iniciando nova execução em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*50}\n")

        # Initialize modules
        self.rest_client = BybitRestClient(config, trade_logger, error_logger)
        self.ws_monitor = BybitWebSocketMonitor(self, config, trade_logger, error_logger)
        
        # Configuração do saldo limite
        self.saldo_limite = config['saldo_limite']
        self.fee = config['fee'] if config['fee'] is not None else 0.001
        trade_logger.info(f"\n💹 Taxa de transação configurada: {self.fee * 100:.3f}% {'(sem taxa)' if self.fee == 0 else ''}\n📈 Limite de saldo para operações configurado: {self.saldo_limite:.2f} USDT {('(saldo total)' if self.saldo_limite == 0 else '')}")

        # State
        self.active_orders = {}
        self.btc_balance = Decimal('0.0')
        self.usdt_balance = Decimal('0.0')
        self.order_event = asyncio.Event()
        self.running = True
        self.stop_after_sell = False

        # Parametros de inicialização
        self.qty_initial = Decimal(str(config['qty_initial']))
        self.qty_min = Decimal(str(config['qty_min']))
        self.qty_max = Decimal(str(config['qty_max']))
        self.qty_multiplier = Decimal(str(config['qty_multiplier']))

        # Parâmetros de lucro
        self.profit_target = Decimal(str(config['profit_target']))
        self.profit_target_min = Decimal(str(config['profit_target_min']))
        self.profit_target_max = Decimal(str(config['profit_target_max']))
        self.profit_target_multiplier = Decimal(str(config['profit_target_multiplier']))
        self.current_profit_target = Decimal(str(config['profit_target']))

        # Parâmetros de recompra
        self.rebuy_percent = config['rebuy_percent']
        self.rebuy_drop_min = config['rebuy_drop_min']
        self.rebuy_drop_max = config['rebuy_drop_max']
        self.rebuy_multiplier = config['rebuy_multiplier']
        self.current_rebuy_drop = self.rebuy_percent
        self.rebuys_max = config['rebuys_max']

        # Parametros do ciclo
        self.cycle_id = 0
        self.cycle_buys = []
        self.rebuy_count = 0

        # Parametros da ordem atual
        self.current_sell_id = None
        self.current_rebuy_id = None

        # Parametros de lucro
        self.profit_per_cycle = Decimal('0.0')
        self.total_profit = Decimal('0.0')
        self.profit_reaplicar = config['profit_reaplicar'].lower()
        self.profit_distribution_orders = config['profit_distribution_orders']
        self.last_cycle_profit = Decimal('0.0')
        self.profit_to_add_per_order = Decimal('0.0')
        self.profit_orders_remaining = 0
        trade_logger.info(f"💸 Configuração de reaplicação de lucro: {'Ativada' if self.profit_reaplicar == 's' else 'Desativada'}, Ordens de distribuição: {self.profit_distribution_orders}")

        # Configuração de salvamento da estratégia
        self.save_strategy = config['save_strategy'].lower()
        trade_logger.info(f"💾 Configuração de salvamento da estratégia: {'Ativada' if self.save_strategy == 's' else 'Desativada'}")
        self.total_investido = Decimal('0.0')

        # Novas variáveis para controlar pausa por saldo insuficiente
        self.paused_for_insufficient_balance = False
        self.pending_rebuy_price = None
        self.pending_rebuy_qty = None

        # Salvar estratégia se configurado
        if self.save_strategy == 's':
            self._save_strategy_to_json()

    def _save_strategy_to_json(self):
        strategy_config = {
            "qty_initial": float(self.qty_initial),
            "qty_min": float(self.qty_min),
            "qty_max": float(self.qty_max),
            "qty_multiplier": float(self.qty_multiplier),
            "profit_target": float(self.profit_target * 100),
            "profit_target_min": float(self.profit_target_min * 100),
            "profit_target_max": float(self.profit_target_max * 100),
            "profit_target_multiplier": float(self.profit_target_multiplier),
            "rebuy_percent": float(self.rebuy_percent * 100),
            "rebuy_drop_min": float(self.rebuy_drop_min * 100),
            "rebuy_drop_max": float(self.rebuy_drop_max * 100),
            "rebuy_multiplier": float(self.rebuy_multiplier),
            "rebuys_max": self.rebuys_max,
            "fee": float(self.fee * 100),
            "saldo_limite": float(self.saldo_limite),
            "profit_reaplicar": self.profit_reaplicar,
            "profit_distribution_orders": self.profit_distribution_orders,
            "save_strategy": self.save_strategy
        }
        try:
            with open(f'{main_file_name}_strategy.json', 'w', encoding='utf-8') as f:
                json.dump(strategy_config, f, indent=4, ensure_ascii=False)
            self.logger.info(f"💾 Estratégia salva com sucesso em {main_file_name}_strategy.json")
        except Exception as e:
            self.error_logger.error(f"⚠️ Falha ao salvar estratégia em JSON: {e}")

    def _calculate_cycle_profit(self, sell_details: Dict):
        total_usdt_invested = sum(b["price"] * b["qty"] * (1 + self.fee) for b in self.cycle_buys)
        total_btc_sold = sum(b["qty"] * (1 - self.fee) for b in self.cycle_buys)
        sell_price = Decimal(str(sell_details["price"]))
        sell_qty = Decimal(str(sell_details["qty"]))
        total_usdt_received = sell_price * sell_qty * (1 - self.fee)
        self.profit_per_cycle = total_usdt_received - total_usdt_invested
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📊 Calculando lucro: Investido {total_usdt_invested:.2f} USDT, Recebido {total_usdt_received:.2f} USDT, BTC vendido {total_btc_sold:.6f}")
        self.total_profit += self.profit_per_cycle
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💵 Lucro do ciclo #{self.cycle_id}: {self.profit_per_cycle:.2f} USDT")
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💵 Lucro total acumulado: {self.total_profit:.2f} USDT\n")

    def _distribute_profit(self):
        if self.profit_reaplicar != 's' or self.total_profit <= 0:  # Use total_profit
            self.profit_to_add_per_order = Decimal('0.0')
            self.profit_orders_remaining = 0
            return
        num_orders = min(self.profit_distribution_orders, self.rebuys_max + 1)
        self.profit_to_add_per_order = self.total_profit / Decimal(str(num_orders))  # Use total_profit
        self.profit_orders_remaining = num_orders
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📈 Lucro de {self.total_profit:.2f} USDT distribuído em {num_orders} ordens: {self.profit_to_add_per_order:.2f} USDT por ordem")

    def _calculate_qty(self, side: str, qty: str, is_rebuy: bool = False) -> Decimal:
        initial_qty_usdt = Decimal(str(qty))
        if side.lower() == "buy":
            if is_rebuy and len(self.cycle_buys) > 0:
                last_buy_usd_qty = Decimal(str(self.cycle_buys[-1]["price"])) * Decimal(str(self.cycle_buys[-1]["qty"]))
                calculated_qty_usdt = last_buy_usd_qty * self.qty_multiplier
            else:
                calculated_qty_usdt = initial_qty_usdt
            if self.profit_reaplicar == 's' and self.profit_orders_remaining > 0 and self.profit_to_add_per_order > 0:
                calculated_qty_usdt += self.profit_to_add_per_order
                self.profit_orders_remaining -= 1
                self.logger.info(f"💸 Adicionando {self.profit_to_add_per_order:.2f} USDT de lucro reinvestido. Ordens restantes: {self.profit_orders_remaining}")
            actual_qty_usdt = max(self.qty_min, min(calculated_qty_usdt, self.qty_max))
            actual_qty_usdt = actual_qty_usdt.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            self.logger.info(
                f"🔄 Calculando qty para {'recompra' if is_rebuy else 'compra inicial'}: base {initial_qty_usdt:.2f} USDT, calculado {calculated_qty_usdt:.2f} USDT, final {actual_qty_usdt:.2f} USDT (min: {self.qty_min}, max: {self.qty_max})")
            return actual_qty_usdt
        elif side.lower() == "sell":
            return Decimal(str(qty))
        return Decimal('0')

    def _update_rebuy_parameters(self):
        self.rebuy_count += 1
        self.current_rebuy_drop *= self.rebuy_multiplier
        self.current_rebuy_drop = max(self.rebuy_drop_min, min(self.current_rebuy_drop, self.rebuy_drop_max))
        self.logger.info(
            f"📉 Nova queda necessária para recompra: {self.current_rebuy_drop * 100:.2f}% (min: {self.rebuy_drop_min * 100:.2f}%, max: {self.rebuy_drop_max * 100:.2f}%)\n")

    async def on_sell_filled(self):
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🎉 Venda {self.current_sell_id} preenchida! Finalizando ciclo #{self.cycle_id}...\n")
        if self.current_rebuy_id:
            await self.rest_client.cancel_order(self.current_rebuy_id)
            self.current_rebuy_id = None
        sell_details = self.rest_client.get_order_details(self.current_sell_id)
        self._calculate_cycle_profit(sell_details)
        self.last_cycle_profit = self.profit_per_cycle
        self._distribute_profit()
        
        # Resetar para próximo ciclo
        self.cycle_buys = []
        self.current_sell_id = None
        self.total_investido = Decimal('0.0')
        self.rebuy_count = 0
        self.current_rebuy_drop = self.rebuy_percent
        self.current_profit_target = self.profit_target
        
        # Resetar estado de pausa por saldo insuficiente
        if self.paused_for_insufficient_balance:
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔓 Saindo da pausa - venda preenchida (Gatilho 1)")
            self.paused_for_insufficient_balance = False
            self.pending_rebuy_price = None
            self.pending_rebuy_qty = None
        
        # Verificar se deve parar ou continuar
        if self.stop_after_sell:
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🛑 Ordem de parada após venda executada. Encerrando o bot...")
            self.running = False
        else:
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Preparando para iniciar novo ciclo...")
            # O order_event.set() fará o loop principal continuar e iniciar novo ciclo
        
        self.order_event.set()

    async def on_rebuy_filled(self, order: Dict):
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Recompra {self.current_rebuy_id} preenchida no ciclo #{self.cycle_id}!")
        if self.current_sell_id:
            await self.rest_client.cancel_order(self.current_sell_id)
            self.current_sell_id = None
        rebuy_details = self.rest_client.get_order_details(order['orderId'])
        if rebuy_details["qty"] == Decimal('0'):
            self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Quantidade da recompra {order['orderId']} inválida! Abortando ciclo #{self.cycle_id}...\n")
            self.order_event.set()
            return
        self.cycle_buys.append({
            "price": rebuy_details["price"],
            "qty": rebuy_details["qty"],
            "order_id": order['orderId'],
            "cycle_id": self.cycle_id
        })
        self.total_investido = sum(b["price"] * b["qty"] for b in self.cycle_buys)
        rebuy_count = len(self.cycle_buys) - 1
        self._update_rebuy_parameters()
        if self.rebuys_max > 0 and rebuy_count >= self.rebuys_max:
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Limite de recompras ({self.rebuys_max}) atingido no ciclo #{self.cycle_id}! Aguardando venda...")
            await self._place_sell_order_after_rebuy()
        else:
            if not await self._place_sell_order_after_rebuy():
                self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao criar ordem de venda! Abortando ciclo #{self.cycle_id}...\n")
                self.order_event.set()
                return
            if not await self._place_rebuy_order_after_rebuy():
                self.error_logger.error(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao criar ordem de recompra! Abortando ciclo #{self.cycle_id}...\n")
                self.order_event.set()
                return
        btc_balance, usdt_balance, success = self.rest_client.get_balances()
        if success:
            self.btc_balance = btc_balance
            self.usdt_balance = usdt_balance
            # self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💰 Saldos Atuais:\nBTC: {self.btc_balance:.8f}\nUSDT: {self.usdt_balance:.2f}\n")
        self.logger.info(f"🔄 Continuando monitoramento do ciclo #{self.cycle_id}...\n")  # No timestamp
        self.logger.info(f"DEBUG: self.rebuys_max = {self.rebuys_max}, rebuy_count = {rebuy_count}\n")

    async def try_execute_pending_rebuy(self) -> bool:
        """Tenta executar uma recompra pendente quando há saldo suficiente"""
        if not self.paused_for_insufficient_balance or not self.pending_rebuy_price or not self.pending_rebuy_qty:
            return False
            
        # Verificar se agora há saldo suficiente
        btc_balance, usdt_balance, success = self.rest_client.get_balances()
        if not success:
            return False
            
        self.usdt_balance = usdt_balance
        if self.usdt_balance >= self.pending_rebuy_qty:
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔓 Saindo da pausa - saldo suficiente detectado (Gatilho 2)")
            self.logger.info(f"💰 Saldo atual: {self.usdt_balance:.2f} USDT >= {self.pending_rebuy_qty:.2f} USDT necessários")
            
            # Tentar executar a recompra pendente
            self.current_rebuy_id = self.rest_client.place_order("Buy", str(self.pending_rebuy_qty), "Limit", str(int(self.pending_rebuy_price)), self.fee)
            
            if self.current_rebuy_id:
                self.active_orders[self.current_rebuy_id] = {"symbol": "BTCUSDT", "side": "Buy"}
                self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Recompra pendente executada! ID: {self.current_rebuy_id}")
                
                # Resetar estado de pausa
                self.paused_for_insufficient_balance = False
                self.pending_rebuy_price = None
                self.pending_rebuy_qty = None
                return True
            else:
                self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Falha ao executar recompra pendente")
                return False
        
        return False

    async def _place_sell_order_after_rebuy(self) -> bool:
        self.logger.info("📈 Iniciando o processo da ordem de venda após recompra...\n")
        total_usdt_invested = sum(b["price"] * b["qty"] for b in self.cycle_buys)
        total_usdt_with_fees = sum(b["price"] * b["qty"] * (1 + self.fee) for b in self.cycle_buys)
        total_btc_received = sum(b["qty"] * (1 - self.fee) for b in self.cycle_buys)
        self.logger.info(f"\n📊 Resumo das compras no ciclo #{self.cycle_id}:")
        for idx, buy in enumerate(self.cycle_buys, 1):
            fee_usdt = (buy['price'] * buy['qty'] * self.fee).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            fee_btc = buy['qty'] * self.fee
            trade_value_usdt = (buy['price'] * buy['qty']).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            self.logger.info(
                f"   Compra {idx}: {buy['qty']:.6f} BTC (Taxa: {fee_btc:.6f} BTC) a {buy['price']:.2f} USDT (Taxa: {fee_usdt:.2f} USDT, Valor: {trade_value_usdt:.2f} USDT)")
        self.logger.info(f"   Total: {total_btc_received:.6f} BTC, {total_usdt_with_fees:.2f} USDT (incluindo taxas)")
        self.logger.info(f"   Taxa total: {total_usdt_with_fees - total_usdt_invested:.2f} USDT")
        if total_btc_received <= 0:
            self.error_logger.error(f"Total BTC zerado! Abortando ciclo #{self.cycle_id}...")
            return False
        avg_price = total_usdt_with_fees / total_btc_received
        self.logger.info(f"📊 Preço médio do ciclo #{self.cycle_id}: {avg_price:.2f} USDT/BTC")
        self.current_profit_target = max(self.profit_target_min,
                                         min(self.current_profit_target * self.profit_target_multiplier,
                                             self.profit_target_max))
        self.logger.info(
            f"🎯 Lucro alvo ajustado para o próximo ciclo: {self.current_profit_target * 100:.2f}% (Min: {self.profit_target_min * 100:.2f}%, Max: {self.profit_target_max * 100:.2f}%)\n")
        sell_price = avg_price * (1 + self.current_profit_target) / (1 - self.fee)
        self.logger.info(f"💰 Taxa de venda estimada: {sell_price * total_btc_received * self.fee:.2f} USDT")
        self.logger.info(
            f"💰 Preço de venda calculado: {sell_price:.2f} USDT/BTC (Preço médio: {avg_price:.2f} + Lucro Alvo: {self.current_profit_target * 100:.2f}%)\n")
        sell_qty = f"{total_btc_received:.6f}"
        self.current_sell_id = self.rest_client.place_order("Sell", sell_qty, "Limit", str(int(sell_price)), self.fee)
        if not self.current_sell_id:
            return False
        self.active_orders[self.current_sell_id] = {"symbol": "BTCUSDT", "side": "Sell"}
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ Aguardando 2 segundos para processar a ordem de venda...\n")
        await asyncio.sleep(2)
        return True

    async def _place_rebuy_order_after_rebuy(self) -> bool:
        self.logger.info("🔄 Iniciando o processo da ordem de recompra após recompra...\n")
        last_buy_price = self.cycle_buys[-1]["price"]
        rebuy_price = last_buy_price * (1 - self.current_rebuy_drop)
        qty = self._calculate_qty("Buy", str(self.qty_initial), is_rebuy=True)
        
        # Verificar se há saldo suficiente antes de tentar a ordem
        btc_balance, usdt_balance, success = self.rest_client.get_balances()
        if success:
            self.usdt_balance = usdt_balance
            if self.usdt_balance < qty:
                self.logger.info(f"🔄 Saldo insuficiente para recompra ({self.usdt_balance:.2f} < {qty:.2f} USDT). Pausando ciclo e aguardando gatilhos...")
                # Ativar modo de pausa e salvar parâmetros da recompra pendente
                self.paused_for_insufficient_balance = True
                self.pending_rebuy_price = rebuy_price
                self.pending_rebuy_qty = qty
                return True  # Não abortar, apenas pausar
        
        self.current_rebuy_id = self.rest_client.place_order("Buy", str(qty), "Limit", str(int(rebuy_price)), self.fee)
        if not self.current_rebuy_id:
            # Em vez de retornar False (que abortaria), aguardar e tentar novamente
            self.logger.info("🔄 Falha na ordem de recompra. Aguardando para tentar novamente...")
            return True
        
        self.active_orders[self.current_rebuy_id] = {"symbol": "BTCUSDT", "side": "Buy"}
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ Aguardando 2 segundos para processar a ordem de recompra...\n")
        await asyncio.sleep(2)
        return True

    async def _execute_initial_buy(self) -> Dict | None:
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🛒 Iniciando o processo da ordem de compra inicial...\n")
        qty = self._calculate_qty("Buy", str(self.qty_initial))
        buy_id = self.rest_client.place_order("Buy", str(qty), "Market", None, self.fee)
        if not buy_id:
            self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao criar ordem de compra inicial.\n")
            return None
        self.active_orders[buy_id] = {"symbol": "BTCUSDT", "side": "Buy"}
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ Aguardando 8 segundos para processar a compra inicial...\n")
        await asyncio.sleep(8)  # Aumentado de 5 para 8 segundos
        buy_details = self.rest_client.get_order_details(buy_id)
        if buy_details["qty"] == Decimal('0'):
            self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Detalhes da compra inicial inválidos.\n")
            return None
        self.cycle_buys.append({
            "price": buy_details["price"],
            "qty": buy_details["qty"],
            "order_id": buy_id,
            "cycle_id": self.cycle_id
        })
        self.total_investido = Decimal(str(buy_details["price"])) * Decimal(str(buy_details["qty"]))
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📊 Compra inicial do ciclo #{self.cycle_id} a {buy_details['price']:.2f} USDT/BTC, Qty: {buy_details['qty']:.6f} BTC\n")
        return buy_details

    async def _place_sell_order(self, buy_details: Dict) -> bool:
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📈 Iniciando o processo da ordem de venda...\n")
        sell_price = Decimal(str(buy_details["price"])) * (Decimal('1') + self.profit_target) / (Decimal('1') - self.fee)
        sell_qty_btc = f"{buy_details['qty']:.6f}"
        self.current_sell_id = self.rest_client.place_order("Sell", sell_qty_btc, "Limit", str(int(sell_price)), self.fee)
        if not self.current_sell_id:
            return False
        self.active_orders[self.current_sell_id] = {"symbol": "BTCUSDT", "side": "Sell"}
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ Aguardando 2 segundos para processar a ordem de venda...\n")
        await asyncio.sleep(2)
        return True

    async def _place_rebuy_order(self, buy_details: Dict) -> bool:
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Iniciando o processo da ordem de recompra...\n")
        rebuy_price = Decimal(str(buy_details["price"])) * (Decimal('1') - self.rebuy_percent)
        qty = self._calculate_qty("Buy", str(self.qty_initial), is_rebuy=True)
        self.current_rebuy_id = self.rest_client.place_order("Buy", str(qty), "Limit", str(int(rebuy_price)), self.fee)
        if not self.current_rebuy_id:
            return False
        self.active_orders[self.current_rebuy_id] = {"symbol": "BTCUSDT", "side": "Buy"}
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ Aguardando 2 segundos para processar a ordem de recompra...\n")
        await asyncio.sleep(2)
        return True

    async def check_stop(self):
        self.logger.info("\nℹ️ Pressione 'q' para parar imediatamente, 's' para parar após a próxima venda...\n")
        while self.running:
            try:
                char = await asyncio.get_event_loop().run_in_executor(None, input)
                char = char.lower().strip()
                if char == 'q':
                    self.running = False
                    self.logger.warning("🛑 Parada imediata solicitada!")
                    await asyncio.sleep(2)
                    if self.current_sell_id:
                        await self.rest_client.cancel_order(self.current_sell_id)
                    if self.current_rebuy_id:
                        await self.rest_client.cancel_order(self.current_rebuy_id)
                    self.order_event.set()
                    break
                elif char == 's':
                    self.stop_after_sell = True
                    self.logger.warning("⏳ Solicitação de parada após a próxima venda recebida.")
            except Exception as e:
                self.error_logger.error(f"⚠️ Erro ao ler input: {e}")
            await asyncio.sleep(0.1)

    async def order_status(self, order=None):
        """Atualiza o status das ordens com base nos eventos do WebSocket"""
        if order:
            self.active_orders.pop(order.get('orderId'), None)
            if order.get('orderStatus') == 'Filled':
                self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Ordem {order.get('orderId')} preenchida")
                
                # Verificar se é uma recompra preenchida
                if order.get('orderId') == self.current_rebuy_id:
                    await self.on_rebuy_filled(order)
                elif order.get('orderId') == self.current_sell_id:
                    await self.on_sell_filled(self)
        else:
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Atualizando status das ordens")

    async def execute_strategy(self):
        self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Iniciando estratégia de trading...\n")
        try:
            self.total_investido = Decimal('0.0')
            self.total_profit = Decimal('0.0')
            self.last_cycle_profit = Decimal('0.0')
            self.profit_to_add_per_order = Decimal('0.0')
            self.profit_orders_remaining = 0
            self.rest_client.sync_server_time()
            await asyncio.sleep(1)
            if not await self.ws_monitor.connect_websocket():
                return
            stop_task = asyncio.create_task(self.check_stop())
            
            # Variáveis para controlar o estado do ciclo atual
            current_cycle_buy_details = None
            retry_sell_order = False
            
            while self.running:
                btc_balance, usdt_balance, success = self.rest_client.get_balances()
                if not success:
                    self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Erro ao obter saldos. Tentando novamente em 5 segundos...\n")
                    await asyncio.sleep(5)
                    continue
                self.btc_balance = btc_balance
                self.usdt_balance = usdt_balance
                if self.usdt_balance < self.qty_initial:
                    self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Saldo insuficiente pra iniciar ciclo ({self.usdt_balance:.2f} < {self.qty_initial:.2f} USDT)! Aguardando...\n")
                    await asyncio.sleep(5)  # Reduzido para 5 segundos
                    continue
                if self.saldo_limite > 0 and self.total_investido >= self.saldo_limite:
                    self.logger.info(f"⚠️ Limite de saldo atingido ({self.saldo_limite:.2f} USDT). Aguardando venda para continuar...\n")
                    await self.ws_monitor.monitor_cycle()
                    continue
                
                # Verificar se precisamos tentar novamente a ordem de venda do ciclo atual
                if retry_sell_order and current_cycle_buy_details:
                    self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Tentando novamente a ordem de venda para o ciclo #{self.cycle_id}\n")
                    if await self._place_sell_order(current_cycle_buy_details):
                        retry_sell_order = False
                        current_cycle_buy_details = None
                        if not await self._place_rebuy_order(current_cycle_buy_details):
                            self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao criar ordem de recompra inicial. Tentando novamente em 5 segundos...\n")
                            await asyncio.sleep(5)
                        else:
                            await self.ws_monitor.monitor_cycle()
                    else:
                        self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao criar ordem de venda novamente. Tentando em 5 segundos...\n")
                        await asyncio.sleep(5)
                    continue
                        
                if not self.current_sell_id and not self.current_rebuy_id and not self.stop_after_sell:
                    self.cycle_id += 1
                    self.current_rebuy_drop = self.rebuy_percent
                    self.current_profit_target = self.profit_target
                    self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 Iniciando novo ciclo principal #{self.cycle_id}\n")
                    buy_details = await self._execute_initial_buy()
                    if not buy_details or buy_details["qty"] == Decimal('0'):
                        self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Compra inicial falhou! Tentando novamente...\n")
                        await asyncio.sleep(5)
                        continue
                            
                    # Salvar os detalhes da compra para possível retry
                    current_cycle_buy_details = buy_details
                        
                    if not await self._place_sell_order(buy_details):
                        self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao criar ordem de venda inicial. Tentando novamente em 5 segundos...\n")
                        retry_sell_order = True  # Marcar para tentar novamente a ordem de venda
                        await asyncio.sleep(5)
                        continue
                    if not await self._place_rebuy_order(buy_details):
                        self.error_logger.warning(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Falha ao criar ordem de recompra inicial. Tentando novamente em 5 segundos...\n")
                        await asyncio.sleep(5)
                        continue
                    await self.ws_monitor.monitor_cycle()
                else:
                    await self.ws_monitor.monitor_cycle()
            stop_task.cancel()
        except Exception as e:
            self.error_logger.error(f"Erro crítico na estratégia: {str(e)}\n")
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💵 Lucro total acumulado: {self.total_profit:.2f} USDT\n")
        finally:
            if self.current_sell_id and await self.rest_client.cancel_order(self.current_sell_id):
                self.current_sell_id = None
            if self.current_rebuy_id and await self.rest_client.cancel_order(self.current_rebuy_id):
                self.current_rebuy_id = None
            if self.ws_monitor.ws_connected:
                await self.ws_monitor.ws.close()
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔌 Conexão WebSocket encerrada")
            self.logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💵 Lucro total acumulado: {self.total_profit:.2f} USDT\n")

if __name__ == "__main__":
    config = get_strategy_config(trade_logger)
    trader = BybitTrader(**config)
    asyncio.run(trader.execute_strategy())

# Criar diretórios de logs se não existirem
os.makedirs('log_error', exist_ok=True)
os.makedirs('user/logs_traders', exist_ok=True)

# Configuração do logging com timestamps para nomes de arquivos
timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(message)s', encoding='utf-8')
trade_logger = logging.getLogger('trade_log')
trade_logger.setLevel(logging.INFO)

# Log de operações no diretório específico
trade_handler = logging.FileHandler(f'user/logs_traders/{config.get("exchange", "Exchange")}_{config.get("symbol", "Pair")}_{timestamp}_trade.log', encoding='utf-8')
trade_formatter = logging.Formatter('%(message)s')
trade_handler.setFormatter(trade_formatter)
trade_logger.addHandler(trade_handler)

# Log de erros no diretório específico
error_logger = logging.getLogger('error_log')
error_handler = logging.FileHandler(f'log_error/{timestamp}_error.log', encoding='utf-8')
error_handler.setLevel(logging.DEBUG)
error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s\n%(exc_info)s')
error_handler.setFormatter(error_formatter)
error_logger.addHandler(error_handler)