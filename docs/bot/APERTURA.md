# Apertura di una partita 1v1 (RiftAtlas, osservata il 25/11)

## Sequenza
Regole: `docs/rules/CORE_RULES.md` setup §113 campi (§488.5) -> §115 chi comincia -> §116 pesca 4.
1. Ready. Ogni giocatore sceglie il proprio campo fra i 3 del mazzo (o "Casuale"): scelta coperta e simultanea.
2. I due campi si scoprono insieme. Sono pubblici (§488.5 li mette nella Battlefield Zone; §107.2.c
   Public Information, §128.2.a): si decide chi comincia a campi noti.
3. d20 a testa (si ritira se pari); chi fa di più decide: "Inizio io" / "Inizia l'avversario".
4. Pesca 4; mulligan fino a 2 carte, simultaneo.
5. Turno 1: chi comincia canalizza 2 rune, il secondo 3 rune; entrambi pescano 1.

## Cosa fa il motore
- `build_game(bf_a, bf_b, first_player)` (Python) e `Game.build(..., bf_a, bf_b)` (Rust): campo per posto, per nome;
  nome valido = quello senza consumare il caso, assente o non valido = a caso (§487). Senza scelte tutto come prima
  (parità con `6427b90`). Pesca 4, mulligan, rune del secondo: già nel motore.

## Cosa fa la pagina (`CoachSession`, una volta per entrambi i motori)
- `/api/new` -> stato "opening": `/api/campo` (campo o "random") -> campi scoperti e d20 -> se vinco io `/api/inizia`
  `{io: bool}`, se vince il campione decide `riftbound/ai/apertura.py` (`scegli_inizio`) e basta "Continua".
- Il d20 e il campo a caso usano generatori derivati dal seme (riproducibile). Poi si costruisce la partita con campi e
  primo giocatore scelti; il rewind li riusa e non torna mai prima del mulligan.
- Il registro riporta campi, tiri (con i ritiri) e chi comincia; `games.jsonl` ha `campo_mio`, `campo_avv`, `inizia`.
- Il campione per ora è provvisorio: campo a caso, comincia sempre (la tabella per matchup arriva dopo).

## Partite 2 e 3 della Bo3
Decide chi comincia chi ha perso la partita precedente (Matteo, 25/11; non è nelle regole base, §488.6 non lo dice).
Non implementato: la pagina gioca partite singole.

## Non osservato
- Cosa succede al d20 in caso di pari: si suppone il ritiro (la pagina lo fa).
- Bo3: §488.5, campi esclusi dopo una vittoria (non osservato su RiftAtlas, non implementato).
- Dove vanno le carte del mulligan (in fondo al mazzo, come oggi nel motore, §116: da confermare).
