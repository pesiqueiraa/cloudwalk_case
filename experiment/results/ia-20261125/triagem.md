## Categoria

| Conjunto | n | regras | jev |
|---|---|---|---|
| Categoria — base | 73 | 100% | 99% |
| Categoria — hard | 48 | 35% | 100% |
| Categoria — blind | 40 | 52% | 95% |

## Sentimento (jev)

| Conjunto | n | Nível exato | ±1 nível | Frustrado ou mais: precisão | recall | Pede humano |
|---|---|---|---|---|---|---|
| hard | 48 | 71% | 96% | 94% | 85% | 100% |
| blind | 40 | 90% | 95% | 94% | 94% | 100% |

## Latência e reservas

| Classificador | p50 | p95 | Caiu nas regras |
|---|---|---|---|
| regras | 0 ms | 0 ms | 0 |
| jev | 172 ms | 196 ms | 0 |

## Erros de categoria

- regras [hard] esperado payments, veio other: “Vendi a manhã inteira e até agora nada entrou na minha conta”
- regras [hard] esperado payments, veio other: “O cliente jura que mandou, mas pra mim não chegou nada ainda”
- regras [hard] esperado payments, veio other: “Terceira vez que escrevo aqui e ninguém resolve meu repasse!!! Que palhaçada”
- regras [hard] esperado hardware, veio other: “A tela da minha POS apagou do nada e não volta”
- regras [hard] esperado hardware, veio other: “O aparelho não imprime mais o papelzinho pro cliente”
- regras [hard] esperado hardware, veio other: “Comprei o equipamento semana passada e já parou, estou perdendo cliente, isso é um absurdo”
- regras [hard] esperado card, veio other: “Como faço pra pedir o plástico físico pra pagar minhas compras?”
- regras [hard] esperado card, veio other: “Tentei pagar no mercado e foi recusado, passei vergonha na fila”
- regras [hard] esperado account, veio other: “Esqueci como entro no app, já tentei de tudo”
- regras [hard] esperado account, veio other: “Mudei de telefone e agora o aplicativo não me reconhece”
- regras [hard] esperado fraud, veio other: “Apareceu uma movimentação de 900 reais que eu não fiz”
- regras [hard] esperado fraud, veio other: “Um cara se passou pela empresa no WhatsApp e pediu pra eu instalar um app”
- regras [hard] esperado fraud, veio other: “Me roubaram e estão usando minha conta, socorro”
- regras [hard] esperado payments, veio other: “Tudo certo, só queria saber o prazo do crédito parcelado”
- regras [hard] esperado payments, veio other: “Ótimo, mais um dia sem receber. Parabéns pelo serviço.”
- regras [hard] esperado account, veio fraud: “Não é golpe, só quero mudar meu e-mail de contato”
- regras [hard] esperado payments, veio hardware: “A maquininha funciona, o problema é que o valor não aparece no app”
- regras [hard] esperado payments, veio account: “I sold all morning and nothing has hit my account yet”
- regras [hard] esperado payments, veio other: “My customer swears they paid, but it never showed up on my end”
- regras [hard] esperado hardware, veio other: “The device stopped printing slips for my customers”
- regras [hard] esperado hardware, veio other: “Bought the terminal last week and it already died, I'm losing customers, this is unacceptable”
- regras [hard] esperado card, veio other: “How do I get the physical plastic one to pay for my purchases?”
- regras [hard] esperado card, veio other: “Got declined at the grocery store, so embarrassing in front of everyone”
- regras [hard] esperado account, veio other: “I forgot how to get into the app, tried everything”
- regras [hard] esperado account, veio other: “I switched phones and now the app doesn't recognize me”
- regras [hard] esperado fraud, veio other: “There's a $900 movement I never made”
- regras [hard] esperado fraud, veio other: “A guy pretending to be from the company texted me and asked me to install an app”
- regras [hard] esperado fraud, veio account: “They stole my phone and are using my account, help”
- regras [hard] esperado payments, veio other: “Great, another day without getting paid. Amazing service.”
- regras [hard] esperado account, veio fraud: “It's not a scam, I just want to change my contact email”
- regras [hard] esperado payments, veio hardware: “The reader works fine, the problem is the amount doesn't show in the app”
- regras [blind] esperado payments, veio other: “vendi ontem a tarde toda e ate agora nao caiu nada na conta, quando cai?”
- regras [blind] esperado payments, veio fraud: “não é golpe não viu, só quero confirmar se o dinheiro que o cliente disse que mandou entrou mesmo, ele me mostrou o comprovante mas nao to vendo aqui”
- regras [blind] esperado card, veio payments: “meu cartão foi recusado no mercado hoje com saldo na conta, passei a maior vergonha no caixa”
- regras [blind] esperado card, veio other: “perdi a carteira com o cartao dentro, como bloqueio rapido??”
- regras [blind] esperado hardware, veio other: “O APARELHO FICA SEM SINAL TODA HORA E O CLIENTE DESISTE DA COMPRA. QUE PALHAÇADA”
- regras [blind] esperado hardware, veio other: “bom dia, poderia me passar pra um atendente? a tela da que chegou ontem veio rachada”
- regras [blind] esperado account, veio other: “nao consigo entrar no app, fala q o codigo expirou mas nem chega sms”
- regras [blind] esperado fraud, veio other: “um rapaz ligou dizendo q era da infinitepay e pediu o codigo que chegou no meu zap, é vcs mesmo?”
- regras [blind] esperado fraud, veio other: “APARECEU UMA TRANSFERENCIA DE 2 MIL Q EU NAO FIZ!!! ME ROUBARAM, QUERO FALAR COM UM HUMANO AGORA”
- regras [blind] esperado fraud, veio account: “entraram na minha conta e trocaram meu email, agora nao consigo acessar nada”
- regras [blind] esperado payments, veio other: “hey quick q, how long do deposits usually take over the weekend?”
- regras [blind] esperado card, veio other: “pretty sure I left the plastic at the diner last night, can I lock it til I go check?”
- regras [blind] esperado hardware, veio payments: “the little device keeps saying tap again and then times out. lost two sales already today”
- regras [blind] esperado hardware, veio other: “Wow, love paying for a gadget that only connects on tuesdays. Truly innovative stuff.”
- regras [blind] esperado account, veio other: “locked out AGAIN. third time this week. fix your app”
- regras [blind] esperado fraud, veio account: “got a text saying my account is suspended and to click a link to verify, is that legit?”
- regras [blind] esperado fraud, veio other: “there are 4 charges from a store in another state I've never been to. please get me a real person”
- regras [blind] esperado fraud, veio account: “someone changed my login email overnight and now I can't get in. I definitely didn't do that”
- regras [blind] esperado fraud, veio other: “a guy called saying he was from jim support and asked me to read back a code. I gave it to him. what do I do now”
- jev [base] esperado other, veio card: “I booked my trip with a travel agency, can I pay with JIM?”
- jev [blind] esperado account, veio other: “need to update the business address, we moved last month”
- jev [blind] esperado fraud, veio account: “someone changed my login email overnight and now I can't get in. I definitely didn't do that”

