# STATO

Aggiornato: 2026-11-13 (primo training fallito e diagnosticato; ricetta nuova in prova).

## Obiettivo
Motore Riftbound fedele a `docs/rules/CORE_RULES.md` e al testo stampato delle
carte; su quello, una rete allenata in self-play sui due mazzi competitive.
Documento di riferimento: `docs/audit/AUDIT.md` (l'intestazione riassume lo stato).

## Decisioni prese
- Una deviazione = un test in `tests/audit/` che gioca la situazione + un commit
  di fix (verificabile e reversibile). Eccezione: D35-D49, soli dati, un commit.
- Golden game rigenerate solo per cambi voluti, motivo per partita nel commit.
  D19-D21, D23, D26, D29, D34: scelte tecniche, motivate in AUDIT.md.
- Q1–Q4, D27 (utente): priorità §337.4; Shadow Order Disciple invariato; cap
  dei turni = pareggio; Keeper of Law conta solo le unità di chi la gioca;
  Patched Porobot è unità e gear insieme.
- (Utente, 2026-11-12) Otto mazzi non precon eliminati (con agenti Pyke e
  Diana), correzioni di carte tenute; training sui due mazzi competitive.
- L'agente random è seminato dal seed della partita (riproducibile).
- Commenti di Codex: verificati uno per uno prima di agire.
- Flow: costo alternativo con i soli sconti di aura; gli altri modificatori
  §356.3-4 lasciati aperti perché nessuno è nei quattro mazzi.
- Scelte nella ricerca: nodi dell'albero per opzione con chiave (tipo, carta,
  descrizione), non per indice: le copie determinizzate mostrano altre carte.
  Prior uguali tra le opzioni (con 0.75 alla baseline le visite restavano
  sulla baseline anche quando valeva meno).
- Scelte nascoste: decise quando la partita le chiede, rigiocando il tratto
  dall'ultima decisione del turno (giornale nel motore; un fork del processo
  non funziona su Windows).
- Training: si parte senza aspettare il BACKLOG vuoto (di fatto, 2026-11-12).
  Più partite e meno esempi per partita invece di più ricerca per mossa: il
  valore ha bisogno di esiti, non di posizioni della stessa partita.

## Fatto
- Passaggi 1-4: D1–D49, Q1–Q4, bug del coach (`cc3d776`). Dettagli in AUDIT.md.
- Rimozione mazzi: test spostati sui precon, 20 golden game rigenerate.
- Quinto passaggio (mazzi competitive, D50-D52, 8 golden game Kai'Sa vs
  Kennen) e sesto (righe MECHANICS.md, D53-D56 `0b877df` `5ef1d33` `e115324`
  `56ce034`; sostituzioni §367-373 e layer §475-482 giusti). Dettagli in
  AUDIT.md.
- Punto 3 (BACKLOG O3, `6ebd0e7`): la ricerca fa tutte le scelte del suo
  giocatore (albero, difesa, nascoste, `_Fallback`); PREDICT nell'encoding.
  A/B con lo stesso valutatore, 240 partite: nuova 68,8% contro la vecchia.
- Training: due budget di ricerca in self-play (piena solo sulle decisioni
  che diventano esempi), weight decay, misure nuove nel log (`fd01c63`).

## In corso
Training (O4), ricetta nuova in prova: run dell'utente sul Mac in
`runs/competitive2` (60 iterazioni, 48 partite, `--fast-iters 16
--full-fraction 0.25 --weight-decay 1e-4`). A 27 iterazioni tiene: 0,50-0,65
contro simple_trade, turni a vuoto 9-13%. Run di prova qui (20 iterazioni):
rete 10 → 20 su 40 partite: 0,45 → 0,57 simple_trade, 0,90 → 0,93 random.

Primo run (2026-11-12/13, `runs/competitive`, 205 iterazioni da 16 partite,
tutto in ricerca piena): **da buttare**. La rete impara a passare (turni a
vuoto 8% → 30-50%; random 0,95 → 0,55; simple_trade mai sopra 0,45). Causa:
il valore memorizza le partite (90 esempi con un solo esito): su partite nuove
è sicuro (|v| 0,8) e sbaglia (errore 0,91 nel primo terzo); le mosse di un
turno non si distinguono più e la politica scivola sul PASS. Scegliere la
mossa per Q o abbassare c_puct sulla rete finale non la recupera.

## Prossimi passi
1. Log del run `competitive2` → se tiene fino a 60: la ricetta nuova diventa
   il default di `allena.command`/`.bat`, poi run lungo. Reti da confrontare
   su 100+ partite (20 a valutazione ballano di ±0,1).
2. Da guardare: 0,70 contro random all'iterazione 25 con 0,65 contro
   simple_trade (rumore o stati mai visti in self-play?).
3. Se il valore torna a memorizzare (`fresh` lontano da `value`): più partite
   per iterazione, bersaglio del valore misto all'esito della ricerca, gating
   sulla rete migliore. PASS: bersaglio della politica con i Q (Gumbel).
4. Banlist del 23/11: l'utente incolla l'elenco → `banned_cards.json`,
   ricontrollare i due mazzi; il run "buono" è quello dopo.
5. Possono aspettare: sideboard, tempi per turno, carte fuori dai mazzi,
   costruzione del mazzo (§103), regole aperte fuori dai mazzi (AUDIT.md).

Macchine: PC Windows (Ryzen 7 7800X3D, `allena.bat`, 8 worker) o Mac M1 Max
(`allena.command`, un worker per core veloce). Conta la CPU, non la GPU.
Nel log: `fresh`/`|v|` (errore e sicurezza del valore sulle partite nuove
prima di allenarcisi), `empty_turns` (turni passati senza fare nulla).

## File principali
- `docs/audit/AUDIT.md`: deviazioni, stato, domande aperte, cosa non è stato
  controllato; `tests/audit/`: un test per deviazione (un file per passaggio,
  helper in `audit_helpers.py`); `docs/MECHANICS.md`: le meccaniche.
- `riftbound/core/loop.py`: il motore (turno, chain, showdown, combattimento).
- `riftbound/core/`: `battlefield.py` (controllo, Hold / Conquer),
  `effects.py` (effetti), `legality.py` (azioni legali offerte agli agenti).
- `riftbound/ai/net_mcts.py`: la ricerca guidata dalla rete (albero delle
  scelte, `_Plan`, `_Fallback`); test in `tests/test_net_mcts.py`.
- `riftbound/ai/selfplay.py` + `scripts/train_selfplay.py`: self-play e
  training; `scripts/allena.bat` / `allena.command`: lo stesso con doppio clic.
- `riftbound/ai/coach.py` + `scripts/coach.py`: il coach e la sua pagina.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato
  (`scripts/piltover_sync.py compare` per le differenze).
- `riftbound/data/decks/`: i due precon e i due competitive dell'utente.
- `tests/golden_games.json` + `test_golden_games.py`: 20 partite Zed vs Shen
  (`RBSIM_REGEN_GOLDEN=1` per rigenerarle); `BACKLOG.md`: quel che resta.
