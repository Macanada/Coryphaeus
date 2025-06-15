Essa é explicação do que se espera da estratégia:
💡 Objetivo
O bot executa ciclos automáticos de trade baseados em compras e recompras, com lógica de lucro e ajuste de preço médio. O usuário define os parâmetros de lucro e percentual de queda para recompra.

⚙️ Funcionamento Esperado
1. Início do Ciclo
O ciclo começa com uma ordem de compra a mercado.

Assim que a compra é preenchida, o bot:

Envia uma ordem de venda LIMIT com a quantidade comprada e uma margem de lucro definida pelo usuário.

Envia simultaneamente uma ordem de recompra LIMIT a um percentual abaixo do preço da compra inicial (também definido pelo usuário).

2. Cenários possíveis
🟢 Cenário 1: Ordem de venda é preenchida (take profit)
O bot cancela a ordem de recompra pendente.

Um novo ciclo se inicia:

Compra a mercado.

Venda limit com lucro.

Recompra limit com desconto.

🔵 Cenário 2: Ordem de recompra é preenchida (preço caiu)
O bot cancela a ordem de venda pendente.

Recalcula:

Quantidade total acumulada no ciclo (compra inicial + recompra).
Preço médio ponderado das compras.
Com base nisso, o bot:
Cria uma nova ordem de venda limit, com a nova quantidade e preço médio + lucro configurado.
Envia novamente uma ordem de recompra com percentual de queda baseado na última compra.
Esse processo se repete conforme o número de recompras configurado pelo usuário. A cada recompra preenchida:
A ordem de venda anterior é cancelada.
O bot recalcula a média de preço e a quantidade acumulada.
Atualiza a ordem de venda com os novos valores.
Cria uma nova ordem de recompra (mais abaixo).
Caso a venda seja preenchida em qualquer momento, o ciclo é reiniciado do zero com nova compra a mercado.

Varias ferramentas de caculos foram criadas para ajudar a otimizar as configurações de estratégia, ex.:

# Bloco: Order Value.

(input)🔹Order Value (aqui deve aparecer a sigla da Moeda de Cotação automaticamente):
ValueHelp: "Valor da Ordem inicial na Moeda de Cotação para as operaçõesl. (ex. 100 USDT)"
ValueError("⚠️O valor da ordem deve ser maior ou igual ao mínimo permitido pela Exchange, não pode ser superior ao Limite de Saldo.")

(input)🔹Order Value Mínimo:
ValueHelp: "Valor da Ordem Mínima na Moeda de Cotação para as operaçõesl. O fator multiplicador irá reduzir gradativamente o valor das ordens a patir do Order Value até ao mínimo. (ex. 10 USDT). ⚠️Não utilize está função a menos que você saiba exatamente o que está fazendo, a redução do Order Value pode ocasionar prejuízos irreversíveis!"
ValueError("⚠️ Não pode ser superior ao Order Value, Não pode ser inferior ao mínimo permitido pela Exchange.")

(input)🔹 Order Value Máximo:
ValueHelp: "Valor da Ordem Máxima na Moeda de Cotação para as operaçõesl. O fator multiplicador irá ampliar gradativamente o valor das ordens a patir do Order Value até ao máximo. (ex. 400 USDT).”

ValueError("⚠️ Não pode ser menor que o Order Value, Não pode ser superior ao Limite de Saldo para a Estratégia caso houver.")

(input)🔹 Multiplicador do Order Value: 
versão original - ValueHelp: “Multiplicador do Order Value, esse parâmetro  criará uma escala gradual do valor da ordem, elevando, mantendo ou diminuindo o valor de cada nova Ordem de Recompra dentro de um mesmo ciclo até atingir os limites ou ao terminar o ciclo, esse efeito é resetado quando um novo ciclo começar. O multiplicador maior que 1 aumenta o valor das ordens de compra a partir do Order Value até atingir o Order Value Máximo, menor que 1 diminui a partir do Oder Value até atingir o Order Value Mínimo,  igual a 1 inteiro anula os efeitos de multiplicação, todas as ordens terão sempre o mesmo valor. (Ex: 1.02 aumenta, 1 mantém, 0.9 reduz) "
versão editada - ValueHelp:”
Define o fator de multiplicação aplicado ao valor base das ordens de recompra dentro de um mesmo ciclo de operação. Esse parâmetro controla a progressão do valor das ordens, permitindo aumentos, reduções ou manutenção constante conforme configurado:

