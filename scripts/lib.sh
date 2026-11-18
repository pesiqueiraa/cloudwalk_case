# Funções comuns ao chaos.sh e ao experiment.sh. Uso: source "$(dirname "$0")/lib.sh"
# Espera estar em cloudwalk_case/ e ter $WORK (pasta temporária) definido.

sim() { docker compose run --rm -T simulator "$@" 2>>"$WORK/sim.err"; }
sql() { docker compose exec -T postgres psql -U helpdesk -d helpdesk -tAq -c "$1"; }
rpk() { docker compose exec -T redpanda rpk "$@"; }

# Soma o atraso (lag) do grupo nos tópicos principais
lag() {
  rpk group describe "$1" 2>/dev/null | awk '$1 ~ /^helpdesk\.(inbound|outbound)$/ && $6 ~ /^[0-9]+$/ {s += $6} END {print s + 0}'
}

wait_lag_zero() {
  for _ in $(seq 1 60); do
    if [[ $(lag agent-mock) == 0 && $(lag broker-outbound) == 0 ]]; then return 0; fi
    sleep 1
  done
  echo "consumidores ainda com atraso depois de 60 s" >&2
  return 1
}

# Depois do stop, o consumidor só sai do grupo quando a sessão expira; o seek exige grupo vazio
wait_group_empty() {
  for _ in $(seq 1 60); do
    [[ $(rpk group describe "$1" 2>/dev/null | awk '$1 == "STATE" {print $2}') == Empty ]] && return 0
    sleep 1
  done
  echo "grupo $1 não esvaziou em 60 s" >&2
  return 1
}

# Offsets atuais do grupo, no formato do "rpk group seek --to-file" (partição sem commit = 0)
# Espera o grupo estável com as 3 partições: logo depois de um SIGKILL ele ainda está rebalanceando
snapshot() {
  local out
  for _ in $(seq 1 60); do
    out=$(rpk group describe "$1" 2>/dev/null)
    if [[ $(awk '$1 == "STATE" {print $2}' <<< "$out") == Stable ]] &&
       [[ $(awk '$1 ~ /^helpdesk\.(inbound|outbound)$/ && $3 ~ /^[0-9]+$/' <<< "$out" | wc -l) -eq 3 ]]; then
      awk '$1 ~ /^helpdesk\.(inbound|outbound)$/ {print $1, $2, $3}' <<< "$out"
      return 0
    fi
    sleep 1
  done
  echo "grupo $1 não estabilizou em 60 s" >&2
  return 1
}

# Volta os offsets dos dois consumidores para os arquivos "$WORK/<grupo>.offsets" (do snapshot) e
# religa os consumidores. Falha se o seek não voltou pelo menos $1 registros em algum grupo.
# O rpk sai com 0 mesmo quando o seek falha: confere a coluna ERROR e quantos registros voltaram.
rewind_consumers() {
  local min_back=$1 failed="" back
  docker compose stop agent-mock broker-outbound >/dev/null 2>&1
  for group in agent-mock broker-outbound; do
    wait_group_empty "$group" || { failed="$failed $group"; continue; }
    docker compose exec -T redpanda sh -c "cat > /tmp/seek-$group.txt" < "$WORK/$group.offsets"
    rpk group seek "$group" --to-file "/tmp/seek-$group.txt" > "$WORK/seek-$group.out"
    back=$(awk 'NR > 1 && $3 ~ /^[0-9]+$/ && $4 ~ /^[0-9]+$/ {n += $3 - $4} END {print n + 0}' "$WORK/seek-$group.out")
    echo "  $group: $back registro(s) a reentregar"
    echo "$back" > "$WORK/rewound-$group"
    if grep -q ERROR "$WORK/seek-$group.out" || (( back < min_back )); then
      cat "$WORK/$group.offsets" "$WORK/seek-$group.out"
      failed="$failed $group"
    fi
  done
  # Religa sempre, mesmo se o seek falhou: o script não pode deixar o ambiente parado
  docker compose start agent-mock broker-outbound >/dev/null 2>&1
  if [[ -n $failed ]]; then echo "seek falhou em:$failed" >&2; return 1; fi
}
