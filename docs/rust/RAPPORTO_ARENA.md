# Arena EK su Rust: rapporto della tappa A (24/11)

## Cosa ti permette di fare
L'arena è il modo in cui il progetto decide se un bot è più forte di un altro: partite a coppie, posti
scambiati. Fino a oggi girava solo sul motore Python, e un'arena costava 2,5–9,5 ore per tappa, contro
0,7–1 ora di training.
Ora la ricerca del bot a mano gira in Rust, con o senza i prior della rete PPO. È lo stesso bot del campione
(`ekris_s12/ckpt_040000.pt`) e anche dell'avversario con cui giocherai.
- **A lavoro uguale** fa le stesse mosse di Python ed è circa 8,5 volte più veloce con il prior, circa 28 volte senza.
- **A tempo uguale** (0,4 s per mossa) esplora molte più continuazioni. In una prova breve (rete casuale,
  macchina carica) il prior ha fatto circa 400 iterazioni per decisione in 0,05 s. Python ne fa 96–129 in
  0,4 s su questa macchina.

Per il traguardo pratico (un avversario per allenarti) questa è la base: il bot che userai è già su Rust
per Evelynn–Kha'Zix. Mancano gli altri mazzi e un modo di giocarci contro sul motore Rust.

## Sigle
- **EK**: Evelynn contro Kha'Zix.
- **MCTS**: la ricerca che prova molte continuazioni.
- **PUCT**: la regola che sceglie quale continuazione provare.
- **Prior**: le preferenze della rete PPO sulle mosse, che dicono alla ricerca cosa provare prima.
- **Determinizzazione**: il bot non vede la mano dell'avversario né l'ordine dei mazzi. In ogni simulazione
  li pesca a caso, in modo coerente con ciò che sa.
- **Lavoro fisso**: un numero fisso di iterazioni per decisione (qui 50), invece di un tempo.

## Cosa è stato portato
`rust/rbsim-core/src/search.rs` è la traduzione di `riftbound/ai/net_mcts.py`, `handwritten.py` e
`ppo/prior_bot.py`, come li usa l'arena.

### Ricerca
- Copie determinizzate (`determinize`).
- Turno principale: albero sulle azioni e su ogni scelta interna (bersagli, modi, ordine dei trigger, ...).
- Showdown e catena: un passo di ricerca (`_search_now`), con la sonda `_choices_ahead`.
- Backup "best", mossa col Q più alto.
- Mulligan sul valore di tre mondi.

### Scelte nella partita vera
- **Piani**: la partita vera segue le opzioni più visitate dall'albero.
- **Ripresa da una scelta pendente**: le scelte che l'albero non ha visto si pesano rigiocando il tratto
  dall'ultima decisione principale, con lo stato salvato (`segment`) e il giornale delle risposte (`journal`).

### Valore e prior
- `table_value` alle foglie.
- Prior PPO su tutto il menu: Rust costruisce osservazione, descrittori e contesto; Python fa solo forward e
  softmax (`riftbound/rs/arena_rs.py`).

### Uso
- `scripts/diag/arena_mazzi.py --motore rust`: i matchup coperti vanno su Rust, gli altri restano su Python.
  I matchup coperti si riconoscono dal contenuto delle liste.
- La provenienza della run registra quale motore ha giocato ogni matchup.
- La ripresa di un'arena conta solo risultati comparabili: stessi checkpoint (per hash), budget, motore e regole.

## Parità (50 iterazioni, semi dell'arena, posti scambiati, PPOChooser sotto le scelte)
Per ogni partita si confrontano:
- la traccia della partita vera (stato canonico, finestra, menu, azione, scelte, estrazioni);
- ogni ricerca: menu, prior della radice, visite, Q e W di ogni figlio fino a tre livelli di scelte,
  valore della radice, mossa, numero di nodi, valori del mulligan.

| bot | semi | partite identiche | ricerche confrontate | Python | Rust |
|---|---|---|---|---|---|
| a mano | 40000–40039 | 40/40 | 2.335 | 510 s | 17,6 s |
| prior (rete dal seme 1) | 40000–40019 | 20/20 | 1.218 | 311 s | 32,3 s |
| a mano | 900001–900010 (tenuti da parte) | 10/10 | 547 | 126 s | 4,6 s |
| prior (rete dal seme 1) | 900001–900010 (tenuti da parte) | 10/10 | 568 | 165 s | 16,6 s |

