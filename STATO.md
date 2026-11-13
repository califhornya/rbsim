# STATO

Aggiornato: 2026-11-13 (run 3 finito: ricerca corretta regge, ma il gioco non sale dopo la 10).

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
- Training: due budget di ricerca in self-play, weight decay, misure nuove
  nel log (`fd01c63`); ricerca `backup="best"`.

## In corso
Training (O4). Trovati due difetti, in quest'ordine di peso:
1. **La ricerca passava troppo** (`backup="mean"`): un'azione valeva la media
   di tutte le linee provate dopo, PASS un valore netto. Con una valutazione
   scritta a mano al posto della rete: 0,20 contro simple_trade, un turno su
   tre a vuoto. Ora `backup="best"` (default): un nodo vale la migliore linea
   sotto di sé e si gioca la mossa col Q più alto. Stesse 40 partite: a mano
   0,20 → 0,55; rete del run di prova (20 iterazioni) 0,57 → 0,70 e
   0,93 → 0,97 contro random.
2. **Il valore memorizzava le partite** (16 partite a iterazione, 90 esempi
   l'una): primo run (`runs/competitive`, 205 iterazioni) da buttare, la rete
   aveva imparato a passare. Ricetta nuova (48 partite, `--fast-iters 16
   --full-fraction 0.25 --weight-decay 1e-4`): nel run `competitive2` (60
   iterazioni, ricerca vecchia) nessun crollo (turni a vuoto 8-13%, errore
   del valore sulle partite nuove 0,75 → 0,50) ma gioco fermo: 0,52 di media
   contro simple_trade.

## Prossimi passi
1. Run 3 finito: 0,72 contro simple_trade dalla 10 alla 60, pendenza nulla
   → fermo. Rete 60 contro rete 10 (`scripts/diag/net_vs_net.py`, 200
   partite): 0,49 ± 0,07, ferma anche contro se stessa. Proposto all'utente:
   bersaglio della politica dai Q prima dell'imitazione. In attesa di risposta.
2. Non ancora fatto: bersaglio della politica dai Q (le visite seguono i
   prior più dei valori); con "best" il self-play non è stato ancora provato.
3. Banlist del 23/11: l'utente incolla l'elenco → `banned_cards.json`,
   ricontrollare i due mazzi; il run "buono" è quello dopo.
4. Possono aspettare: sideboard, tempi per turno, carte fuori dai mazzi,
   costruzione del mazzo (§103), regole aperte fuori dai mazzi (AUDIT.md).

Macchine: PC Windows (Ryzen 7 7800X3D) o Mac M1 Max; conta la CPU. Nel log:
`fresh`/`|v|` (valore sulle partite nuove), `empty_turns` (turni a vuoto).
Run 3 (13/11), 60 iterazioni: media 0,72 simple_trade, 0,97 random; non sale.

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
- `docs/history/SESSIONE_2026-11-13.md`: il primo training nel dettaglio; `scripts/diag/`: le misure.
- `riftbound/data/cards/all_cards.json`: dati delle carte;
  `riftbound/data/reference/piltover_archive.json`: testo stampato
  (`scripts/piltover_sync.py compare` per le differenze).
- `riftbound/data/decks/`: i due precon e i due competitive dell'utente.
- `tests/golden_games.json` + `test_golden_games.py`: 20 partite Zed vs Shen
  (`RBSIM_REGEN_GOLDEN=1` per rigenerarle); `BACKLOG.md`: quel che resta.
