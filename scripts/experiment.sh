#!/usr/bin/env bash
# Experimento da semana 4: carga do k6 contra o volume de referência, com falhas injetadas.
#
# Hipótese: no pico de referência (11 msg/s), com o agente fora do ar por 10 s, nenhuma mensagem
# se perde ou duplica, e 95% das respostas às mensagens enviadas fora da queda chegam em menos de 1 s.
#
# Uso (dentro de cloudwalk_case/):  scripts/experiment.sh [cenário...]
#   cenários: base (2 msg/s), pico (11), agente-fora (11, agente derrubado por OUTAGE s),
#             reentrega (11, offsets voltam para antes do lote), maxima (22)   (padrão: todos)
#   RUNS=3 DURATION=60 OUTAGE=10 RESET=1 scripts/experiment.sh
#
# Cada rodada grava em experiment/results/<data>/<cenário>-<n>/: meta.json, k6-summary.json,
# lote.json, report.json (verify) e summary.json (run_summary.py), que a análise lê.
#
# RESET=1 (padrão) zera o ambiente antes de cada rodada (docker compose down -v): todas começam com
# o banco vazio e o seed. Apaga os dados locais do compose (todos sintéticos).
set -euo pipefail
cd "$(dirname "$0")/.."

# No macOS, o repouso por inatividade congela a VM do Docker no meio da rodada (17/11: duas rodadas
# esticaram de 60 s para 98 s e 224 s). caffeinate -i impede o repouso enquanto o script roda.
if [[ -z ${CAFFEINATED:-} ]] && command -v caffeinate >/dev/null; then
  CAFFEINATED=1 exec caffeinate -i "$0" "$@"
fi

RUNS=${RUNS:-3}
DURATION=${DURATION:-60}
OUTAGE=${OUTAGE:-10}
RESET=${RESET:-1}
PER_CONVERSATION=5
STAMP=$(date +%Y%m%d-%H%M%S)
RESULTS=experiment/results/$STAMP
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$RESULTS" experiment/out

source scripts/lib.sh

say() { printf '\n== %s\n' "$*"; }
now_utc() { python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())'; }

# meta DIR chave=valor...  (números viram número no JSON)
meta() {
  python3 - "$@" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]) / "meta.json"
data = json.loads(path.read_text()) if path.exists() else {}
for pair in sys.argv[2:]:
    key, _, value = pair.partition("=")
    try:
        data[key] = json.loads(value)
    except json.JSONDecodeError:
        data[key] = value
path.write_text(json.dumps(data, indent=2))
PY
}

prepare() {
  if [[ $RESET == 1 ]]; then
    echo "zerando o ambiente"
    docker compose down -v >/dev/null 2>&1
    docker compose up -d >/dev/null 2>&1
  fi
  # Aquecimento: confirma o caminho ponta a ponta e espera os consumidores estáveis no grupo
  sim smoke > /dev/null
  snapshot agent-mock > /dev/null
  snapshot broker-outbound > /dev/null
}

# load DIR RATE COUNT [-e VAR=valor...]: roda o k6 e converte a saída no lote do verify
load() {
  local dir=$1 rate=$2 count=$3; shift 3
  docker compose run --rm -T k6 run -q --log-format raw \
    --console-output "/$dir/k6.log" \
    -e RATE="$rate" -e COUNT="$count" -e PER_CONVERSATION="$PER_CONVERSATION" \
    -e RUN_ID="$(basename "$dir")-$STAMP" -e POOL=/experiment/out/pool.json \
    -e SUMMARY="/$dir/k6-summary.json" "$@" /experiment/k6/chat_load.js 2>>"$WORK/k6.err"
  sim from-k6 --rate "$rate" < "$dir/k6.log" > "$dir/lote.json"
  rm -f "$dir/k6.log"
}

verify() {  # verify DIR [--settle S]
  local dir=$1; shift
  sim verify --json "$@" < "$dir/lote.json" > "$dir/report.json" || true
}

steady() {  # steady DIR RATE: carga constante, sem falha
  local dir=$1 rate=$2
  load "$dir" "$rate" $((rate * DURATION))
  verify "$dir"
}

run_base()   { steady "$1" 2; }
run_pico()   { steady "$1" 11; }
run_maxima() { steady "$1" 22; }

run_agente-fora() {
  local dir=$1 rate=11
  load "$dir" "$rate" $((rate * DURATION)) &
  local load_pid=$!
  sleep $((DURATION / 3))
  docker compose kill -s SIGKILL agent-mock >/dev/null 2>&1
  meta "$dir" outage_start="$(now_utc)"
  echo "  agent-mock derrubado (SIGKILL); volta em $OUTAGE s"
  sleep "$OUTAGE"
  docker compose start agent-mock >/dev/null 2>&1
  meta "$dir" outage_end="$(now_utc)"
  echo "  agent-mock religado"
  wait "$load_pid"
  verify "$dir" --timeout 180
}

run_reentrega() {
  local dir=$1 rate=11 count=$((11 * DURATION))
  wait_lag_zero
  snapshot agent-mock > "$WORK/agent-mock.offsets"
  snapshot broker-outbound > "$WORK/broker-outbound.offsets"
  load "$dir" "$rate" "$count"
  sim verify --settle 0 < "$dir/lote.json" > /dev/null || true   # espera as respostas
  wait_lag_zero
  echo "  parando os consumidores e voltando os offsets para antes do lote"
  rewind_consumers "$count"
  meta "$dir" rewound_agent_mock="$(cat "$WORK/rewound-agent-mock")" \
              rewound_broker_outbound="$(cat "$WORK/rewound-broker-outbound")"
  sleep 3
  wait_lag_zero
  verify "$dir"
}

rate_of() { case $1 in base) echo 2 ;; maxima) echo 22 ;; *) echo 11 ;; esac; }

scenarios=("$@")
[[ ${#scenarios[@]} -eq 0 ]] && scenarios=(base pico agente-fora reentrega maxima)

docker compose up -d --build >/dev/null 2>&1   # imagem com o código atual
sim k6-pool > experiment/out/pool.json
say "Experimento $STAMP: ${scenarios[*]} × $RUNS rodada(s) de $DURATION s (resultados em $RESULTS)"
dirs=()
for scenario in "${scenarios[@]}"; do
  for run in $(seq 1 "$RUNS"); do
    dir=$RESULTS/$scenario-$run
    mkdir -p "$dir"
    say "$scenario #$run"
    prepare
    rate=$(rate_of "$scenario")
    meta "$dir" scenario="$scenario" run="$run" rate="$rate" count=$((rate * DURATION)) \
                duration_s="$DURATION" per_conversation="$PER_CONVERSATION" started_at="$(now_utc)" \
                outage_target_s="$OUTAGE" reset="$RESET"
    "run_$scenario" "$dir"
    python3 experiment/run_summary.py "$dir" || true
    dirs+=("$dir")
  done
done

say "Resultado ($RESULTS)"
if python3 experiment/run_summary.py "${dirs[@]}"; then
  echo "EXPERIMENTO OK"
else
  echo "EXPERIMENTO COM FALHAS (stderr: $WORK/sim.err, $WORK/k6.err)"; trap - EXIT; exit 1
fi
