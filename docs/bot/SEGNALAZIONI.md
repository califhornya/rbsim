# Segnalazioni dalle partite a mano (pagina col campione)

Ogni segnalazione ha un esito:
- **pagina**: difetto della pagina (`riftbound/ai/coach.py`, `coach_page.html`); si corregge subito, con un test.
- **motore**: difetto delle regole; va in `docs/audit/AUDIT.md` (D77 in poi) con un test rosso e si corregge
  in Rust (Python congelato, decisione del 24/11). La pagina gira sul motore Python: la correzione si vede
  quando la pagina passa a Rust.
- **corretto**: il motore segue le regole; si spiega perché.
- **da decidere**: miglioria possibile, serve una scelta.

| # | Data | Segnalazione | Esito | Stato |
|---|------|--------------|-------|-------|
| 1 | 25/11 | Punch First offerto solo "per campo": non si poteva dare +5 a un'unità in base | pagina: il menu chiedeva un campo che per questa magia non conta; il bersaglio (base compresa) veniva dopo | corretto: una voce "Lancia X", poi il bersaglio (`spell_lane_free`) |
| 2 | 25/11 | Il Gold di Reckless Innovator entra pronto, la carta dice esausto | pagina: il motore lo mette esausto, la pagina disegnava ogni gear dritta | corretto: gear esauste ruotate (`gear_exhausted` negli extra del tavolo) |
| 3 | 25/11 | Punch First pagato con le rune invece che col Gold | corretto in quel turno: il Gold era esausto. Col Gold pronto il motore non lo usa da solo: va prima "Usa Gold" (scegli il dominio), poi il lancio paga prima con quel power | da decidere: la pagina potrebbe chiedere "come paghi?" al lancio quando c'è un Gold pronto |