Tempi tracciati, un processo. Risultati in `docs/rust/misure/arena_parita_*.json`.
In 6 partite i piani rispondono 230 volte e la ripresa da scelta pendente 9 volte: la parità li copre.
Il caso "ripresa su una copia di dichiarazione" non si è presentato in queste partite: è portato ma non provato.

### Un errore trovato e corretto durante la parità (seme 40003, scelta `trigger_order`)
Python etichetta un trigger con il suo `repr`. Quel testo contiene anche la carta che lo ha innescato, e se
è un token creato nella copia ha un `uuid` nuovo: ogni simulazione apre un nodo diverso.
In Rust l'etichetta riportava solo l'indice della carta, quindi due nodi si fondevano e un Q differiva
all'ultima cifra. Ora le carte hanno un `uuid` (nuovo a ogni creazione, conservato dalle copie) e l'etichetta
lo usa.

### Quando non si può confrontare
Il `repr` di un insieme Python (`combat_designated`) dipende dagli indirizzi di memoria. Se un trigger da
ordinare cade su un campo con due o più unità designate al combattimento, anche Python può dare chiavi
diverse fra una simulazione e l'altra. Rust lo tratta come insieme ordinato. Nelle 80 partite il caso non ha
dato differenze.

## Tempo per partita a lavoro fisso (`bench_arena_fisso.py`, 4 coppie, 50 iterazioni, un processo)

| motore | partite | totale | mediana per partita | chiamate alla rete |
|---|---|---|---|---|
| Python | 8 | 94,8 s / 88,8 s | 12,3 s / 11,4 s | 11.028 |
| Rust | 8 | 11,7 s / 10,0 s | 1,39 s / 1,29 s | 11.028 |

- Le chiamate alla rete sono le stesse: il lavoro è identico.
- Su Rust il forward della rete (batch 1, in Python) è il 62–64% del tempo; motore e ricerca sono circa
  il 36%, cioè circa 19 volte meno del motore Python.
- Il prossimo guadagno per l'arena col prior è quindi la rete, non il motore.
- Misure in `docs/rust/misure/arena_fisso_*.json` (questa macchina; sul Mac: `scripts/rust/arena_mac.command`).

## Sul Mac col campione (24/11, `scripts/rust/arena_mac.command`)
Apple M1 Max, checkpoint `runs/sett/ekris_s12/ckpt_040000.pt`.
- `tests/rust`: 19 passati.
- **Parità col checkpoint vero**: bot col prior, 50 iterazioni, semi 40000–40019 a posti scambiati:
  **20/20 partite identiche**.
- Tempo a lavoro fisso (50 iterazioni, 4 coppie, un processo):

| motore | totale 8 partite | mediana per partita |
|---|---|---|
| Python | 67,8 s / 69,1 s | 8,60 s / 8,79 s |
| Rust | 4,64 s / 4,69 s | 0,61 s / 0,61 s |

Sul Mac Rust è circa **14,6 volte** più veloce a parità di lavoro (8,5 su questa macchina): il forward
della rete costa meno sull'M1 e pesa meno sul totale.

## Forza a budget ridotto: arena mista a passo comune (metodo di Astra, 24/11)
Domanda: il campione su Rust a 0,030 s CPU per ricerca è forte almeno quanto il campione su Python a
0,400 s? Il primo tempo da provare viene da 0,400 / 14,6 ≈ 0,027 s, il rapporto misurato sul Mac.

Una partita con un lato per motore non si gioca su un solo motore: si giocano due copie della stessa
partita in due thread, una su Python e una su Rust (`scripts/rust/arena_mista.py`).
- Chi cerca a tempo è la copia del suo motore: Python per il bot "Python", Rust per il bot "Rust".
- Prima di partire col cronometro aspetta che l'altra copia sia ferma sulla stessa ricerca.
- Finita la ricerca, passa il numero esatto di iterazioni; l'altra copia rifà la ricerca con quel numero.
  A lavoro fisso i due motori sono identici, quindi le copie restano la stessa partita.
