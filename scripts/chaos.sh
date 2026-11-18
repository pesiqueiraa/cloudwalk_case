#!/usr/bin/env bash
# Script de caos: manda lotes de mensagens, provoca falhas no meio e confere pela API que nenhuma
# mensagem se perdeu nem duplicou, e que a ordem por conversa se manteve.
#
# Uso (dentro de cloudwalk_case/, com o ambiente no ar):  scripts/chaos.sh [cenário...]
#   cenários: duplicado, agente, reentrega (padrão: os três)
#   COUNT=60 RATE=10 scripts/chaos.sh      tamanho e ritmo de cada lote
#
# Mexe só no ambiente local do compose: para e religa serviços, volta offsets de consumidores e
# devolve jobs já entregues para a fila. Não apaga dados.
set -euo pipefail
cd "$(dirname "$0")/.."

COUNT=${COUNT:-60}
RATE=${RATE:-10}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
RESULTS=()

say() { printf '\n== %s\n' "$*"; }
source scripts/lib.sh

check() {
  local name=$1 file=$2
  if sim verify --settle "${3:-5}" < "$file" | tee "$WORK/$name.out"; then
    RESULTS+=("OK     $name")
  else
    RESULTS+=("FALHOU $name")
  fi
}

traces_sql() {  # lista SQL dos trace_id de um lote
  python3 -c 'import json,sys; print(",".join("'"'"'%s'"'"'" % m["trace_id"] for m in json.load(open(sys.argv[1]))["messages"]))' "$1"
}

scenario_duplicado() {
  say "Cenário 1: webhook duplicado ($COUNT mensagens, cada uma enviada duas vezes pelo canal)"
  sim burst --count "$COUNT" --rate "$RATE" --per-conversation 3 --duplicate > "$WORK/dup.json"
  sim verify --settle 0 < "$WORK/dup.json" > /dev/null || true   # espera as respostas
  echo "devolvendo os $COUNT jobs já entregues para a fila: o worker manda cada webhook de novo"
  sql "UPDATE webhook_jobs SET status = 'pending', next_attempt_at = now()
       WHERE status = 'done' AND trace_id IN ($(traces_sql "$WORK/dup.json"))" 
  sleep 3
  wait_lag_zero
  check "webhook duplicado" "$WORK/dup.json"
}

scenario_agente() {
  say "Cenário 2: agente derrubado e religado, broker-outbound morto com SIGKILL ($COUNT mensagens)"
  sim burst --count "$COUNT" --rate "$RATE" --per-conversation 3 > "$WORK/down.json" &
  local burst_pid=$!
  sleep 2
  echo "parando o agent-mock"; docker compose stop agent-mock >/dev/null 2>&1
  sleep 8
  echo "religando o agent-mock"; docker compose start agent-mock >/dev/null 2>&1
  sleep 1
  echo "matando o broker-outbound (SIGKILL) e religando"
  docker compose kill -s SIGKILL broker-outbound >/dev/null 2>&1
  docker compose start broker-outbound >/dev/null 2>&1
  wait "$burst_pid"
  wait_lag_zero
  check "agente derrubado" "$WORK/down.json"
}

scenario_reentrega() {
  say "Cenário 3: reentrega forçada (offsets voltam para antes do lote)"
  wait_lag_zero
  snapshot agent-mock > "$WORK/agent-mock.offsets"
  snapshot broker-outbound > "$WORK/broker-outbound.offsets"
  sim burst --count "$COUNT" --rate "$RATE" --per-conversation 3 > "$WORK/redeliver.json"
  sim verify --settle 0 < "$WORK/redeliver.json" > /dev/null || true
  wait_lag_zero
  echo "parando os consumidores e voltando os offsets"
  local failed=""
  rewind_consumers "$COUNT" || failed=" consumidores"
  sleep 3
  wait_lag_zero
  if [[ -n $failed ]]; then RESULTS+=("FALHOU reentrega forçada (seek de$failed)"); return; fi
  check "reentrega forçada" "$WORK/redeliver.json"
}

scenarios=("$@")
[[ ${#scenarios[@]} -eq 0 ]] && scenarios=(duplicado agente reentrega)
for s in "${scenarios[@]}"; do "scenario_$s"; done

say "Resultado"
printf '%s\n' "${RESULTS[@]}"
if printf '%s\n' "${RESULTS[@]}" | grep -q FALHOU; then
  echo "CAOS FALHOU (stderr do simulador: $WORK/sim.err)"; trap - EXIT; exit 1
fi
echo "CAOS OK"
