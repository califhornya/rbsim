# STATO

Aggiornato: 2026-11-19 (risultati di boot1: stop alla misura 3).

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
- (Utente, 12/11) Otto mazzi non precon eliminati, correzioni di carte tenute.
  (17/11) Kai'Sa e Kennen bannati: i competitive sono Evelynn e Kha'Zix; i file
  vecchi restano come fixture. Un solo file di stato, BACKLOG solo voci aperte.
- (Utente, 17/11) Revisione esterna: prima la correttezza, poi la struttura
  (piano v2, `docs/PIANO_MOTORE.md`). Sera: strada A, prima il bot: solo la
  fase 1 (D66-D68, le copie: piccola, la partita vera non cambia), poi il bot.
  Fuori perimetro: D59-D65, la struttura, il training.
- (Utente, 17/11) `Result` di una copia: contatori dal punto di copia, lasciato.
- Flow: solo sconti di aura (§356.3-4 aperti). Ricerca: un nodo per opzione,
  prior uguali. Scelte nascoste: decise quando servono, rigiocando.
- (Utente, 13/11) La rete: avversario per allenarsi e per misurare mazzi e
  matchup. Proposte in parole semplici (cosa faccio, quanto costa, cosa
  sapremo); ogni deviazione dal piano concordato detta esplicitamente.
- Training: più partite, meno esempi per partita (il valore vuole esiti).
- (Utente, 18/11) Rete: imita il bot a mano, poi self-play; sul Mac.
- (Utente, 18/11) Regole dal motore o da CORE_RULES, mai a memoria; lezioni
  in GIUDIZI.md sempre con partita e turno (i principi da soli non si capiscono).
- RiftAtlas: carte nascoste dell'avversario senza lista = le sue carte viste,
  ripetute (avviso); Might dal motore, il segnalino dei giocatori solo confronto.
- (gptAstra, 18/11) Rete: seed disgiunti 1.600 / 200 / 200 (allenare, epoca,
  test), Evelynn metà per lato. (Utente) Mosse della mano dalla carta; "once"
  della leggenda visibile.
- Mano nota: carte per identità (`Player.hand_public`, come `Deck.known_top`);
  determinize ordina il pool prima di mescolare (dipende solo da cosa è nascosto).

## Fatto
- Audit, passaggi 1-7: D1–D58, Q1–Q4 e Q6; dettagli in AUDIT.md.
- Revisione esterna (17/11): D59-D68 in AUDIT; fase 1 del piano v2: D66-D68
  corrette (`tests/audit/test_audit_copies.py`), 28 golden identiche.
- Partite dal vivo su RiftAtlas (17-18/11): partita 1 giocata da Claude
  (persa), BO3 dall'utente. GIUDIZI G8-G15; checklist e note in PARTITA_LIVE.
  18/11 notte: contro Ivern (flamingo, stanza 82FAW), interrotta al turno 10
  sul 5-4; G16-G23; registrazione e log in `docs/bot/partite/`.
- PR #32 (18/11): determinize tiene le carte note; bot 0,58 → 0,80 contro
  simple_trade; S6-S9, S11a/b, TEORIA_PUNTI. Turno avversario: `TURNO_AVVERSARIO.md`.
- Audit, nono passaggio (19/11): D69-D70, copie del Chosen Champion: campione
  + 2 copie nel mazzo, Hallowed Tomb riporta anche una copia; golden identiche.

## In corso
RiftAtlas → bot (18/11 notte): `stati.py` e `posizione.py` funzionano su 82FAW,
con la lista di Ivern (`docs/bot/partite/82FAW_ivern_lista.txt`). Da fare (dopo):
bot contro le mosse dell'utente nei suoi 5 turni di 82FAW (giudizi, scenari).
Rete dal bot a mano (`docs/bot/RETE.md`, sezione "Risultati di boot1"):
girata sul Mac il 18/11. Prevede chi vince meglio del valore a mano (0,466
contro 0,559) ma contro il bot fa 0,46 ± 0,05 (serviva 0,55): stop per la
regola concordata. `net_boot.pt` resta sul Mac (`runs/` non è nel repo).
Proposta all'utente, in attesa: una misura di diagnosi prima di decidere.

## Prossimi passi
0. Valutazione dai giudizi (`judgment_value.py`): non rende il bot più forte
   (0,49; più peso alla mano 0,65); turno avversario simulato 0,44, per media
   o caso peggiore sbaglia 5-6 posizioni su 7. Deciso: la rete. boot1:
   misura 1 passa, misura 3 no (0,46) → stop; decisione dell'utente su
   diagnosi, self-play comunque, o tornare al bot a mano / piano v2.
   Registratore RiftAtlas usato nella 82FAW (nessun buco; `avversarioScoperto`
   esclude le carte rivelate).
1. Base del bot (`handwritten_value.py 200 100`, 20 min): 0,80 contro
   simple_trade, 0,97 contro random. Giudizi: `docs/bot/GIUDIZI.md`.
2. Piano v2 (fasi 0, 2-6, D59-D65) dopo il bot, se l'utente decide.
   Possono aspettare: training, sideboard, tempi, carte fuori dai mazzi.
Macchine: PC Windows (Ryzen 7 7800X3D) o Mac M1 Max. Log: `fresh`/`|v|`, `empty_turns`.

## File principali
- `docs/audit/AUDIT.md`: deviazioni, stato, domande aperte, cosa non è stato
  controllato; `tests/audit/`: un test per deviazione; `docs/MECHANICS.md`.
- `docs/bot/`: GIUDIZI, TEORIA_PUNTI, PARTITA_LIVE, scenari.json, partite/.
- `docs/PIANO_MOTORE.md`: piano v2 (correttezza, poi struttura), con
  l'avanzamento; `docs/audit/revisione_esterna/`: i rapporti (in inglese).
- `riftbound/core/`: il motore. `loop.py` (turno, chain, showdown, combattimento),
  `effects.py`, `battlefield.py` (Hold / Conquer), `legality.py` (azioni legali).
- `riftbound/ai/net_mcts.py` (ricerca con la rete), `selfplay.py`, `coach.py`,
  `scenari.py` (coach e scenari dei giudizi); `scripts/train_selfplay.py`.
- `riftbound/ai/handwritten.py`: il bot a mano (valore, ricerca a tempo);
  `scripts/bootstrap_net.py` + `scripts/rete.command`: la rete dal bot.
- `scripts/diag/`: le misure (`handwritten_value.py`, `opponent_turn*.py`).
  `docs/archivio/`: storico (training del 13/11, BACKLOG A-G, piano v1).
- `riftbound/data/cards/all_cards.json`: dati; `riftbound/data/reference/
  piltover_archive.json`: testo stampato (`scripts/piltover_sync.py compare`).
- `riftbound/data/decks/`: precon, competitive dell'utente, `competitive_ivern`
  (82FAW, RiftAtlas); da lista .txt: `scripts/deck_from_txt.py`.
- `scripts/riftatlas/`: registratore.js (in pagina), stati.py (registrazione →
  tavolo), posizione.py (tavolo → GameState → bot); test `test_riftatlas_*`.
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, solo stato
  finale (`RBSIM_REGEN_GOLDEN=1` per rigenerarle). `BACKLOG.md`: voci aperte.
