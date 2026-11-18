| Cenário | Rodadas | Mensagens | Perdidas | Duplicadas | Fora de ordem | Vazão (resp/s) | Ingestão p95 (ms) | Ponta a ponta p50 (s) | p95 (s) | p99 (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| Base (2 msg/s) | 3 | 360 | 0 | 0 | 0 | 2.0 ± 0.0 | 11.0 ± 0.8 | 0.22 ± 0.01 | 0.49 ± 0.01 | 0.50 ± 0.00 |
| Pico (11) | 3 | 1980 | 0 | 0 | 0 | 11.0 ± 0.0 | 14.5 ± 8.3 | 0.27 ± 0.00 | 0.49 ± 0.01 | 0.62 ± 0.20 |
| Pico, agente fora (11) | 3 | 1980 | 0 | 0 | 0 | 11.0 ± 0.0 | 10.4 ± 0.7 | 0.33 ± 0.00 | 8.89 ± 0.20 | 11.32 ± 0.19 |
| Reentrega forçada (11) | 3 | 1980 | 0 | 0 | 0 | 11.0 ± 0.0 | 9.6 ± 0.1 | 0.26 ± 0.00 | 0.49 ± 0.00 | 0.51 ± 0.00 |
| Máxima (22) | 3 | 3960 | 0 | 0 | 0 | 21.9 ± 0.1 | 8.3 ± 0.1 | 0.27 ± 0.00 | 0.49 ± 0.00 | 0.51 ± 0.00 |

Agente fora do ar (média ± desvio das rodadas):

| Queda medida (s) | Mensagens na queda | p95 fora da queda (s) | Recuperação (s) | Hipótese por rodada |
|---|---|---|---|---|
| 11.4 ± 0.0 | 125 ± 0 | 0.49 ± 0.01 | 0.4 ± 0.0 | confirmada, confirmada, confirmada |
