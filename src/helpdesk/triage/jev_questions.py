"""Texto das perguntas ao Jev, num lugar só: é o que se audita e se ajusta.

Mudou uma pergunta, uma opção ou um critério? Suba QUESTIONS_VERSION: a versão vai para a auditoria
de cada mensagem classificada, e os limiares de decision.py foram medidos nesta formulação (25/11).
"""
from typesafe_sdk import Choice, Noul, Score

QUESTIONS_VERSION = "1"

# Fatos que o modelo não teria: o que cada marca vende e em que idioma o cliente escreve
COMPANY = {
    "infinitepay": "InfinitePay, a Brazilian fintech. It sells card machines (called 'maquininha') to small "
                   "merchants and offers them a digital account with Pix transfers and a payment card. "
                   "Customers write in Portuguese.",
    "jim": "JIM, a US fintech brand. It sells card readers to small merchants and offers them a business "
           "account with transfers and a payment card. Customers write in English.",
}

# Ordem das opções conferida: invertê-la não mudou o acerto (sonda de 25/11)
TOPICS = {
    "payments": "Money the merchant expected to receive or send: sales settling into the account, "
                "Pix or transfers, balance, payouts, anticipation of receivables.",
    "card": "The payment card the company issues to the customer: getting one, limits, declines, "
            "statements, blocking.",
    "hardware": "The card machine or card reader device itself: not turning on, screen, battery, "
                "printing receipts, chip slot.",
    "account": "Access to and details of the customer's account: login, password, changing phone, "
               "e-mail or address.",
    "fraud": "Someone else acting against the customer: scams, impersonation, transactions the "
             "customer did not make, a stolen or invaded account.",
}

# Níveis 0 a 3, cada um descrito como uma situação
FRUSTRATION_LEVELS = [
    "The customer is calm and neutral, or friendly.",
    "The customer is worried or mildly bothered, but polite.",
    "The customer is clearly upset about the impact on them.",
    "The customer is angry: exclamation marks, sarcasm, insults, threats or saying they are fed up.",
]

QUESTIONS = {
    "topic": Choice(instructions="Which product area is the customer's `message` about?", criteria=TOPICS),
    # Par do Choice: o Choice sempre escolhe uma opção, este Noul diz se alguma serve
    "has_topic": Noul(
        instructions="Does `message` describe a problem or question about one of the company's products?",
        criteria={
            "true": "The customer talks about receiving or sending money, the card, the card machine, account "
                    "access, or a scam.",
            "false": "The message is only a greeting, a thank-you, a request to talk to a person, a threat to "
                     "complain, or a question about the company in general, such as opening hours or stores.",
        },
    ),
    "frustration": Score(
        instructions="How frustrated is the customer, judging by `message` and the earlier messages in "
                     "`conversation`?",
        criteria=FRUSTRATION_LEVELS,
    ),
    "wants_human": Noul(
        instructions="In `message`, is the customer asking to talk to a human person instead of the automated "
                     "assistant?",
        criteria={
            "true": "The customer asks for an attendant, a person, a manager, or someone other than the bot.",
            "false": "The customer only describes a problem, even an angry one, without asking for a person.",
        },
    ),
    "urgent": Noul(
        instructions="Does the customer say in `message` that the problem is blocking their business or must "
                     "be solved today?",
    ),
}


def build_state(brand: str, text: str, history: list[dict]) -> dict:
    """Estado da pergunta: a empresa, as mensagens anteriores (quem disse o quê) e a mensagem nova."""
    return {
        "company": COMPANY[brand],
        "conversation": [{"from": m["author"], "text": m["text"]} for m in history],
        "message": text,
    }
