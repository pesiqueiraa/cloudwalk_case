-- Dados iniciais sintéticos. IDs fixos e ON CONFLICT DO NOTHING: reaplicar na subida não desfaz
-- o que a operação mudou pela API (filas e regras são desativadas, nunca apagadas).

INSERT INTO teams (id, name) VALUES
    ('geral', 'Suporte Geral'),
    ('pagamentos', 'Pagamentos'),
    ('hardware', 'Hardware'),
    ('seguranca', 'Segurança e Fraude')
ON CONFLICT DO NOTHING;

INSERT INTO analysts (id, team_id, name, email) VALUES
    ('30000000-0000-0000-0000-000000000001', 'geral', 'Lia Exemplo', 'lia.exemplo@example.com'),
    ('30000000-0000-0000-0000-000000000002', 'geral', 'Tom Sample', 'tom.sample@example.com'),
    ('30000000-0000-0000-0000-000000000003', 'pagamentos', 'Rui Ficticio', 'rui.ficticio@example.com'),
    ('30000000-0000-0000-0000-000000000004', 'pagamentos', 'Kate Mock', 'kate.mock@example.com'),
    ('30000000-0000-0000-0000-000000000005', 'hardware', 'Davi Inventado', 'davi.inventado@example.com'),
    ('30000000-0000-0000-0000-000000000006', 'hardware', 'Nina Teste', 'nina.teste@example.com'),
    ('30000000-0000-0000-0000-000000000007', 'seguranca', 'Olga Sintetica', 'olga.sintetica@example.com'),
    ('30000000-0000-0000-0000-000000000008', 'seguranca', 'Sam Placeholder', 'sam.placeholder@example.com')
ON CONFLICT DO NOTHING;

INSERT INTO queues (id, name, brand_id, team_id, first_responder, is_default) VALUES
    ('10000000-0000-0000-0000-000000000001', 'InfinitePay · Geral', 'infinitepay', 'geral', 'agent', true),
    ('10000000-0000-0000-0000-000000000002', 'InfinitePay · Pagamentos', 'infinitepay', 'pagamentos', 'agent', false),
    ('10000000-0000-0000-0000-000000000003', 'InfinitePay · Hardware', 'infinitepay', 'hardware', 'agent', false),
    ('10000000-0000-0000-0000-000000000004', 'InfinitePay · Segurança', 'infinitepay', 'seguranca', 'human', false),
    ('10000000-0000-0000-0000-000000000011', 'JIM · General', 'jim', 'geral', 'agent', true),
    ('10000000-0000-0000-0000-000000000012', 'JIM · Payments', 'jim', 'pagamentos', 'agent', false),
    ('10000000-0000-0000-0000-000000000013', 'JIM · Hardware', 'jim', 'hardware', 'agent', false),
    ('10000000-0000-0000-0000-000000000014', 'JIM · Security', 'jim', 'seguranca', 'human', false)
ON CONFLICT DO NOTHING;

INSERT INTO routing_rules (id, name, position, brand_id, category, queue_id) VALUES
    ('20000000-0000-0000-0000-000000000001', 'InfinitePay: fraude', 10, 'infinitepay', 'fraud', '10000000-0000-0000-0000-000000000004'),
    ('20000000-0000-0000-0000-000000000002', 'InfinitePay: pagamentos', 20, 'infinitepay', 'payments', '10000000-0000-0000-0000-000000000002'),
    ('20000000-0000-0000-0000-000000000003', 'InfinitePay: cartão', 30, 'infinitepay', 'card', '10000000-0000-0000-0000-000000000002'),
    ('20000000-0000-0000-0000-000000000004', 'InfinitePay: maquininha', 40, 'infinitepay', 'hardware', '10000000-0000-0000-0000-000000000003'),
    ('20000000-0000-0000-0000-000000000011', 'JIM: fraud', 10, 'jim', 'fraud', '10000000-0000-0000-0000-000000000014'),
    ('20000000-0000-0000-0000-000000000012', 'JIM: payments', 20, 'jim', 'payments', '10000000-0000-0000-0000-000000000012'),
    ('20000000-0000-0000-0000-000000000013', 'JIM: card', 30, 'jim', 'card', '10000000-0000-0000-0000-000000000012'),
    ('20000000-0000-0000-0000-000000000014', 'JIM: card reader', 40, 'jim', 'hardware', '10000000-0000-0000-0000-000000000013')
ON CONFLICT DO NOTHING;

-- Os mesmos clientes do simulador (simulator/data.py), identificados pelo canal de chat
INSERT INTO customers (brand_id, external_id, name, email) VALUES
    ('infinitepay', 'sim-ip-001', 'Ana Ficticia', 'ana.ficticia@example.com'),
    ('infinitepay', 'sim-ip-002', 'Bruno Inventado', 'bruno.inventado@example.com'),
    ('infinitepay', 'sim-ip-003', 'Carla Sintetica', 'carla.sintetica@example.com'),
    ('jim', 'sim-jim-001', 'John Placeholder', 'john.placeholder@example.com'),
    ('jim', 'sim-jim-002', 'Mary Sample', 'mary.sample@example.com')
ON CONFLICT DO NOTHING;
