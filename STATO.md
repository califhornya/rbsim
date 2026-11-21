# STATO

Aggiornato: 2026-11-21 (piano per la forza; mazzo Rengar).

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
RiftAtlas → bot: `stati.py` e `posizione.py` funzionano su 82FAW (lista di Ivern
in `docs/bot/partite/`); il bot d'accordo con G17, G20, G22 (GIUDIZI, 19/11).
Rete dal bot a mano: **chiusa** (19/11, `docs/bot/RETE.md`). Prevede chi vince
meglio (0,466 contro 0,559) ma ordina male le mosse: completa 0,46, solo il
suo valore con prior uguali 0,296 ± 0,038 contro il bot (arena, 230 coppie).
Spareggio (`tie_break="mean"`, W/N tra i Q pari, 24% delle decisioni): arena
19/11, 800 coppie: 0,483 ± 0,013, peggio; non promosso, il bot resta com'è.
Chi comincia decide: Evelynn vince ~91% se comincia, ~45% se no (arena e 2.000
partite; il motore dà la runa in più a chi è secondo, §487.7). Matchup divisi così.
Piano "forza" (20/11, con GPTAstra): 1) velocità; 2) dati di confronto tra mosse
sorelle (pilota 128 radici) e rete che li impara; 3) self-play grande (tappe a
5.000 / 15.000 / 30.000 partite). Fatto: ricerca 1,16× (mosse identiche);
corretti mulligan e ordine delle rune (la ricerca vedeva carte e rune nascoste);
la rete vede le proprie coperte per campo (boot1 non si carica più).
Dichiarazioni (copia del gioco): 31% del tempo senza profiler, sempre vuote
il 12%: saltarle darebbe al massimo 1,14×; rimandato. La leva vera: iterazioni.

## Prossimi passi
0. Pilota (Mac 20/11, 73 min, 95 radici): passa. Differenze tra sorelle W1/W2
   correlate 0,73 (0,60-0,83); 32 iterazioni bastano (perdita -0,015 ± 0,021).
   Passo 2 chiuso; tempo 0,472, orizzonte 0,490: la ricerca attuale è satura.
   (21/11) `docs/PIANO_FORZA.md`: prova A chiusa (G +0,007 e +0,006, limite
   superiore sotto 0,02); prova B: rete senza ricerca 120 ms a partita sul Mac.
   Rust rimandato; prossima strada: PPO in Python (prima codifica e scelte).
1. Bot a mano (`handwritten_value.py 200 100`): 0,80 contro simple_trade, 0,97 random.
2. Piano v2 (fasi 0, 2-6, D59-D65) se l'utente decide.

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
- `scripts/diag/`: misure (`handwritten_value.py`, `arena_spareggio.py`,
  `pilota_sorelle.py`); `scripts/*.command`: lanciatori Mac. `docs/archivio/`: storico.
- `riftbound/data/cards/all_cards.json`, `data/reference/piltover_archive.json`.
- `riftbound/data/decks/`: precon, competitive (Evelynn, Kha'Zix, Ivern, Sett, Rengar del 21/11)
  e i vecchi come fixture; da lista .txt: `scripts/deck_from_txt.py`.
- `scripts/riftatlas/`: registratore.js (in pagina), stati.py (registrazione →
  tavolo), posizione.py (tavolo → GameState → bot); test `test_riftatlas_*`.
- `tests/golden_games.json` + `test_golden_games.py`: 28 partite, solo stato
  finale (`RBSIM_REGEN_GOLDEN=1` per rigenerarle). `BACKLOG.md`: voci aperte.
