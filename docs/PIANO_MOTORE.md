# Il motore: il groviglio e il piano per scioglierlo

Scritto il 2026-11-17, dopo la pulizia della PR #28. È il piano di un lavoro
lungo, da eseguire a fasi in più sessioni. Stato e priorità restano in
`STATO.md`; qui c'è il problema, misurato, e come risolverlo. Chi esegue legge
tutto prima di toccare il codice. A lavoro finito il file va in `docs/archivio/`.

## 1. Il problema in breve

Il motore funziona ed è verificato (audit D1-D58, 1790 test), ma la sua
struttura è degradata:

1. **`riftbound/core/loop.py` è un blocco unico**: 8.448 righe, una sola classe
   (`GameLoop`) con 344 metodi.
2. **Tra `effects.py` e il motore manca un confine.** Gli effetti, invece di
   chiedere al motore poche operazioni ufficiali, usano direttamente i suoi
   ingranaggi interni (i metodi con il trattino basso). E il motore, a sua
   volta, usa funzioni interne di `effects.py`. Tutto parla con tutto.
3. **Anche i test conoscono gli ingranaggi**: chiamano i metodi interni
   direttamente, quindi ogni riorganizzazione rompe test che sono giusti.

Conseguenze: il progetto è difficile da consultare, ogni modifica richiede di
ricostruire a mano chi dipende da cosa, e alcune sequenze di regole sono
ricopiate a mano in decine di effetti (se una copia sbaglia, la regola si rompe
in silenzio).

## 2. I numeri (misurati il 17/11, `main` + PR #28)

Come sono misurati: Appendice B.

### 2.1 `loop.py`

- 8.448 righe; `GameLoop` va dalla riga 458 alla fine; 344 metodi, 337 privati.
- In cima al file: `EffectContext` (250 righe), helper di modulo, il controllo
  di coerenza con `engine_vocab.py` (righe 25-100 circa).
- I metodi più lunghi: `_check_condition` 445 righe (100 rami
  `if ctype == ...`), `_apply_action` 222, `_apply_activated_ability` 140,
  `activatable_abilities` 124, `_resolve_card_effects` 118,
  `_phase_beginning_steps` 112.

Il codice è organizzato per sistemi di regole, non per fasi del turno:

| Area | Righe | Metodi |
|---|---|---|
| Costi e pagamenti (sconti, aure, kicker, costi aggiuntivi, flow, tasse) | ~1.300 | 66 |
| Trigger ed effetti (trigger, ritardati, riflessivi, risoluzione) | ~810 | 41 |
| Giocare carte (da ogni zona: mano, cimitero, bando, coperte, cima del mazzo) | ~810 | 48 |
| Turno e partita (fasi, pesca, punti, vittoria, leggende) | ~810 | 39 |
| Abilità attivate (quali, costi, risoluzione) | ~740 | 29 |
| Passivi e condizioni (`_check_condition` da sola 445) | ~730 | 12 |
| Chain, showdown, combattimento | ~670 | 26 |
| Scelte e giornale (`choose`, segmenti, replay, scelte dichiarate) | ~380 | 20 |
| Morte, danno, sostituzioni | ~300 | 7 |
| Carte coperte (Hidden) | ~260 | 15 |
| Gear ed equip, movimento, battlefield, scarti, registrazione | ~500 | 40 |
| `_apply_action` e altro | ~250 | 2 |

### 2.2 Chi usa gli ingranaggi interni del motore (codice, test esclusi)

117 dei 337 metodi privati di `GameLoop` sono usati da fuori `loop.py`:

| File | Metodi distinti | Chiamate |
|---|---|---|
| `core/effects.py` | 89 | 428 |
| `core/legality.py` | 20 | 32 |
| `ai/` (base_agent, ismcts, net_mcts, simple_trade, coach, scenari, pregame, monte_carlo) | ~20 | 33 |
| `core/decisions.py`, `scripts/choice_audit.py`, `scripts/baseline_ab.py` | 3 | 6 |

In `effects.py`, 179 delle 317 funzioni entrano nel motore. Le 89 chiamate,
per tipo:

| Tipo | Metodi | Chiamate | Esempi |
|---|---|---|---|
| Azioni (cambiano la partita) | 54 | 173 | `_route_deaths`, `_play_unit`, `_move_unit_by_effect`, `_pay_generic_power`, `_empower` |
| Domande (sola lettura) | 24 | 163 | `_locate_unit` (74 da sola), `_can_ready`, `_equip_cost`, `_is_empowered` |
| Registrazioni (da ricordarsi a mano) | 5 | 59 | `_note_chosen` (31), `_note_recycled`, `_note_revealed`, `_note_banished` |
| Trigger lanciati a mano | 6 | 33 | `_fire_leaves_board`, `_fire_attached`, `_fire_readied` |

