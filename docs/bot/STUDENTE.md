# Pilota «studente» (27/11, Astra/Matteo)

Scopo: capire se un modello veloce impara da «Pensa» quale delle ≤3 mosse candidate scegliere alla fine della ricerca
del campione (138 iterazioni, `ckpt_040000`, `rimonta`, regole `6427b90+D72-D83`), senza giocare partite in turno.
Tetto: **2 h di CCX63 comprese le verifiche**. Se la soglia non passa ci si ferma e resta il campione.

## Partite e posizioni
- Partite autonome campione contro campione (`decisione_rs.autonoma`, stessi argomenti di `seguiti.partite`), 10 matchup
  (`arena_rs.COPERTI`). Semi nuovi: raccolta `110_000_000 + 1000*i + j`, verifica `130_000_000 + 1000*i + j`.
- **Entrambi i posti**: per ogni seme due prospettive (`campione="A"` e `"B"`), quindi chi inizia e chi risponde, ogni
  mazzo nei due ruoli (lo starter dipende dalla parità del seme). Le due prospettive di un seme stanno sempre nello stesso
  insieme (raccolta, validazione o verifica) e sono un unico gruppo nel bootstrap.
- Posizioni: decisioni di turno (`turn_action`, menu ≥2) di quel posto, al più `PER_POSTO` (4) per prospettiva, sparse
  come `seguiti.selezionate`. Ruolo = «inizia» se il posto è lo starter, altrimenti «risponde».
- Candidati come `fondo.candidati` (mossa del campione, poi ≤2 per visite), con **identità esatta**: si salva il JSON
  dell'azione (`action_list`) di ogni candidata; si esclude una candidata alternativa la cui etichetta compare più volte
  nel menu, e si salta la posizione se è ambigua l'etichetta del campione (conteggi nel riepilogo).

## Etichette (raccolta)
- Ogni candidata giocata fino in fondo dal campione (stessa macchina di `fondo`: `A.posizione`, `A.linea_primo`,
  mondi `ignote`) su `MONDI_RACCOLTA` = 8 mondi appaiati (indici 60000..). Si salvano i ritorni per mondo (1 / 0,5 / 0),
  pareggi compresi; mondo valido solo se tutte le linee hanno `primo_ok`.
- Bersaglio per l'alternativa j: d_j = media sui mondi validi di (y_j − y_0), dal punto di vista di chi decide.

## Studente
- Input alla radice della posizione: (x, q, ctx, otype, ocards, ofeats) della rete, nell'ordine del menu, con le azioni
  JSON. Dalla rete congelata: h = `net.ctx(...)` (256), o_j = `net.opt(...)` (128) per candidata, logit della politica.
- Caratteristiche della coppia (j, 0): [h, o_j, o_0, Q_j−Q_0, log1p(N_j)−log1p(N_0) (/log 139), P_j−P_0, logit_j−logit_0,
  turno/20, ruolo]. Testa: MLP 64 (ReLU) → 1 e, in alternativa, regressione ridge sulle stesse caratteristiche.
- Perdita: MSE su d_j, peso 1/sqrt(numero di alternative). Regola: j* = argmax predizione; si cambia solo se
  predizione(j*) > τ, altrimenti la mossa del campione (a parità resta il campione).
- Divisione per semi: 80% allenamento, 20% validazione. Su validazione si scelgono modello (MLP o ridge) e τ ∈ {0; 0,03;
  0,06; 0,10} per guadagno realizzato (d della mossa scelta, 0 se resta). **Cancello**: se il guadagno di validazione
  ≤ 0 lo studente «non impara» e la verifica non parte.
- **Congelamento** prima di generare le partite di verifica: `studente.pt` (pesi, caratteristiche, τ) e
  `congelato.json` (sha256 di `studente.pt` e del checkpoint, regole, parametri, ora). La verifica carica solo da lì e
  controlla lo sha.

## Verifica (dopo il congelamento)
- Posizioni dalle partite di verifica, stesse regole. Studente: se resta sul campione vale 0 senza giocare; se cambia,
  campione e scelta giocate su `MONDI_VERIFICA` = 64 mondi appaiati nuovi (indici 70000..).
- Maestro («Pensa» piena, 32 mondi 40000.., 3 candidati) su un sottoinsieme fisso: i primi `SEMI_MAESTRO` semi per
  matchup (entrambe le prospettive); i suoi cambi valutati sugli stessi 64 mondi nuovi.
- Riepilogo come `scelta.riassunto`: matchup a pesi uguali, IC 95% ricampionando i semi dentro il matchup; totale e
  ruoli separati («inizia», «risponde»), per studente e maestro; cambi, esclusioni, tempi.
- **Soglia fissata ora**: PASSA se lo studente fa ≥ +1,0 pp con limite inferiore > 0 sui due ruoli insieme. Se passa, il
  candidato per l'arena è lo studente veloce; se no, si ferma la spesa e resta il campione.

## Tetto di tempo
- Compiti in ordine fisso intercalato (matchup, seme, prospettiva). Scadenza per fase (`TETTO_RACCOLTA_MIN` 55,
  `TETTO_VERIFICA_MIN` 50): dopo la scadenza non si inviano compiti nuovi, si aspettano quelli in corso e si usano solo le
  posizioni complete. Il taglio dipende dall'ordine, mai dagli esiti.
- Dati pesanti (input della rete) in `runs/studente/<stamp>/`; risultati leggeri in `docs/bot/esperimenti/studente_<stamp>/`.

## File
`riftbound/rs/studente.py`, `scripts/rust/studente.py`, `scripts/rust/studente.command`, `tests/rust/test_studente.py`.
