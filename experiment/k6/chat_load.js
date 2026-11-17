// Gerador de carga do experimento: manda COUNT mensagens de chat a RATE msg/s, em modelo aberto.
//
// O executor constant-arrival-rate dispara cada mensagem no horário marcado, sem esperar a anterior
// responder: se a ingestão ficar lenta, a taxa pedida se mantém e o atraso aparece em
// http_req_duration (e, faltando VUs, em dropped_iterations), em vez de sumir.
//
// Cada mensagem enviada vira uma linha JSON no console (--console-output), que
// `simulator from-k6` converte no lote do `simulator verify`. O k6 mede só a ingestão síncrona;
// a latência ponta a ponta (recebida → respondida pelo agente) sai da auditoria, no verify.
//
// Conversas intercaladas: a mensagem i vai para a conversa i % N. Duas mensagens da mesma conversa
// saem com N/RATE segundos de distância, então a ordem de envio é a ordem de chegada e o verify
// pode conferir a ordem por conversa mesmo com várias VUs em paralelo.
//
// Variáveis: RATE (msg/s), COUNT, PER_CONVERSATION, DUPLICATE=1 (manda cada mensagem duas vezes),
// RUN_ID, PLATFORM_URL, POOL (JSON de `simulator k6-pool`), SUMMARY (arquivo do resumo).
import http from 'k6/http';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

const RATE = Number(__ENV.RATE || 11);
const COUNT = Number(__ENV.COUNT || 660);
const PER_CONVERSATION = Number(__ENV.PER_CONVERSATION || 5);
const DUPLICATE = __ENV.DUPLICATE === '1';
const RUN_ID = __ENV.RUN_ID || `k6-${Date.now()}`;
const PLATFORM_URL = __ENV.PLATFORM_URL || 'http://platform-web:8000';
const SUMMARY = __ENV.SUMMARY || '/experiment/out/summary.json';
const pool = JSON.parse(open(__ENV.POOL || '/experiment/out/pool.json'));

const CONVERSATIONS = Math.ceil(COUNT / PER_CONVERSATION);
const accepted = new Counter('messages_accepted');
const rejected = new Counter('messages_rejected');

export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  // Declarar a submétrica faz o resumo trazer a latência só das primeiras cópias (tag ingest)
  thresholds: { 'http_req_duration{name:ingest}': ['max>=0'] },
  scenarios: {
    chat: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: `${Math.ceil(COUNT / RATE)}s`,
      preAllocatedVUs: Math.max(10, Math.ceil(RATE * 2)),
      maxVUs: 300,
      gracefulStop: '30s',
    },
  },
};

const ok = (r) => r.status >= 200 && r.status < 300; // a ingestão responde 202

function post(payload, name = 'ingest') {
  return http.post(`${PLATFORM_URL}/channels/chat/messages`, JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '10s',
    tags: { name },
  });
}

export default function () {
  const seq = exec.scenario.iterationInTest;
  if (seq >= COUNT) return; // o executor pode disparar uma iteração a mais no fim
  const conversation = seq % CONVERSATIONS;
  const customer = pool.customers[conversation % pool.customers.length];
  const payload = {
    session_id: `${RUN_ID}-c${conversation}`,
    message_id: `${RUN_ID}-m${seq}`,
    brand: pool.brand,
    customer,
    text: pool.texts[seq % pool.texts.length],
    sent_at: new Date().toISOString(),
  };

  const response = post(payload);
  if (!ok(response)) {
    rejected.add(1);
    console.log(JSON.stringify({ seq, error: response.status || response.error }));
    return;
  }
  const body = response.json();
  if (DUPLICATE) {
    const copy = post(payload, 'ingest_copy');
    if (!ok(copy) || copy.json('duplicate') !== true) {
      rejected.add(1);
      console.log(JSON.stringify({ seq, error: `copia nao marcada como duplicata (${copy.status})` }));
      return;
    }
  }
  accepted.add(1);
  console.log(JSON.stringify({
    seq,
    trace_id: body.trace_id,
    conversation_id: body.conversation_id,
    message_id: body.message_id,
    ingest_ms: response.timings.duration,
  }));
}

function metric(data, name, stat) {
  const m = data.metrics[name];
  return m && m.values[stat] !== undefined ? m.values[stat] : null;
}

export function handleSummary(data) {
  const summary = {
    run_id: RUN_ID,
    rate_requested: RATE,
    count_requested: COUNT,
    per_conversation: PER_CONVERSATION,
    duplicate: DUPLICATE,
    accepted: metric(data, 'messages_accepted', 'count') || 0,
    rejected: metric(data, 'messages_rejected', 'count') || 0,
    dropped_iterations: metric(data, 'dropped_iterations', 'count') || 0,
    send_window_s: data.state.testRunDurationMs / 1000,
    ingest_ms: {
      p50: metric(data, 'http_req_duration{name:ingest}', 'med'),
      p95: metric(data, 'http_req_duration{name:ingest}', 'p(95)'),
      p99: metric(data, 'http_req_duration{name:ingest}', 'p(99)'),
      max: metric(data, 'http_req_duration{name:ingest}', 'max'),
    },
    vus_max: metric(data, 'vus_max', 'max'),
  };
  const ms = (v) => (v === null ? '-' : `${v.toFixed(1)} ms`);
  const text = [
    `k6 ${RUN_ID}: ${summary.accepted}/${COUNT} aceitas a ${RATE} msg/s pedidas ` +
      `(${(summary.accepted / summary.send_window_s).toFixed(1)} msg/s efetivas)`,
    `  recusadas: ${summary.rejected}  iterações descartadas: ${summary.dropped_iterations}`,
    `  ingestão: p50=${ms(summary.ingest_ms.p50)} p95=${ms(summary.ingest_ms.p95)} ` +
      `p99=${ms(summary.ingest_ms.p99)} máx=${ms(summary.ingest_ms.max)}`,
    '',
  ].join('\n');
  return { stdout: text, [SUMMARY]: JSON.stringify(summary, null, 2) };
}