### 2.3 Anche al contrario

`loop.py` importa da `effects.py` 13 nomi, 10 dei quali privati (`_amount`,
`_passes_filter`, `_zone_card_matches`, `_zone_effect_card_ok`, `_gear_entries`,
`_choosable`, `_fallback_units`, `_return_gear`, `_zone_value`,
`_SINGLE_UNIT_TARGETS`), quasi tutti dentro le funzioni per aggirare l'import
circolare. Il groviglio va nei due sensi.

### 2.4 I test

113 file di test chiamano direttamente circa 141 metodi privati, per circa
1.720 chiamate (i più: `test_corpus_radiance.py` 204, `test_corpus_vendetta.py`
183). Rinominare o unire un metodo interno rompe questi test anche quando il
comportamento resta giusto.

### 2.5 Come è cresciuto

| Data | Metodi interni usati da `effects.py` (misura approssimata) | Righe di `loop.py` |
|---|---|---|
| 10 agosto | 0 | 1.827 |
| 25 ottobre | 7, poi 31 nello stesso giorno | 3.080 → 3.910 |
| 26 ottobre | 51 | 5.093 |
| 10 novembre | 92 | 8.268 |
| 17 novembre | 94 (89 con la misura precisa) | 8.448 |

Il salto è del 25-26 ottobre, durante la revisione delle carte una per una.

## 3. Perché è un problema, in concreto

