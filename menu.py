import os
import json
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from cryptography.fernet import Fernet
import time
import re
from getpass import getpass
from api_rest import BybitRestClient
from typing import Dict

def listar_estrategias_salvas() -> list:
    """Lista todos os arquivos JSON de estratégias na pasta user/strategy."""
    arquivos = []
    strategy_dir = 'user/strategy'
    
    # Criar diretório se não existir
    if not os.path.exists(strategy_dir):
        os.makedirs(strategy_dir)
        return arquivos
    
    for arquivo in os.listdir(strategy_dir):
        if (arquivo.startswith('strategy_') and arquivo.endswith('.json')) or (arquivo.endswith('_strategy.json')):
            arquivos.append(os.path.join(strategy_dir, arquivo))
    return arquivos

def carregar_estrategia_de_arquivo(arquivo: str) -> dict:
    """Carrega uma estratégia de um arquivo JSON."""
    try:
        with open(arquivo, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Convert percentages and other values to Decimal
            config['profit_target'] = Decimal(str(config['profit_target'])) / Decimal('100')
            config['profit_target_min'] = Decimal(str(config['profit_target_min'])) / Decimal('100')
            config['profit_target_max'] = Decimal(str(config['profit_target_max'])) / Decimal('100')
            config['rebuy_percent'] = Decimal(str(config['rebuy_percent'])) / Decimal('100')
            config['rebuy_drop_min'] = Decimal(str(config['rebuy_drop_min'])) / Decimal('100')
            config['rebuy_drop_max'] = Decimal(str(config['rebuy_drop_max'])) / Decimal('100')
            config['fee'] = Decimal(str(config['fee'])) / Decimal('100')
            config['qty_initial'] = Decimal(str(config['qty_initial']))
            config['qty_min'] = Decimal(str(config['qty_min']))
            config['qty_max'] = Decimal(str(config['qty_max']))
            config['qty_multiplier'] = Decimal(str(config['qty_multiplier']))
            config['rebuy_multiplier'] = Decimal(str(config['rebuy_multiplier']))
            return config
    except Exception as e:
        print(f"⚠️ Erro ao carregar arquivo: {e}")
        return None

def save_api_keys(api_key: str, api_secret: str, memorize: str) -> bool:
    """Salva as chaves API criptografadas se memorize for 's'."""
    if memorize.lower() != 's':
        return False
    try:
        key = Fernet.generate_key()
        fernet = Fernet(key)
        encrypted_key = fernet.encrypt(api_key.encode('utf-8'))
        encrypted_secret = fernet.encrypt(api_secret.encode('utf-8'))
        with open('api_keys.json', 'w', encoding='utf-8') as f:
            json.dump({
                'encryption_key': key.decode('utf-8'),
                'api_key': encrypted_key.decode('utf-8'),
                'api_secret': encrypted_secret.decode('utf-8')
            }, f)
        return True
    except Exception as e:
        print(f"⚠ Erro ao salvar chaves API: {e}")
        return False

def load_api_keys() -> tuple[str, str]:
    """Carrega as chaves API criptografadas."""
    try:
        with open('api_keys.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        fernet = Fernet(data['encryption_key'].encode('utf-8'))
        api_key = fernet.decrypt(data['api_key'].encode('utf-8')).decode('utf-8')
        api_secret = fernet.decrypt(data['api_secret'].encode('utf-8')).decode('utf-8')
        return api_key, api_secret
    except Exception:
        return None, None

def calculate_required_balance(config: dict) -> Decimal:
    """Calcula o saldo necessário para a estratégia."""
    qty_initial = Decimal(str(config['qty_initial']))
    qty_max = Decimal(str(config['qty_max']))
    fee = Decimal(str(config['fee']))
    rebuys_max = config['rebuys_max']
    qty_multiplier = Decimal(str(config['qty_multiplier']))
    
    total_qty = qty_initial
    current_qty = qty_initial
    for _ in range(rebuys_max if rebuys_max > 0 else 45):  # Default to 45 if unlimited
        current_qty *= qty_multiplier
        current_qty = min(current_qty, qty_max)
        total_qty += current_qty
    total_qty_with_fees = total_qty * (1 + fee)
    return total_qty_with_fees.quantize(Decimal('0.01'))

def get_strategy_config(logger: logging.Logger) -> dict:
    """Configura uma nova estratégia ou carrega uma existente."""
    
    logger.info(
        "atalhos, pressione as seguintes teclas na linha de input para os seguintes comandos:\n"
        "'h' help\n'b' volta para o input anterior\n'r' reinicia o config de estratégia\n"
        "'e' encerra o programa\n'enter' inseri o valor default\n"
    )

    previous_inputs = []
    default_values = {
        'saldo_limite': '0',
        'exchange': 'Bybit Demo',
        'load_api': 'n',
        'api_key': '',
        'api_secret': '',
        'memorize_api': 'n',
        'par': 'BTC/USDT',
        'qty_initial': '100',
        'qty_min': '10',
        'qty_max': '400',
        'qty_multiplier': '1.04',
        'profit_target': '0.3',
        'profit_target_min': '0.1',
        'profit_target_max': '2.0',
        'profit_target_multiplier': '0.97',
        'rebuy_percent': '0.25',
        'rebuy_drop_min': '0.1',
        'rebuy_drop_max': '1.0',
        'rebuy_multiplier': '0.98',
        'rebuys_max': '45',
        'fee': '0.1',
        'profit_reaplicar': 's',
        'profit_distribution_orders': '2',
        'save_strategy': 'n'
    }

    def get_input(prompt: str, help_text: str, error_text: str, default: str = '', validate=None, options: list = None):
        previous_inputs.append((prompt, help_text, error_text, default, validate, options))
        while True:
            user_input = input(prompt).strip()
            if user_input.lower() == 'h':
                print(help_text)
                continue
            if user_input.lower() == 'b' and len(previous_inputs) > 1:
                previous_inputs.pop()  # Remove current input
                prev = previous_inputs.pop()  # Get previous input
                return 'BACK', prev
            if user_input.lower() == 'r':
                logger.info("\n🔁 Reiniciando configuração...")
                return 'RESTART', None
            if user_input.lower() == 'e':
                logger.info("\n🛑 Encerrando programa...")
                exit(0)
            if user_input == '' and default:
                return default
            try:
                if validate:
                    result = validate(user_input)
                    if result is not None:
                        return result
                    else:
                        print(error_text)
                        continue
                if options and user_input.isdigit() and 1 <= int(user_input) <= len(options):
                    return options[int(user_input) - 1]
                return user_input
            except (ValueError, InvalidOperation):
                print(error_text)
                continue

    # Load saved strategies
    estrategias = listar_estrategias_salvas()
    while True:
        prompt = "\n🔹 Carregar Estratégia guardada em arquivo? (s/n): "
        load_strategy = get_input(
            prompt,
            "Digite 's' para carregar uma estratégia salva ou 'n' para criar uma nova.",
            "⚠️ Digite 's' ou 'n'.",
            default='n',
            validate=lambda x: x.lower() if x.lower() in ['s', 'n'] else None
        )
        if load_strategy == 'BACK':
            continue
        if load_strategy == 'RESTART':
            return get_strategy_config(logger)
        if load_strategy.lower() == 's' and estrategias:
            print("\n🔹 Estratégias salvas encontradas:")
            for i, arquivo in enumerate(estrategias, 1):
                print(f"  {i}. {arquivo}")
            escolha = get_input(
                "\n🔹 Escolha uma opção (1-{}): ".format(len(estrategias)),
                "Digite o número da estratégia que deseja carregar.",
                "⚠️ Por favor, digite um número válido.",
                validate=lambda x: int(x) if x.isdigit() and 1 <= int(x) <= len(estrategias) else None
            )
            if escolha == 'BACK':
                continue
            if escolha == 'RESTART':
                return get_strategy_config(logger)
            
            # Corrigir o bug de indexação
            config = carregar_estrategia_de_arquivo(estrategias[escolha - 1])
            if config:
                logger.info(f"\n💾 Estratégia carregada de {estrategias[escolha - 1]}")
                summary = (
                    f"✅ RESUMO DA ESTRATÉGIA CARREGADA:\n"
                    f"• Limite de saldo: {config['saldo_limite']} USDT\n"
                    f"• Exchange: {config.get('exchange', 'Bybit Demo')}\n"
                    f"• Par: {config.get('par', 'BTC/USDT')}\n"
                    f"• Capital inicial por ordem: {config['qty_initial']} USDT\n"
                    f"• Recompra: mín {config['qty_min']}, máx {config['qty_max']} USDT, multiplicador: {config['qty_multiplier']}\n"
                    f"• Lucro alvo: {config['profit_target']*100:.2f}%, mín {config['profit_target_min']*100:.2f}%, máx {config['profit_target_max']*100:.2f}%, multiplicador: {config['profit_target_multiplier']}\n"
                    f"• Recompra a cada queda de: {config['rebuy_percent']*100:.2f}%, mín {config['rebuy_drop_min']*100:.2f}%, máx {config['rebuy_drop_max']*100:.2f}%, multiplicador: {config['rebuy_multiplier']}\n"
                    f"• Máximo de recompras: {'ilimitado' if config['rebuys_max'] == 0 else config['rebuys_max']}\n"
                    f"• Taxa de corretagem: {config['fee']*100:.2f}%\n"
                    f"• Reaplicação de lucro: {'Sim' if config['profit_reaplicar'] == 's' else 'Não'}" +
                    (f", distribuído em {config['profit_distribution_orders']} ordens" if config['profit_reaplicar'] == 's' else "")
                )
                logger.info(summary)
                required_balance = calculate_required_balance(config)
                logger.info(f"💰 Saldo necessário para esta estratégia: {required_balance:.2f} USDT")
                
                # Validate API keys for loaded strategy
                temp_config = {'exchange': config.get('exchange', 'Bybit Demo'), 'api_key': config.get('api_key', ''), 'api_secret': config.get('api_secret', '')}
                client = BybitRestClient(temp_config, logger, logger)
                success, message = client.validate_api_keys()
                if not success:
                    logger.error(f"\n{message}\n⚠️ Chaves API inválidas na estratégia carregada. Por favor, insira novas chaves.")
                    continue
                print(f"\n{message}")
                
                print("\n🔹 Ação desejada:")
                print("  1. Selecionar outra estratégia")
                print("  2. Executar a estratégia")
                print("  3. Editar a estratégia")
                print("  4. Criar nova estratégia")
                print("  5. Sair do programa")
                action = get_input(
                    "\n🔹 Escolha uma opção (1-5): ",
                    "Digite o número da ação desejada.",
                    "⚠️ Por favor, digite um número entre 1 e 5.",
                    validate=lambda x: int(x) if x.isdigit() and 1 <= int(x) <= 5 else None
                )
                if action == 'BACK':
                    continue
                if action == 'RESTART':
                    return get_strategy_config(logger)
                if action == 1:
                    continue
                if action == 2:
                    logger.info("\n🚀 Iniciando operação com a estratégia carregada!\n")
                    return config
                if action == 3:
                    logger.info("\n🔧 Editando estratégia carregada...")
                    break
                if action == 4:
                    break
                if action == 5:
                    logger.info("\n🛑 Encerrando programa...")
                    exit(0)
        else:
            break

    # Exchange selection
    exchanges = ['Bybit Main', 'Bybit Demo', 'Binance Main', 'Binance Testnet', 'Binance Japan']
    while True:
        print("\n🔹 Exchanges disponíveis:")
        for i, exchange in enumerate(exchanges, 1):
            print(f"  {i}. {exchange}")
        exchange = get_input(
            "\n🔹 Exchange: ",
            "Escolha a exchange desejada para realizar operações ou testes (Bybit Main, Bybit Demo, Binance Main, Binance Testnet, Binance Japan). Utilize Bybit Demo para simulações com saldo fictício.",
            "⚠️ Selecione uma exchange válida.",
            default=default_values['exchange'],
            options=exchanges,
            validate=lambda x: exchanges[int(x) - 1] if x.isdigit() and 1 <= int(x) <= len(exchanges) else None
        )
        if exchange == 'BACK':
            if estrategias:
                return 'RESTART', None
            continue
        if exchange == 'RESTART':
            return get_strategy_config(logger)
        if exchange not in ['Bybit Main', 'Bybit Demo']:
            print("\n⚠️ Aviso: Apenas Bybit Main e Bybit Demo são suportados atualmente. Outras exchanges não foram validadas.")
            continue
        break

    # API keys
    api_key, api_secret = None, None
    while True:
        load_api = get_input(
            "\n🔹 Carregar Chaves API? (s/n): ",
            "Digite 's' para carregar chaves API salvas ou 'n' para inserir novas.",
            "⚠️ Digite 's' ou 'n'.",
            default=default_values['load_api'],
            validate=lambda x: x.lower() if x.lower() in ['s', 'n'] else None
        )
        if load_api == 'BACK':
            continue
        if load_api == 'RESTART':
            return get_strategy_config(logger)
        
        if load_api.lower() == 's':
            api_key, api_secret = load_api_keys()
            if api_key and api_secret:
                temp_config = {'exchange': exchange, 'api_key': api_key, 'api_secret': api_secret}
                client = BybitRestClient(temp_config, logger, logger)
                success, message = client.validate_api_keys()
                print(f"\n{message}")
                if success:
                    break
                else:
                    print("⚠️ Não foi possível carregar as chaves API, por favor insira novas chaves.")
            else:
                print("\n⚠️ Não foi possível carregar as chaves API, por favor insira novas chaves.")
        
        while True:
            api_key = get_input(
                "\n🔹 Inserir Chave API pública: ",
                "Insira a chave API pública fornecida pela exchange.",
                "⚠️ Chave API pública inválida.",
                default=default_values['api_key']
            )
            if api_key == 'BACK':
                break
            if api_key == 'RESTART':
                return get_strategy_config(logger)
            
            api_secret = getpass("\n🔹 Inserir Chave API privada: ")
            if api_secret.lower() == 'b':
                continue
            if api_secret.lower() == 'r':
                return get_strategy_config(logger)
            
            temp_config = {'exchange': exchange, 'api_key': api_key, 'api_secret': api_secret}
            client = BybitRestClient(temp_config, logger, logger)
            success, message = client.validate_api_keys()
            print(f"\n{message}")
            if success:
                memorize_api = get_input(
                    "\n🔹 Memorizar chaves API? (s/n): ",
                    "Digite 's' para salvar as chaves API de forma criptografada ou 'n' para não salvar.",
                    "⚠️ Digite 's' ou 'n'.",
                    default=default_values['memorize_api'],
                    validate=lambda x: x.lower() if x.lower() in ['s', 'n'] else None
                )
                if memorize_api == 'BACK':
                    continue
                if memorize_api == 'RESTART':
                    return get_strategy_config(logger)
                if memorize_api.lower() == 's':
                    save_api_keys(api_key, api_secret, memorize_api)
                break
            else:
                continue
        if api_key and api_secret:
            break

    # Trading pair selection
    trading_pairs = {
        'Bybit Main': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
        'Bybit Demo': ['BTC/USDT', 'ETH/USDT'],
        'Binance Mainnet': ['BTC/USDT', 'ETH/BTC', 'BNB/BTC'],
        'Binance Testnet': ['BTC/USDT', 'ETH/USDT'],
        'Binance Japan': ['BTC/JPY', 'ETH/JPY']
    }
    while True:
        print(f"\nAvailable pairs for {exchange}:\n")
        for i, pair in enumerate(trading_pairs[exchange], 1):
            print(f"{i}. {pair}")
        par = get_input(
            "\n🔹 PAR: ",
            f"Informe o par de moedas desejado para operar. Exemplo: BTC/USDT. Verifique se o par está disponível na exchange {exchange}.",
            "⚠️ Par inválido ou não disponível na exchange selecionada.",
            default=default_values['par'],
            options=trading_pairs[exchange],
            validate=lambda x: trading_pairs[exchange][int(x) - 1] if x.isdigit() and 1 <= int(x) <= len(trading_pairs[exchange]) else None
        )
        if par == 'BACK':
            continue
        if par == 'RESTART':
            return get_strategy_config(logger)
        break

    # Order Value
    while True:
        qty_initial = get_input(
            f"\n🔹 Order Value ({par.split('/')[1]}): ",
            f"Valor da Ordem inicial em {par.split('/')[1]} para as operações (ex. {100} {par.split('/')[1]}).",
            f"⚠️ O valor da ordem deve ser maior ou igual ao mínimo permitido pela Exchange (10 {par.split('/')[1]}). Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['qty_initial'],
            validate=lambda x: Decimal(x) if Decimal(x) >= 10 else None
        )
        if qty_initial == 'BACK':
            continue
        if qty_initial == 'RESTART':
            return get_strategy_config(logger)
        qty_initial = Decimal(qty_initial)
        
        qty_min = get_input(
            "\n🔹 Order Value Mínimo: ",
            f"Valor da Ordem Mínima em {par.split('/')[1]} para as operações. O fator multiplicador irá reduzir gradativamente o valor das ordens a partir do Order Value até ao mínimo (ex. {10} {par.split('/')[1]}). ⚠️ Não utilize alert função a menos que você sabe exatamente o que está fazendo, a redução do Order Value pode ocasionar prejuízo irreversível!",
            f"⚠️ Não pode ser superior ao Order Value ({qty_initial}), Não pode ser inferior ao mínimo permitido pela Exchange (10). Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['qty_min'],
            validate=lambda x: Decimal(x) if Decimal(x) <= qty_initial and Decimal(x) >= 10 else None
        )
        if qty_min == 'BACK':
            continue
        if qty_min == 'RESTART':
            return get_strategy_config(logger)
        qty_min = Decimal(qty_min)
        
        qty_max = get_input(
            "\n🔹 Order Value Máximo: ",
            f"Valor da Ordem Máxima em {par.split('/')[1]} para as operações. O fator multiplicador irá ampliar gradativamente o valor das ordens a partir do Order Value até ao máximo (ex. {400} {par.split('/')[1]}).",
            f"⚠️ Não pode ser menor que o valor da ordem ({qty_initial}). Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['qty_max'],
            validate=lambda x: Decimal(x) if Decimal(x) >= qty_initial else None
        )
        if qty_max == 'BACK':
            continue
        if qty_max == 'RESTART':
            return get_strategy_config(logger)
        qty_max = Decimal(qty_max)
        
        qty_multiplier = get_input(
            "\n🔹 Multiplicador do Order Value: ",
            "Define o fator de multiplicação aplicado ao valor base das ordens de recompra dentro de um mesmo ciclo de operação. Esse parâmetro controla a progressão do valor das ordens, permitindo aumentos, reduções ou manutenção constante conforme configurado:\n"
            "Multiplicador > 1.0: incrementar progressivamente o valor das ordens de recompra até o limite definido por Order Value Máximo.\n"
            "Multiplicador = 1.0: desativa a variação, mantendo todas as ordens com o mesmo valor base.\n"
            "Multiplicador < 1.0: reduz gradualmente o valor das ordens até o limite definido por Order Value Mínimo.\n"
            "Essa escala é aplicada apenas dentro do ciclo atual e é reinicializada automaticamente ao início de um novo ciclo.\n"
            "Exemplos: 1.02 (aumenta), 1.00 (mantém), 0.90 (reduz).\n",
            "⚠️ Multiplicador deve ser maior que zero. Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['qty_multiplier'],
            validate=lambda x: Decimal(x) if Decimal(x) > 0 else None
        )
        if qty_multiplier == 'BACK':
            continue
        if qty_multiplier == 'RESTART':
            return get_strategy_config(logger)
        qty_multiplier = Decimal(qty_multiplier)
        break

    # Profit
    while True:
        profit_target = get_input(
            "\n🔹 Lucro: ",
            "Meta de lucro por trade. Ex: 1.5 para 1.5%.",
            "⚠️ O Lucro alvo não pode ser igual a ZERO, no máximo 200%. Não digite o símbolo %, Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['profit_target'],
            validate=lambda x: Decimal(x) / 100 if 0 < Decimal(x) <= 200 else None
        )
        if profit_target == 'BACK':
            continue
        if profit_target == 'RESTART':
            return get_strategy_config(logger)
        profit_target = Decimal(profit_target)
        
        profit_target_min = get_input(
            "\n🔹 Lucro Mínimo: ",
            "O Lucro Mínimo está combinado com o Multiplicador de Lucro e poderá reduzir gradativamente o Lucro até atingir o mínimo. Ex.: 0.5 para 0.5%.",
            f"⚠️ O valor do Lucro Mínimo não pode ser superior ao Lucro ({profit_target*100:.2f}%), Não pode ser ZERO, nem negativo, não pode conter o símbolo %, Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['profit_target_min'],
            validate=lambda x: Decimal(x) / 100 if 0 < Decimal(x) <= profit_target*100 else None
        )
        if profit_target_min == 'BACK':
            continue
        if profit_target_min == 'RESTART':
            return get_strategy_config(logger)
        profit_target_min = Decimal(profit_target_min)
        
        profit_target_max = get_input(
            "\n🔹 Lucro Máximo: ",
            "O Lucro Máximo está combinado com o Multiplicador de Lucro e poderá aumentar gradativamente o Lucro até atingir o Máximo. Ex.: 8.5 para 8.5%.",
            f"⚠️ O valor do Lucro Máximo não pode ser inferior ao Lucro ({profit_target*100:.2f}%) até no máximo 200%. Não pode ser ZERO, nem negativo, não pode conter o símbolo %, Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['profit_target_max'],
            validate=lambda x: Decimal(x) / 100 if profit_target*100 <= Decimal(x) <= 200 else None
        )
        if profit_target_max == 'BACK':
            continue
        if profit_target_max == 'RESTART':
            return get_strategy_config(logger)
        profit_target_max = Decimal(profit_target_max)
        
        profit_target_multiplier = get_input(
            "\n🔹 Multiplicador do Lucro: ",
            "Define o fator de multiplicação aplicado ao percentual de lucro alvo (Target Profit) para ordens de venda dentro de um mesmo ciclo. Esse parâmetro ajusta gradualmente o lucro com base no número de recompras realizadas:\n"
            "Multiplicador < 1.0: reduz o lucro progressivamente a cada recompra, favorecendo a finalização do ciclo mais rapidamente — útil em cenários de mercado em queda.\n"
            "Multiplicador > 1.0: aumenta gradualmente o lucro a cada recompra, mantendo o alvo de venda em uma faixa superior — pode ser útil em mercados voláteis com perspectiva de recuperação (não recomendado para ativos altamente instáveis, como memecoins).\n"
            "Multiplicador = 1.0: desativa o ajuste, mantendo o mesmo percentual de lucro em todas as ordens.\n"
            "Exemplos:\nLucro inicial: 10%, Multiplicador: 0.98 → lucro reduzido a cada recompra.\n"
            "Lucro inicial: 10%, Multiplicador: 1.04 → lucro aumentado a cada recompra.\n"
            "Multiplicador: 1.00 → lucro constante em todas as ordens.\n"
            "O efeito é reiniciado a cada novo ciclo.\n",
            "⚠️ Multiplicador deve ser maior que zero. Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['profit_target_multiplier'],
            validate=lambda x: Decimal(x) if Decimal(x) > 0 else None
        )
        if profit_target_multiplier == 'BACK':
            continue
        if profit_target_multiplier == 'RESTART':
            return get_strategy_config(logger)
        profit_target_multiplier = Decimal(profit_target_multiplier)
        break

    # Rebuys
    while True:
        rebuy_percent = get_input(
            "\n🔹 Diferença Percentual entre os Preços de compra: ",
            "Percentual de queda no preço para realizar uma nova recompra. Ex.: 0.5 para 0.5%.",
            "⚠️ O valor percentual deve ser superior a 0 e inferior a 100%. Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['rebuy_percent'],
            validate=lambda x: Decimal(x) / 100 if 0 < Decimal(x) < 100 else None
        )
        if rebuy_percent == 'BACK':
            continue
        if rebuy_percent == 'RESTART':
            return get_strategy_config(logger)
        rebuy_percent = Decimal(rebuy_percent)
        
        rebuy_drop_min = get_input(
            "\n🔹 Diferença Percentual Mínima entre os Preços de compra: ",
            "Percentual mínimo de queda para realizar uma recompra. Ex.: 0.3 para 0.3%.",
            f"⚠️ O valor da Diferença Percentual Mínima não pode ser superior ao Valor da Diferença Percentual ({rebuy_percent*100:.2f}%), e deve ser superior a ZERO. Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['rebuy_drop_min'],
            validate=lambda x: Decimal(x) / 100 if 0 < Decimal(x) <= rebuy_percent*100 else None
        )
        if rebuy_drop_min == 'BACK':
            continue
        if rebuy_drop_min == 'RESTART':
            return get_strategy_config(logger)
        rebuy_drop_min = Decimal(rebuy_drop_min)
        
        rebuy_drop_max = get_input(
            "\n🔹 Diferença Percentual Máxima entre os Preços de compra: ",
            "Percentual máximo de queda para realizar uma recompra. Ex.: 1.5 para 1.5%.",
            f"⚠️ O valor da Diferença Percentual Máxima não pode ser inferior ao valor da Diferença Percentual ({rebuy_percent*100:.2f}%). Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['rebuy_drop_max'],
            validate=lambda x: Decimal(x) / 100 if Decimal(x) >= rebuy_percent*100 else None
        )
        if rebuy_drop_max == 'BACK':
            continue
        if rebuy_drop_max == 'RESTART':
            return get_strategy_config(logger)
        rebuy_drop_max = Decimal(rebuy_drop_max)
        
        rebuy_multiplier = get_input(
            "\n🔠 Multiplicador da Diferença Percentual entre os Preços: ",
            "Fator de multiplicação aplicado ao percentual de queda para recompras. Ex.: Multiplicador: 1.3 mantém, 1.2 aumenta, 0.98 multiplica.",
            "⚠️⚠ O valor do Multiplicador deve ser maior que ZERO. Use ponto (.) para decimais, não vírgula nula (,).",
            default=default_values['rebuy_multiplier'],
            validate=lambda x: Decimal(x) if Decimal(x) > 0 else None
        )
        if rebuy_multiplier == 'BACK':
            continue
        if rebuy_multiplier == 'RESTART':
            return get_strategy_config(logger)
        rebuy_multiplier = Decimal(rebuy_multiplier)
        
        rebuys_max = get_input(
            "\n🔹 Número Máximo de Recompras: ",
            "Número máximo de recompras consecutivas permitidas. Exemplo: 0 (zero) permite recompras ilimitadas até 45 ordens.",
            "⚠️ O valor não pode ser negativo.",
            default=default_values['rebuys_max'],
            validate=lambda x: int(x) if x.isdigit() and int(x) >= 0 else None
        )
        if rebuys_max == 'BACK':
            continue
        if rebuys_max == 'RESTART':
            return get_strategy_config(logger)
        rebuys_max = int(rebuys_max)
        break

    # Fees
    while True:
        fee = get_input(
            "\n🔹 Taxas: ",
            "Informe as taxas cobradas pela Exchange em operações do tipo Maker (ordem limite) e Taker (ordem a mercado). Pode ser 0 em pares com zero fee. Exemplo: 0.1",
            "⚠️ Valor inválido. Use um percentual positivo ou zero. Não digite o símbolo %. Use ponto (.) para decimais, não vírgula (,).",
            default=default_values['fee'],
            validate=lambda x: Decimal(x) / 100 if Decimal(x) >= 0 else None
        )
        if fee == 'BACK':
            continue
        if fee == 'RESTART':
            return get_strategy_config(logger)
        fee = Decimal(fee)
        break

    # Balance limit
    while True:
        saldo_limite = get_input(
            f"\n🔹 Limitar Saldo para Estratégia em {par.split('/')[1]}: ",
            f"Limitador do Saldo para a estratégia. O valor deve ser inteiro, positivo e superior ao valor mínimo do PAR de trade válido definido pela Exchange. 0 (ZERO) representa sem limites de Saldo para essa estratégia.",
            "⚠️ Insira um valor válido! Use ponto (.) para decimais, não vírgula (,). Pressione h e enter para ajuda!",
            default=default_values['saldo_limite'],
            validate=lambda x: float(x) if float(x) >= 0 else None
        )
        if saldo_limite == 'BACK':
            continue
        if saldo_limite == 'RESTART':
            return get_strategy_config(logger)
        saldo_limite = float(saldo_limite)
        break

    # Profit reapplication
    while True:
        profit_reaplicar = get_input(
            "\n🔹 Reaplicar lucro nas próximas ordens de compra? (s/n): ",
            "Digite 's' para reaplicar o lucro nas próximas ordens de compra ou 'n' para não reaplicar.",
            "⚠️ Digite 's' ou 'n'.",
            default=default_values['profit_reaplicar'],
            validate=lambda x: x.lower() if x.lower() in ['s', 'n'] else None
        )
        if profit_reaplicar == 'BACK':
            continue
        if profit_reaplicar == 'RESTART':
            return get_strategy_config(logger)
        
        profit_distribution_orders = 0
        if profit_reaplicar.lower() == 's':
            profit_distribution_orders = get_input(
                "\n🔹 Em quantas ordens dividir o lucro reaplicado? (Número inteiro positivo): ",
                "Número de ordens nas quais o lucro será distribuído. Deve ser um número inteiro positivo.",
                f"⚠️ O número de ordens deve ser positivo{' e não pode exceder o máximo de recompras (' + str(rebuys_max) + ') + 1' if rebuys_max > 0 else ''}.",
                default=default_values['profit_distribution_orders'],
                validate=lambda x: int(x) if int(x) > 0 and (rebuys_max == 0 or int(x) <= rebuys_max + 1) else None
            )
            if profit_distribution_orders == 'BACK':
                continue
            if profit_distribution_orders == 'RESTART':
                return get_strategy_config(logger)
            profit_distribution_orders = int(profit_distribution_orders)
        break

    # Create config dictionary
    config = {
        "saldo_limite": saldo_limite,
        "exchange": exchange,
        "par": par,
        "api_key": api_key,
        "api_secret": api_secret,
        "qty_initial": qty_initial,
        "qty_min": qty_min,
        "qty_max": qty_max,
        "qty_multiplier": qty_multiplier,
        "profit_target": profit_target,
        "profit_target_min": profit_target_min,
        "profit_target_max": profit_target_max,
        "profit_target_multiplier": profit_target_multiplier,
        "rebuy_percent": rebuy_percent,
        "rebuys_max": rebuys_max,
        "rebuy_drop_min": rebuy_drop_min,
        "rebuy_drop_max": rebuy_drop_max,
        "rebuy_multiplier": rebuy_multiplier,
        "fee": fee,
        "profit_reaplicar": profit_reaplicar,
        "profit_distribution_orders": profit_distribution_orders,
        "save_strategy": 'n'
    }

    # Calculate and display required balance
    required_balance = calculate_required_balance(config)
    logger.info(f"\n💰 Saldo necessário para esta estratégia: {required_balance:.2f} {par.split('/')[1]}")

    # Display summary
    summary = (
        f"✅ RESUMO DA ESTRATÉGIA CONFIGURADA:\n"
        f"• Limite de saldo: {saldo_limite} {par.split('/')[1]}\n"
        f"• Exchange: {exchange}\n"
        f"• Par: {par}\n"
        f"• Capital inicial por ordem: {qty_initial} {par.split('/')[1]}\n"
        f"• Recompra: mín {qty_min}, máx {qty_max} {par.split('/')[1]}, multiplicador: {qty_multiplier}\n"
        f"• Lucro alvo: {profit_target*100:.2f}%, mín {profit_target_min*100:.2f}%, máx {profit_target_max*100:.2f}%, multiplicador: {profit_target_multiplier}\n"
        f"• Recompra a cada queda de: {rebuy_percent*100:.2f}%, mín {rebuy_drop_min*100:.2f}%, máx {rebuy_drop_max*100:.2f}%, multiplicador: {rebuy_multiplier}\n"
        f"• Máximo de recompras: {'ilimitado' if rebuys_max == 0 else rebuys_max}\n"
        f"• Taxa de corretagem: {fee*100:.2f}%\n"
        f"• Reaplicação de lucro: {'Sim' if profit_reaplicar == 's' else 'Não'}" +
        (f", distribuída em {profit_distribution_orders} ordens" if profit_reaplicar == 's' else "")
    )
    logger.info(summary)

    # Final action
    while True:
        action = get_input(
            "\n🧠 Deseja editar, salvar os parâmetros ou iniciar o trade? Digite 'e' para editar, 's' para salvar a estratégia ou 'i' para iniciar: ",
            "Digite 'e' para editar os parâmetros, 's' para salvar a estratégia em um arquivo JSON, ou 'i' para iniciar o trade.",
            "⚠️ Opção inválida. Digite 'e', 's', ou 'i'.",
            validate=lambda x: x.lower() if x.lower() in ['e', 's', 'i'] else None
        )
        if action == 'BACK':
            continue
        if action == 'RESTART':
            return get_strategy_config(logger)
        if action.lower() == 'e':
            logger.info("\n🔁 Reiniciando configuração...")
            return get_strategy_config(logger)
        if action.lower() == 's':
            config['save_strategy'] = 's'
            strategy_config = {
                "saldo_limite": float(saldo_limite),
                "exchange": exchange,
                "par": par,
                "api_key": api_key,
                "api_secret": api_secret,
                "qty_initial": float(qty_initial),
                "qty_min": float(qty_min),
                "qty_max": float(qty_max),
                "qty_multiplier": float(qty_multiplier),
                "profit_target": float(profit_target * 100),
                "profit_target_min": float(profit_target_min * 100),
                "profit_target_max": float(profit_target_max * 100),
                "profit_target_multiplier": float(profit_target_multiplier),
                "rebuy_percent": float(rebuy_percent * 100),
                "rebuy_drop_min": float(rebuy_drop_min * 100),
                "rebuy_drop_max": float(rebuy_drop_max * 100),
                "rebuy_multiplier": float(rebuy_multiplier),
                "rebuys_max": rebuys_max,
                "fee": float(fee * 100),
                "profit_reaplicar": profit_reaplicar,
                "profit_distribution_orders": profit_distribution_orders,
                "save_strategy": 's'
            }
            strategy_dir = 'user/strategy'
            if not os.path.exists(strategy_dir):
                os.makedirs(strategy_dir)
                
            filename = f"{strategy_dir}/strategy_{datetime.now().strftime('%Y%m%d')}_{exchange.replace(' ', '_')}_{par.replace('/', '_')}.json"
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(strategy_config, f, indent=4, ensure_ascii=False)
                logger.info(f"💾 Estratégia salva com sucesso em {filename}")
            except Exception as e:
                logger.error(f"⚠️ Falha ao salvar estratégia: {e}")
            continue
        if action.lower() == 'i':
            logger.info("\n🚀 Iniciando operação com os parâmetros definidos!\n")
            return config