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
| 3 | 25/11 | Punch First pagato con le rune invece che col Gold | corretto in quel turno: il Gold era esausto. Col Gold pronto il motore non lo usa da solo: va prima "Usa Gold" (scegli il dominio), poi il lancio paga prima con quel power | corretto (scelta di Matteo): giocando una carta con un Gold pronto la pagina chiede "Come paghi?" (rune o Gold, con le rune riciclate); una carta pagabile solo col Gold compare "(col Gold)". Il Gold si usa prima, col dominio della carta (`payment_plans`, `gold_only_plays`) |
| 4 | 25/11 | K'Sante Courageous non sembra canalizzare la runa quando tiene | corretto: la canalizza (verificato, 2 del turno + 1 sua); Matteo conferma | chiuso |
| 5 | 25/11 | Nascondendo una carta non si sceglie quale runa riciclare | pagina: il motore paga un [rune] (nascondere, carte a due domini, DEFLECT) dal primo dominio che basta | corretto: "Come paghi?" offre i domini che cambiano qualcosa (`payment_options`), la pagina paga da lì (`CoachLoop`, solo la partita della pagina) |
| 6 | 25/11 | Non si vedono le rune esauste | pagina: il motore tiene l'energia non spesa, non quali rune; la pagina non mostrava nulla | corretto: tante rune pronte quanta energia resta, le altre ruotate e attenuate (il dominio delle esauste è solo un disegno) |
| 7 | 25/11 | Il campione accumula unità sul campo che tiene (Rengar, poi Vi) invece di entrare nel campo di Matteo, anche un punto sotto | strategia: la valutazione premia la Might su un campo senza limite (0,05 contro 0,03 in base); Rengar non poteva entrare direttamente (D72 aperto su Python) | `GIOCATE.md` §8; da misurare con uno scenario, correzioni da provare in arena |
| 8 | 25/11 | Pillaged Armory giocata "durante uno showdown" | motore (D77): Faefolk sposta l'unità di Matteo sul campo del campione con uno spostamento non trattenuto; lo showdown resta in attesa e il campione gioca prima la gear (senza ACTION) | `AUDIT.md` D77, da correggere in Rust |