1. **Sequenze ricopiate a mano.** Ogni effetto che sceglie unità deve chiamare
   `_note_chosen` (conta le scelte di nemici, fa scattare "quando vengo
   scelto"): 31 punti lo fanno a mano, e uno che se lo dimentica rompe la
   regola senza errori. Lo stesso per "gioca un'unità pagandone il costo"
   (`_play_unit` insieme a `_pay_card` / `_can_pay_card` / `_effective_cost`
   in diverse funzioni), per le morti (`_route_deaths` in 15 funzioni, con
   `_locate_unit` e `_note_chosen` intorno), per i movimenti
   (`_move_unit_by_effect` in 11).
2. **Bug già successi per questo motivo.** BACKLOG B (chiuso, in
   `docs/archivio/BACKLOG_chiuso.md`): 30 effetti sceglievano un'unità senza
   passare da `loop.choose`, cioè senza far scegliere il giocatore.
3. **Orientarsi costa.** Per capire cosa c'è in `loop.py` serve uno script che
   lo analizzi; ogni sessione spende una buona parte del suo lavoro a
   ricostruire la mappa.
4. **Cambiare un metodo interno è rischioso**: niente dice chi ne dipende, e i
   test che lo chiamano direttamente si rompono anche quando la regola è
   giusta.

## 4. Perché è successo, e perché l'audit non l'ha visto

- Ogni sessione partiva da `STATO.md` con un compito preciso (correggi D-n,
  fai passare il test). Il modo più rapido era chiamare il metodo interno che
  c'era già. Ogni scelta era ragionevole; il problema è la somma.
- Il progetto aveva un solo criterio di successo, la fedeltà alle regole
  misurata dai test, ed è stato rispettato. La struttura non aveva criteri,
  test o righe in `STATO.md`.
- `docs/audit/AUDIT.md` dichiara il suo perimetro: il motore contro le Core
  Rules e il testo stampato. La struttura non ci rientrava, e nessun documento
  del progetto la nomina mai. Chi ha fatto l'audit ha letto `loop.py` e
  avrebbe dovuto segnalarlo almeno tra le cose "non controllate".
- Lezione: un controllo che nessuno ha il compito di fare non viene fatto. Per
  questo la Fase 0 rende il controllo automatico (il test a cricchetto).

## 5. Obiettivo e criteri di riuscita

Misurabili, e verificati dal test a cricchetto:

- Nessun file in `riftbound/core/` sopra le 1.500 righe (`effects.py` compreso,
  a fine Fase 4).
- `effects.py` e `ai/` usano solo l'API pubblica del motore: 0 metodi privati
  (oggi 89 e circa 20). `legality.py` (20): decidere in Fase 3 se usa l'API o
  diventa parte del motore.
- Comportamento identico: l'impronta delle partite (Fase 0) non cambia, salvo
  deviazioni documentate (sezione 7, Fase 3).
- Tutti i test verdi, nessun test tolto o saltato, nessuna golden game
  rigenerata.
- Velocità: non peggiora più del 5% (tempo dell'impronta prima e dopo).

## 6. Vincoli, da rispettare in ogni fase

- **Nessun cambio di regole "già che ci sei".** Un cambio di comportamento è
  una deviazione: test in `tests/audit/` e commit separato, come da `STATO.md`.
- **Import pubblici invariati.** Fuori dal motore si importa da
  `riftbound.core.loop`: `GameLoop` (116 import), `EffectContext` (49),
  `NO_MORE` (3), `_ADD_VERBS` (2). Devono continuare a funzionare.
- **Import circolari.** `loop.py` importa da `effects.py` dentro le funzioni
  apposta; spostando codice, mantenere quegli import locali finché la Fase 4
  non sposta gli helper condivisi in un modulo neutro.
- **Copie e processi.** `GameLoop` e lo stato vengono copiati con `deepcopy`
  (dichiarazioni in chain, B32; `state.py`), e il self-play usa più processi:
  ogni classe nuova sta a livello di modulo.
- **Controllo di coerenza con `engine_vocab.py`** (in cima a `loop.py`): deve
  continuare a fallire all'import se trigger o condizioni non sono allineati.
- **Test.** Mai cambiare la logica di un test. Se un metodo privato usato dai
  test viene rinominato, si aggiornano i test nello stesso commit, solo nel
  nome.
- **Niente fork** (non funziona su Windows): il giornale delle scelte resta
  com'è.

## 7. Il piano

Ogni fase ha il suo branch e la sua PR. Ogni passo è un commit, con test verdi,
impronta identica e cricchetto rispettato. Ci si può fermare dopo qualsiasi
passo e il progetto resta coerente.

### Protezione del lavoro

- Punto di partenza: il commit `e72318e` (`main` dopo la PR #28), con il tag
  `pre-ristrutturazione` se l'utente l'ha creato. Per tornarci:
  `git checkout e72318e`.
- `main` cambia solo con il merge della PR di una fase, con test verdi,
  impronta identica e l'ok dell'utente. Mai push diretti né force push su
  `main`.
- Branch corti: una fase, una PR, merge; la fase dopo riparte da `main`.
  Niente branch lunghi che divergono dal lavoro sul bot e sulle regole, che
  intanto continua su `main`.
- Il riferimento dell'impronta si rigenera dal `main` di partenza di ogni fase:
  se nel frattempo sono entrati fix di regole, il comportamento giusto è
  cambiato. Una PR di fase in conflitto si riallinea a `main` e si rifà il
  confronto.

### Fase 0: reti di sicurezza (prima di toccare il motore)

1. **Impronta delle partite**, `scripts/diag/impronta.py`:
   - qualche centinaio di partite a seed fisso su tutti gli accoppiamenti dei
     sei mazzi (`precon_zed`, `precon_shen`, `competitive_evelynn`,
     `competitive_khazix`, `competitive_kaisa`, `competitive_kennen`), con gli
     agenti `random` e `simple_trade` su entrambi i posti; se c'è torch, anche
     una ventina di partite con `net_mcts` e una rete non allenata a seed fisso,
     per coprire il giornale e il replay delle scelte nascoste;
   - per ogni partita un hash della traccia completa: ogni decisione (chi, che
     tipo, opzioni offerte, scelta), lo stato a fine turno, il risultato
     (`scripts/trace_game.py` e `data/writer.py` danno già quasi tutto);
   - `--save` scrive il riferimento, `--check` confronta, elenca le partite
     diverse e, per la prima, stampa la prima decisione che diverge;
   - prova che funzioni: cambiare di proposito un dettaglio (un pareggio
     risolto al contrario), vedere che `--check` lo segnala, annullare;
   - il riferimento si salva sul commit di partenza e si committa insieme allo
     script; stampa anche il tempo totale (per il vincolo sulla velocità).
   Le golden game coprono solo Zed contro Shen: da sole non bastano.
2. **Test a cricchetto**, `tests/test_struttura.py`:
   - misura con `ast` (Appendice B), per file: metodi privati di `GameLoop`
     usati fuori dal motore; righe di ogni file in `riftbound/core/`;
   - i riferimenti stanno nel test; ogni numero può solo scendere. Quando
     scende, si abbassa il riferimento nello stesso commit;
   - tetto di 1.500 righe per file, con una lista di eccezioni che può solo
     accorciarsi (all'inizio `loop.py`, `effects.py`).
3. **`CLAUDE.md`**: aggiungere che a fine fase si riportano i numeri del
   cricchetto, e che un riferimento non si alza mai senza dirlo all'utente.

### Fase 1: dividere `loop.py` (solo spostamenti, zero logica)

- `riftbound/core/loop.py` diventa il pacchetto `riftbound/core/loop/`;
  `__init__.py` riesporta `GameLoop`, `EffectContext`, `NO_MORE`, `_ADD_VERBS`.
- Tecnica: ogni area diventa una classe "mixin" in un suo file, con i metodi
  copiati identici (niente riformattazione, niente rinomine);
  `class GameLoop(...)` in `game.py` le eredita tutte.
- File previsti (righe circa):
  `context.py` (`EffectContext`, 250), `_common.py` (helper di modulo e
  controllo di coerenza con `engine_vocab`), `game.py` (costruzione, ciclo
  principale, `_apply_action`, 600), `choices.py` (scelte e giornale, 380),
  `turn.py` (810), `costs.py` (1.300; se serve, dividerlo tra "quanto costa" e
  "come si paga"), `triggers.py` (810), `play.py` (810), `abilities.py` (740),
  `conditions.py` (`_check_condition`, 445), `passives.py` (290),
  `chain.py` (chain, showdown, combattimento, 670), `deaths.py` (300),
  `hidden.py` (260), `board.py` (movimento, gear, battlefield, scarti, 400).
  L'assegnazione esatta metodo → file si fa come primo passo e si scrive in
  questo file (appendice C).
- Ordine degli spostamenti, dal meno al più collegato: `context.py`, `board.py`,
  `deaths.py`, `hidden.py`, `chain.py`, `abilities.py`, `play.py`,
  `triggers.py`, `passives.py`, `conditions.py`, `costs.py`, `turn.py`,
  `choices.py`. Quel che resta è `game.py`.
- Controllo in più a ogni passo: l'elenco ordinato dei nomi di `GameLoop`
  (`dir(GameLoop)`) è identico a prima. Nessun metodo perso o duplicato.
- Finita quando: nessun file del pacchetto sopra 1.500 righe, impronta
  identica, `loop.py` tolto dalle eccezioni del cricchetto.

### Fase 2: l'API del motore

- Per ognuno degli 89 metodi usati da `effects.py`: tipo (azione, domanda,
  registrazione, trigger) e operazione dell'API che lo sostituisce. Tabella
  nell'appendice C.
- Principio: **ogni azione fa la sequenza completa**, registrazioni e trigger
  compresi. Esempi: "scegli unità" chiede al giocatore (`choose`) e registra
  la scelta (`_note_chosen`); "gioca unità pagando" verifica, paga e gioca;
  "uccidi" instrada le morti e fa scattare "lascia il campo"; "sposta" muove e
  lancia i trigger di movimento. Le domande diventano metodi pubblici di sola
  lettura (`locate_unit`, ...).
- Obiettivo: 20-30 operazioni e una quindicina di domande, tutte in un solo
  file (`loop/api.py`): il posto dove si legge cosa un effetto può chiedere al
  motore.
- Prima di scriverle: per ogni operazione, trovare in `effects.py` tutte le
  sequenze fatte a mano che sostituisce (co-occorrenze nella stessa funzione,
  Appendice B) e annotarne le varianti. **Una variante è un possibile bug**:
  si annota qui, non si corregge in silenzio.
- In questa fase l'API chiama i metodi privati che ci sono già: nessun cambio
  di logica, `effects.py` ancora non toccato.
- A fine fase: presentare all'utente l'elenco delle operazioni e delle
  varianti trovate, in parole semplici, prima della Fase 3.

### Fase 3: portare `effects.py` sull'API, una famiglia alla volta

- Ordine, dal rischio più basso: domande (solo rinomina), registrazioni (che
  spariscono dentro le azioni), movimento, morte e danno, scelte, gioco e
  pagamenti, trigger.
- Un commit per famiglia; impronta identica; il cricchetto scende.
- **Se l'impronta cambia**, un effetto faceva la sequenza in modo diverso
  dagli altri. Stop: trovare le carte coinvolte, confrontare testo stampato e
  Core Rules.
  - Era sbagliato il comportamento vecchio: è una deviazione, quindi test di
    audit (D59 e seguenti), fix in un commit separato, aggiornare il
    riferimento dell'impronta con il motivo, dirlo all'utente.
  - È sbagliata l'API: si corregge l'API.
- Poi `ai/` (circa 20 metodi) e `legality.py` (20), con lo stesso metodo.

### Fase 4: `_check_condition`, `effects.py`, il verso opposto

- `_check_condition` (100 rami `if ctype == ...`) diventa una tabella
  `tipo → funzione` in `loop/conditions.py`, come `REGISTRY` degli effetti; il
  controllo di coerenza con `engine_vocab` si ricava dalle chiavi della
  tabella.
- Gli helper di `effects.py` usati dal motore (filtri, quantità, zone: i 10
  privati della 2.3) vanno in un modulo neutro (es. `core/targeting.py`) usato
  da entrambi: spariscono gli import dentro le funzioni e il ciclo.
- `effects.py` (5.891 righe, 317 funzioni) diventa un pacchetto diviso per
  famiglia di effetti, `REGISTRY` invariato. Solo dopo la Fase 3, altrimenti
  si sposta il groviglio invece di scioglierlo.

### Fase 5: chiusura

- README: una tabella "dove sta cosa", una riga per file di `loop/` e
  `effects/`. Nessun documento nuovo.
- `STATO.md` aggiornato. Decidere con l'utente se l'impronta diventa una golden
  permanente (consiglio: sì, ridotta, sui mazzi in uso).
- Il cricchetto resta per sempre. Questo file va in `docs/archivio/`.

## 8. Cosa non fare

- Cambiare regole o correggere bug di passaggio, fuori dalla procedura della
  Fase 3.
- Riformattare il codice spostato: i diff diventano illeggibili.
- Mescolare fasi o aree nello stesso commit.
- Rigenerare golden, togliere o saltare test, alzare un riferimento del
  cricchetto senza dirlo all'utente.
- Toccare training e rete: fuori perimetro.

## 9. Come lavorare

- Leggere `STATO.md`, poi questo file. Seguire `CLAUDE.md` (comunicazione
  breve, niente narrazione).
- Fermarsi e chiedere all'utente se: l'impronta cambia senza spiegazione; una
  fase richiede di cambiare la logica di un test; un numero del cricchetto
  dovrebbe salire; una fase si rivela molto più grande del previsto.
- A fine fase: aggiornare "Avanzamento" qui sotto e `STATO.md`.

## 10. Avanzamento

- [ ] Fase 0: impronta, cricchetto, `CLAUDE.md`
- [ ] Fase 1: `loop.py` diviso
- [ ] Fase 2: API del motore (e varianti trovate, presentate all'utente)
- [ ] Fase 3: `effects.py`, `ai/`, `legality.py` sull'API
- [ ] Fase 4: tabella delle condizioni, modulo neutro, `effects.py` diviso
- [ ] Fase 5: chiusura

## Appendice A: i metodi interni più usati da `effects.py` (17/11)

`_locate_unit` 74, `_note_chosen` 31, `_route_deaths` 15, `_play_unit` 14,
`_move_unit_by_effect` 13, `_fire_leaves_board` 12, `_can_ready` 12,
`_pay_generic_power` 9, `_note_recycled` 9, `_equip_cost` 8,
`_can_pay_generic_power` 7, `_note_revealed` 7, `_note_banished` 7,
`_fire_attached` 7, `_reflexive` 7, `_is_empowered` 7, `_empower` 7,
`_fire_readied` 7, `_before_deck_reveal` 6, `_pay_card` 6.

## Appendice B: come sono misurati i numeri

- Metodi privati di `GameLoop`: con `ast`, i metodi della classe il cui nome
  inizia con `_` (non `__`).
- Uso da un file: con `ast`, gli accessi ad attributo `x._nome` dove `_nome` è
  un metodo privato di `GameLoop` e il file non definisce una funzione con lo
  stesso nome. Commenti e stringhe non contano. Distinti = nomi diversi;
  chiamate = occorrenze.
- La crescita nel tempo (2.5) e i numeri sui test (2.4) sono una misura più
  grezza, con espressioni regolari: per questo dicono 94 dove la misura
  precisa dice 89.
- Co-occorrenze: per ogni funzione di `effects.py`, l'insieme dei metodi
  interni che chiama; per un metodo, quali altri compaiono nelle stesse
  funzioni.

## Appendice C: assegnazioni (da compilare in Fase 1 e 2)

Metodo → file (Fase 1). Metodo → tipo → operazione dell'API (Fase 2).
Varianti delle sequenze fatte a mano, con le carte coinvolte (Fase 2).
