# STATO

Aggiornato: 2026-11-23 sera (giocate della 35.010: Switcheroo D71 proposto; arena finale).

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
  della leggenda visibile. (19/11) Domande a GPTAstra in chat, mai nel repo.
- Mano nota: carte per identità (`Player.hand_public`, come `Deck.known_top`);
  determinize ordina il pool prima di mescolare (dipende solo da cosa è nascosto).

## Fatto
- Audit 1-7 e 9: D1–D58, D69-D70, Q1–Q4, Q6 (AUDIT.md). Revisione esterna
  (17/11): D59-D68; D66-D68 corrette (`test_audit_copies.py`), golden identiche.
- Partite dal vivo su RiftAtlas (17-18/11): partita 1 (Claude, persa), BO3
  dell'utente, 82FAW contro Ivern (turno 10, 5-4). GIUDIZI G8-G23,
  PARTITA_LIVE, registrazioni in `docs/bot/partite/`.
- PR #32 (18/11): determinize tiene le carte note; bot 0,58 → 0,80 contro
  simple_trade; S6-S9, S11a/b, TEORIA_PUNTI, `TURNO_AVVERSARIO.md`.

## In corso
RiftAtlas → bot: `stati.py`, `posizione.py` su 82FAW; bot d'accordo con G17, G20, G22.
Rete dal bot a mano: chiusa (19/11, `docs/bot/RETE.md`: completa 0,46 contro il
bot). Spareggio (`tie_break="mean"`): 0,483 ± 0,013, non promosso.
Chi comincia decide (Evelynn ~91% se comincia, ~45% se no): matchup divisi così.
Piano "forza" (20/11, `docs/PIANO_FORZA.md`): ricerca 1,16×; corretti mulligan e
ordine delle rune (la ricerca vedeva carte nascoste); poi PPO a più mazzi.
Giocate (23/11 sera, `docs/bot/GIOCATE.md`, controllo di Astra sulla 35.010):
Switcheroo: 4 deviazioni (D71 proposto, non applicato); il 98% su Valley è della
rete, l'arena sceglie campo e bersagli con la ricerca. Mulligan fermato a 40 seed, rilevatori a 28 partite: fermati.

## Prossimi passi
0. Sorelle, passo 2, tempo, orizzonte chiusi. PPO: da sola 0,425 contro il bot.
   Bot a mano + prior PPO 30.016: 0,540 ± 0,027, promosso il 22/11 (PIANO_FORZA.md).
   Sfide, ricette, distillazione (s5 0,546, s6 0,428): chiuse, varianza tra semi.
   **Rengar (22/11): entra** (+0,127). **Arena: prior ekr_s8 PROMOSSO** (Rengar 0,541,
   EK 0,515). Campione: bot a mano + prior `runs/rengar/ekr_s8/ckpt_020032.pt`.
   **Ivern (23/11): entra** (Δ +0,244), i tre vecchi tengono. Partenza Sett: ekri_s10.
   **Sett (23/11): entra** (Δ +0,162); vecchi: 5 su 6 tengono, EI incerto (-0,032),
   semi molto discordi. **Ora: arena finale** (`scripts/arena_finale.command`, ~9,5 ore):
   A) EI contro ekri_s10; se passa, B) ekris_s12 contro ekr_s8 sui dieci matchup.
   (23/11) Corretto il difetto della cache in `ppo.py` (pannelli e archivio; le
   verifiche e le arene no). Poi: scelta della tappa, lr 1e-4 contro 3e-4.
   **Riallineare** la sessione delle arene (ramo `claude/rbsim2026-boot1-results-373ku0`, fermo a
   01d4cb0): merge di `claude/wonderful-mendel-eii7zu` (avanti veloce, +3 commit), poi `git pull` sul Mac.
   Ad arena finita, sul Mac: GIOCATE.md §6; poi D71 se l'utente decide.
1. Bot a mano: 0,80 contro simple_trade, 0,97 random. 2. Piano v2 (D59-D65) se l'utente decide.

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
- `riftbound/ai/handwritten.py`: il bot a mano; `scripts/bootstrap_net.py`: boot1.
- `scripts/ppo.py` (PPO, `--mazzi ekr`), `riftbound/ai/ppo/`; `scripts/diag/`: misure
  (`arena_bot.py`, `arena_mazzi.py`, `incroci_ppo.py`, `verifica_mazzi.py`; `giocate.py`,
  `mulligan_mano.py`, `switcheroo_casi.py`: GIOCATE.md); `scripts/*.command`: lanciatori Mac. `docs/archivio/`: storico.
- `riftbound/data/decks/`: precon, competitive (Evelynn, Kha'Zix, Ivern, Sett, Rengar del 21/11)
  e i vecchi come fixture; da lista .txt: `scripts/deck_from_txt.py`.
- `scripts/riftatlas/`: registratore.js (in pagina), stati.py (registrazione →
  tavolo), posizione.py (tavolo → GameState → bot); test `test_riftatlas_*`.
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, solo stato
  finale (`RBSIM_REGEN_GOLDEN=1` per rigenerarle). `BACKLOG.md`: voci aperte.