Multiplicador > 1.0: incrementar progressivamente o valor das ordens de recompra até o limite definido por Order Value Máximo.
Multiplicador = 1.0: desativa a variação, mantendo todas as ordens com o mesmo valor base.
Multiplicador < 1.0: reduz gradualmente o valor das ordens até o limite definido por Order Value Mínimo.

Essa escala é aplicada apenas dentro do ciclo atual e é reinicializada automaticamente ao início de um novo ciclo.
Exemplos: 1.02 (aumenta), 1.00 (mantém), 0.90 (reduz).”

ValueError("⚠️ Multiplicador deve ser maior que zero.")

# Bloco: Profit:

(input)🔹 Lucro:
 ValueHelp: ”Meta de lucro por trade. Ex: 1.5 para 1.5%.”
ValueError("⚠️ O  Lucro alvo não pode ser igual a ZERO, no máximo 200%. Não digite o símbolo %, Não use vírgula.")

(input)🔹 Lucro Mínimo:
 ValueHelp: ”O Lucro Mínimo está combinado com o Multiplicador de Lucro e poderá reduzir gradativamente o Lucro até atingir o Lucro Mínimo. Ex.: 0.5 para 0.5%"
 ValueError("⚠️ O valor do Lucro Mínimo não pode ser superior ao Lucro. Não pode ser ZERO, Não pode ser negativo, não pode conter o símbolo %, Não use vírgula.")

(input)🔹 Lucro Máximo:
 ValueHelp: ”O Lucro Máximo está combinado com o Multiplicador de Lucro e poderá aumentar gradativamente o Lucro até atingir o Lucro Máximo. Ex.: 8.5 para 8.5% "
ValueError("⚠️ O valor do Lucro Máximo não pode ser inferior ao valor Lucro até no máximo 200%.  Não pode ser ZERO, Não pode ser negativo, não pode conter o símbolo %, Não use vírgula.")

(input)🔹 Multiplicador do Lucro:
versão original - ValueHelp:”
Fator de Multiplicação aplicado ao Lucro. Este parâmetro  combina o Lucro com o Lucro Mínimo ou com o Lucro Máximo, gerando um efeito gradadativo de redução ou aumento do percentual do Lucro conforme o número de Recompras for aumentando dentro de um mesmo ciclo de operação. por Exemplo: o Lucro foi definido em 10% com o fator multiplicador em 0.98 forçando a uma redução de lucro a cada Recompra adquirida com o intuito de terminar o ciclo mais rápido, isto é funcinal para o Mercado em descenso, diminuir o lucro na espectativa de recuperar mais rápido o capital investido no ciclo. por Exemplo: o Lucro foi definido em 10% com o fator multiplicador em 1.04 forçando a um aumento gradativo do lucro a cada Recompra adquirida, com o intuito de manter o preço de venda sempre na mesma região, isto é funcinal para Swimming com Mercado em descenso acreditando na pronta recuperação do valor do ativo, e assim obter lucros maiores (isso não é recomendável para Memecoins).por Exemplo: o Lucro foi definido em 10% com o fator multiplicador em 1 o efeito do multiplicador é anulado e a cada Recompra o nova Ordem de Venda sempre terá 10% de Lucro. O multiplicador é resetado a cada novo ciclo.*
 versão editada - ValueHelp:”
Define o fator de multiplicação aplicado ao percentual de lucro alvo (Target Profit) para ordens de venda dentro de um mesmo ciclo. Esse parâmetro ajusta gradualmente o lucro com base no número de recompras realizadas:

Multiplicador < 1.0: reduz o lucro progressivamente a cada recompra, favorecendo a finalização do ciclo mais rapidamente — útil em cenários de mercado em queda.
Multiplicador > 1.0: aumenta gradualmente o lucro a cada recompra, mantendo o alvo de venda em uma faixa superior — pode ser útil em mercados voláteis com perspectiva de recuperação (não recomendado para ativos altamente instáveis, como memecoins).
Multiplicador = 1.0: desativa o ajuste, mantendo o mesmo percentual de lucro em todas as ordens.

