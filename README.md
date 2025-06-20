# Coryphaeus ⚙️🧠

**Bot modular de trading automático para o mercado spot de criptomoedas com estratégia de rebuy, múltiplos pares e múltiplas exchanges simultâneas.**

---

## 💡 Objetivo

Executar ciclos automáticos de trade com foco em recompra estratégica e lucro configurável. O sistema busca o equilíbrio entre preço médio, aproveitamento de quedas e realização de lucros.

---

## ⚙️ Funcionamento da Estratégia Rebuy

### 🔁 Ciclo Operacional

1. **Compra Inicial** a mercado (START).
2. **Ordem de Venda Limit** com lucro definido.
3. **Ordem de Recompra Limit** a um percentual abaixo do preço da última compra.

### 🟢 Se a venda for preenchida:

* Cancela a recompra.
* Inicia novo ciclo com nova compra a mercado.

### 🔵 Se a recompra for preenchida:

* Cancela a venda anterior.
* Recalcula preço médio.
* Atualiza ordem de venda com novo lucro e quantidade, sobre o preço médio.
* Cria nova recompra com base no preço da última compra.
* Cancela a venda anterior.
* Recalcula preço médio.
* Atualiza ordem de venda com novo lucro e quantidade, sobre o preço médio.
Esse ciclo se repete até atingir as limitações explícitas nas configurações ou a venda ser executada.

### 🔵 Se saldo terminar, o bot aguardará (pause) até detectar a entrada de mais saldo na conta ou até a ordem de venda ser preenchida.

---

## 🧱 Componentes Principais (em desenvolvimento)

* **StrategyManager**: Lógica central da estratégia.
* **RebuyStrategy**: Estratégia baseada em recompra.
* **StableTradeStrategy**: Estratégia voltada para pares de stablecoins.
* **ExchangeManager**: Gerencia múltiplas exchanges e subcontas.
* **BybitRESTClient / WSClient**: Conexões autenticadas com a Bybit (mainnet/testnet).
* **OrderManager**: Criação, cancelamento e verificação de ordens.
* **CycleManager**: Controle de ciclos de trading.
* **PairManager**: Gerencia pares ativos.
* **ProfitManager**: Consolidação de lucros por par/exchange.
* **RiskManager**: Limites de saldo e validações.
* **BalanceManager**: Verificação de saldos disponíveis.
* **LogManager**: Logging estruturado.
* **TheGuardian**: Monitor de estado persistente.
* **BacktestModule**: Simulações offline.
* **MenuManager**: Interface interativa com o usuário.
* **Utils**: Funções auxiliares (math, tempo, formatação, etc).

---

## 📆 Configurações Avançadas

### 🔹 Bloco: Valores de Ordem

* Valor Inicial da Ordem
* Valor Mínimo e Máximo da Ordem
* Multiplicador progressivo de ordens

### 🔹 Bloco: Lucro

* Lucro alvo por trade (%)
* Lucro Mínimo/Máximo
* Multiplicador de Lucro (ajusta conforme número de recompras)
* Reaplicação de lucro nos próximos ciclos

### 🔹 Bloco: Recompras

* Diferença percentual entre os preços de compras (queda)
* Rebuy %: inicial
* Rebuy Minimo e Máximo %:
* Multiplicador da variação da queda
* Número máximo de recompras

### 🔹 Bloco: Taxas

* Taxas Maker/Taker da Exchange
* Suporte a pares com taxa zero

### 🔹 Bloco: Limite de Saldo

* Definição de capital máximo por estratégia
* Detecção automática de saldo necessário

---

## 📊 Exemplo de Ciclo

```
1. Compra a mercado: 100 USDT
2. Venda LIMIT: +1.5%
3. Recompra LIMIT: -3%
   → Preenchida?
       → Atualiza preço médio e nova venda com lucro.
       → Nova recompra (com possível novo valor ajustado).
```

---

## 📦 Em Desenvolvimento

* [ ] Modularização completa do projeto atual
* [ ] Multi-instância por par (Thread/Async)
* [ ] Estratégias específicas por par
* [ ] Persistência e recuperação de estado
* [ ] Interface CLI amigável
* [ ] Logs com rotação e contexto por par

---

## ▶️ Requisitos

* Python 3.10+
* Biblioteca WebSocket e REST
* Acesso API às Exchanges (ex.: Bybit)

---

## 📁 Estrutura Inicial do Projeto (prevista)

```
coryphaeus/
├── core/
│   ├── exchange/
│   ├── strategy/
│   ├── trading/
│   ├── system/
│   ├── events/
│   └── utils/
├── interface/
├── config/
├── main.py
└── requirements.txt
```

---

## 📚 Contribuindo

Este projeto está em fase de reestruturação. Se você domina Python, mercados financeiros, arquitetura de sistemas ou deseja aprender e colaborar, contribuições são bem-vindas!


---

> Desenvolvido por [Sindak](https://github.com/Macanada) — projeto pessoal com foco em automação inteligente, segurança e experimentação estratégica.

