"""Clientes e frases sintéticos. Nenhum dado real."""

CUSTOMERS = {
    "infinitepay": [
        {"external_id": "sim-ip-001", "name": "Ana Ficticia", "email": "ana.ficticia@example.com", "phone": "+5500900000001"},
        {"external_id": "sim-ip-002", "name": "Bruno Inventado", "email": "bruno.inventado@example.com", "phone": "+5500900000002"},
        {"external_id": "sim-ip-003", "name": "Carla Sintetica", "email": "carla.sintetica@example.com", "phone": "+5500900000003"},
    ],
    "jim": [
        {"external_id": "sim-jim-001", "name": "John Placeholder", "email": "john.placeholder@example.com", "phone": "+1555000000001"},
        {"external_id": "sim-jim-002", "name": "Mary Sample", "email": "mary.sample@example.com", "phone": "+1555000000002"},
    ],
}

PHRASES = {
    "infinitepay": [
        "Minha maquininha não liga",
        "Não recebi o pagamento de ontem",
        "Como faço para pedir uma segunda via do cartão?",
        "Quero falar com um atendente",
    ],
    "jim": [
        "My card reader won't turn on",
        "I didn't get yesterday's payout",
        "How do I change my bank account?",
        "I want to talk to a human",
    ],
}