Exemplos:
Lucro inicial: 10%, Multiplicador: 0.98 → lucro reduzido a cada recompra.
Lucro inicial: 10%, Multiplicador: 1.04 → lucro aumentado a cada recompra.
Multiplicador: 1.00 → lucro constante em todas as ordens.

O efeito é reiniciado a cada novo ciclo.”
ValueError("⚠️ Multiplicador deve ser maior que zero.")

(input)🔹 Reaplicar Lucro? (s/n)

‘n’ = continuar sem reaplicar o lucro.
‘s’ = Reaplicar o Lucro 

ValueHelp:"O lucro que se obtém ao terminar os Ciclos será Reaplicado ao Order Value dos próximos ciclos“

if ‘s’ 
(input)🔹 Em até quantas compras Reaplicar o Lucro? 
ValueHelp:"O lucro que se obtém ao terminar os Ciclos será Reaplicado ao um número específico de ordens de compra do próximo ciclo.“
ValueError("⚠️ Use um número Inteiro positivo. ZERO anula o efeito de reaplicar o lucro.")
```python:
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
```

      # Bloco: Recompras
 
(input)🔹Diferença Percentual entre os Preços de compra:
 ValueHelp:"falta adicionar o texto de ajuda.(ex.: 0.5 para 0.5%) "
 ValueError("O valor percentual deve ser superior à 0 e inferior à 100%.")

(input)🔹 Diferença Percentual Mínima entre os Preços de compra:
 ValueHelp:"falta adicionar o texto de ajuda.(ex.: 0.3 para 0.3%) "
 ValueError("⚠️ O valor da Diferença Percentual Mínima entre os Preços não pode ser superior ao Valor da Diferença Percentual entre os Preços, e Deve ser superior a ZERO.")

(input)🔹 Diferença Percentual Máxima entre os Preços de compra:
 ValueHelp:"falta adicionar o texto de ajuda.(ex.: 1.5 para 1.5%) "
ValueError("⚠️ O valor da Diferença Percentual Máxima entre os Preços não pode ser inferior ao Valor da Diferença Percentual.")

(input)🔹 Multiplicador da Diferença Percentual entre os Preços:
ValueHelp:" falta adicionar o texto de ajuda. (Ex: 1 mantém, 1.02 aumenta, 0.98 diminui)  "
ValueError("⚠️O valor do Multiplicador deve ser maior que ZERO.")


(input)🔹 Número Máximo de Recompras:
ValueHelp: "Número máximo de recompras consecutivas permitidas. 0 (ZERO) permite recompras ilimitadas até o saldo acabar."
ValueError(" ⚠️O valor Não pode ser negativo.")


# Bloco: Taxas da Exchange

(input)🔹Taxas:
ValueHelp: "Informe as taxas cobradas pela Exchange em operações do tipo Maker (ordem limite) e Taker (ordem a mercado). Pode ser 0 em pares com zero fee.(ex: 0.1%)"
ValueError: ("⚠️ Valor inválido. Use um percentual positivo ou zero. Não digite o símbolo %. Não use vírgula")



# Bloco: Resumo

 # Imprimir Resumo Final

✅ RESUMO DA ESTRATÉGIA CONFIGURADA:

    # Pergunta Final

#  Bloco: Limite de Saldo e Salvamento

“Se possivel, imprimir aqui o status da quantidade de Moeda de Cotação necessária para rodar a Estratégia (ex: Saldo necessário para esta estratégia: $ 13500 USDT)”

(input)🔹Limitar Saldo para Estratégia em MC (aqui deve aparecer automaticamente o símbolo da Moeda de Cotação):
ValueHelp: "Limitador do Saldo para a estratégia. O valor deve ser inteiro, positivo e superior ao valor mínimo do PAR de trade válido definido pela Exchange. 0 (ZERO) representa sem limites de Saldo para essa estratégia."
ValueError: ("⚠️ Insira um valor válido! pressione h e enter para ajuda!")

🧠 Deseja editar, salvar os parâmetros ou iniciar o trade?

(input) Digite 'e’ para editar, ‘s’ para salvar a estratégia ou 'i’ para iniciar  ➡️