- Vale anche per reazioni e showdown; mulligan e decisioni forzate restano come sono.
- Controlli fuori dal cronometro:
  - a ogni scambio, l'identità della ricerca (posto, progressivo, finestra, turno);
  - a fine partita, traccia e ogni ricerca.

Una partita divergente sospende l'esito.

Prova in container: 12 partite con budget piccoli e rete casuale, tutte verificate e senza divergenze. Il bot
con più tempo vince sempre, in tutti e due i versi, come ci si aspetta: decide il tempo concesso.

Regole fissate prima (`scripts/rust/arena_mista.command`):
- 800 coppie, semi 70000–70799; sono esclusi quelli di calibrazione e di parità;
- posti scambiati nella coppia, primo giocatore bilanciato fra i semi;
- punteggio del bot Rust (1, 0,5, 0) e IC 95% sulle medie delle coppie;
- **promosso 0,030 s per Evelynn–Kha'Zix se il limite inferiore, prima dell'arrotondamento, supera 0,47**.

Lo script riporta anche le iterazioni per tipo di ricerca (media, P10, mediana, P90) e il tempo reale per
partita sul percorso Rust di produzione, con entrambi i bot a 0,030 s.
Il budget validato andrà ricontrollato sui matchup successivi.

### Divergenza del seme 70113 (Mac, 24/11): spiegata e corretta
- **Cosa:** una partita su ~220 ha dato una ricerca con numeri interni diversi nei due motori (il bot "Python",
  turno 15). Albero, visite, Q e mossa uguali; la partita è rimasta identica.
- **Riproduzione** (`scripts/rust/arena_mista_riprova.py`, conteggi registrati, checkpoint del campione): 4 simulazioni
  su 57 valutano diversamente la stessa posizione finale (0,955 contro 0,565). Passo per passo, le copie sono
  uguali fino al combattimento; lì una scelta interna della ricerca ("optional:give_temporary_assault" di un
  token Shadow Clone) va in modo diverso.
- **Causa: Python.** L'etichetta di un'opzione "ordine dei trigger" è il `repr` del trigger, che contiene il campo
  di battaglia e il suo insieme `combat_designated`. Python stampa un insieme nell'ordine degli indirizzi di
  memoria: su ogni copia la stessa opzione ha una chiave diversa e la ricerca apre nodi nuovi a caso. Rust
  (insieme ordinato) li riunisce. È il caso segnalato sopra come "non confrontabile".
- **Correzione minima anche in Python** (regola del congelamento: una prova che deve continuare su Python):
  `net_mcts._label` stampa gli insiemi in ordine (`_stable_repr`), identico al `repr` in tutto il resto. Cambia
  solo questi casi, dove prima decideva l'indirizzo di memoria. Test: `tests/test_search_labels.py` (fallisce
  senza la correzione). Con la correzione il seme 70113 rigiocato è identico, traccia e ricerche.
- **Conseguenza per la prova**: la partita 70113 conta (`--spiegata 70113:A`); le partite già giocate restano
  valide, il bot Python è lo stesso salvo questi casi rari. Dal rilancio vale la correzione.

### Divergenze gestite dall'arena stessa (24/11)
Non si inseguono una per una:
- **solo nei numeri delle ricerche** (stessa partita nelle due copie): a fine arena ciascuna si rigioca coi
  conteggi registrati e il codice attuale (`arena_mista_riprova.spiega`). Se ora le copie coincidono è spiegata
  dalle correzioni fatte dopo, la partita conta, e la spiegazione va in `<out>.spiegate.json` (col commit);
- **nella partita** (le copie si sono separate): la partita non ha un risultato valido e al rilancio si rigioca;
- una divergenza che resta anche col codice attuale è un problema nuovo: tiene l'esito sospeso e va guardata.

## Da fare (in ordine)
1. **Forza a budget ridotto**: `bash scripts/rust/arena_mista.command` sul Mac.
2. **Rengar, Ivern, Sett** (con le sideboard), per arena e raccolta PPO su tutti e cinque i mazzi.
3. **Giocare contro il bot su Rust**: oggi la partita interattiva (coach) usa il motore Python.
