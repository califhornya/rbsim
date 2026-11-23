# Porting Rust · prima consegna: Gold in D59 e D62

Riferimento: motore Python a `6427b90`, non modificato. Rust: `rust/rbsim-core`
più l'estensione `riftbound_rs` compilata in release.

## Riprodurre

```bash
cd rust/rbsim-py && maturin develop --release && cd ../..
taskset -c 2 python scripts/rust/consegna1.py --ripetizioni 300
python -m pytest -q tests/rust
```

- Lo script costruisce ogni posizione con `tests/audit/audit_helpers.py`, la gioca in Python con traccia e ne esporta lo stato iniziale canonico.
- Rust importa quello stato (`Game.from_canonical`) e gioca lo stesso segmento. Le decisioni registrate di `Scripted` arrivano tramite un agente di replay, che controlla il menu Rust prima di applicarle.
- Le due tracce si confrontano evento per evento e il confronto si ferma alla prima differenza.
- Uscite:
  - `docs/rust/consegna1/<caso>_{python,rust}.jsonl`: le tracce appaiate. A ogni decisione registrano posto, finestra, hash dello stato canonico, menu ordinato, azione e indice.
  - `docs/rust/misure/consegna1.json`: osservazioni e tempi.
- Il segmento è questo: le azioni del giocatore di turno, la fine del turno (showdown, combattimento, cleanup), l'inizio del turno dopo, le sue azioni, la sua fine e l'inizio del terzo turno. In D59 il segmento comprende un combattimento.

## Posizioni ed esito
Su 3 posizioni su 3 le tracce sono identiche: prima differenza nessuna, nessun errore Rust.

| Caso | Posizione | Gold eseguito | Movimento dopo la scelta | Finestra |
|---|---|---|---|---|
| D59 | A muove Traveling Merchant su BF0, dove c'è Vex di B. Il trigger del movimento apre la catena; nella reazione A sceglie Gold. | no | chiuso dentro la finestra: lo showdown e il combattimento girano lì (il Merchant muore) | **non** conta un pass: l'impronta di `_use_ability_now` cambia, il passo vale "kept" e A tiene la priorità |
| D59b | Come D59, ma su un campo vuoto dove A ha già segnato in questo turno. | no | chiuso dentro la finestra (showdown, conquista senza punto) | conta un pass: l'impronta non cambia e la priorità passa a B |
| D62 | B gioca Punch First (catena senza movimento in sospeso). B passa, A usa Gold (eseguito, Gold sacrificato), A passa. | sì | — | B **non** riceve di nuovo priorità: la catena si risolve (§339.1, il difetto D62) |

Rust riproduce le deviazioni D59 e D62 così come sono a `6427b90`, per scelta d'impianto.

D59 ha due esiti nel riferimento, secondo che chiudere il movimento cambi o no l'impronta:
- quando la cambia, la scelta di Gold vale come un'abilità Add riuscita: chi l'ha scelta tiene la priorità senza che l'abilità sia stata eseguita;
- quando non la cambia, la finestra conta un pass, come descritto in AUDIT.md.

## Tempi su un core
Macchina: container Linux, Intel Xeon a 2,1 GHz, Python 3.13. Ogni caso è stato ripetuto 300 volte, alternando Python e Rust a ogni ripetizione, senza traccia. I valori sono mediane in ms, con la deviazione standard fra parentesi.

| Caso | Python segmento | Rust segmento | Rapporto | Python caricamento | Rust caricamento |
|---|---|---|---|---|---|
| D59 | 4,12 (0,84) | 0,29 (0,18) | ×14,4 | 0,55 | 0,33 |
| D59b | 2,62 (0,47) | 0,19 (0,04) | ×13,6 | 0,42 | 0,25 |
| D62 | 2,13 (0,67) | 0,12 (0,12) | ×17,5 | 0,41 | 0,25 |

Come leggere i tempi:
- Il segmento include, in entrambi i motori, il calcolo del menu legale a ogni decisione. In Rust include anche l'attraversamento PyO3 della chiamata.
- Il caricamento si misura a parte:
  - in Python è la costruzione della posizione con `audit_helpers`;
  - in Rust è il parsing dello stato canonico in JSON più le decisioni da rigiocare.
- Il rapporto vale per questi segmenti brevi, senza rete né osservazione. Non è una stima del guadagno su una run PPO, perché lì l'aggiornamento della rete pesa circa metà del ciclo (F0). Il dato che conta arriva con le misure EK di fine incarico.

## Correzione emersa durante la prova
Il dump di Rust usciva con le chiavi in ordine alfabetico, mentre Python segue l'ordine dei campi. Questo cambiava la numerazione canonica delle copie della stessa carta: per esempio la Gust in mano risultava `:2` invece di `:1`. Ora `serde_json` usa `preserve_order`. Le 20 partite EK del replay differenziale restano identiche (20/20).
