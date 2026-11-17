# Il motore: piano di correzione e ristrutturazione (v2)

Scritto il 2026-11-17, dopo una revisione esterna del motore. Sostituisce la
v1 (`docs/archivio/PIANO_MOTORE_v1.md`), che metteva la struttura per prima:
la revisione ha trovato difetti più gravi, nella partita vera e nelle copie
della partita usate dalla ricerca del bot. **Non avviato.** Chi esegue e quando
lo decide l'utente; stato e priorità in `STATO.md`. Le deviazioni D59-D68 sono
in `docs/audit/AUDIT.md`, ottavo passaggio.

## 1. Cosa cambia rispetto alla v1

Errori della v1, tutti verificati:
- metteva per prima la divisione di `loop.py`, mentre difetti che cambiano la
  partita (vera e copiata) restavano dietro un grande lavoro di struttura;
- la sua "impronta" si basava su `scripts/trace_game.py`, che non è
  deterministico (stesso seed, partite diverse: gli agenti non sono seminati);
- diceva 20 golden game: sono 28, anche Kai'Sa e Kennen; e controllano solo lo
  stato finale (non hanno visto D62);
- il conteggio "preciso" (89 metodi, 428 chiamate) escludeva 19 chiamate vere:
  sono 94 e 447;
- il cricchetto sui metodi privati si aggira togliendo il trattino basso;
- "ogni operazione fa la sequenza completa" viola i tempi delle regole
  (bersagli fissati alla dichiarazione, morti risolte in blocco);
- gli helper "neutri" da spostare in un modulo comune modificano la partita;
- la ricerca del bot e gli effetti hanno bisogno di interfacce diverse.

Nuovo ordine: prima la correttezza (partita vera e copie), poi la struttura.

## 2. I documenti della revisione

In `docs/audit/revisione_esterna/` (in inglese). Gli script e i dati delle
sonde non sono nella repo (contengono file pickle e codice esterno): li ha
l'utente, negli ZIP della revisione.

| File | Contenuto | Serve per |
|---|---|---|
| `review_motore_rbsim_e72318e.txt` | Analisi alla cieca del motore, per gravità | Quadro generale |
| `review_piano_motore_rbsim_2900311.txt` | Critica della v1 | Sezione 1 |
| `verifica_quattro_rilievi_rbsim_2900311.txt` | Rimisura dei rilievi della v1; scritture dirette nello stato: gravità medio-alta | Fase 6 |
| `systematic_action_probe_rbsim_e72318e.txt` | Sonda su 576 partite: ogni azione offerta provata su una copia | D59-D61 |
| `design_action_outcomes_rbsim_e72318e.txt` | Progetto del fix degli esiti; risposta di regole sul movimento; difetti di registro e coach; controlli trovati sani | Fasi 2-4, D62-D64 |
| `design_stable_identity_rbsim_2900311.txt` | Identità stabile, passo A e B; inventario delle 96 chiamate a `id()`; quando una carta è un oggetto nuovo (§124...) | Fasi 1 e 5, D65 |
| `clone_fidelity_probe_rbsim_e72318e.txt` | Fedeltà delle copie: 61 punti su 3.123 divergono, 19 cambiano il vincitore | Fase 1, D66-D68 |

## 3. Verificato in questa sessione (17/11)

| Affermazione della revisione | Verifica |
|---|---|
| Sonda azioni: 576 partite, 80.430 decisioni, 309.097 prove, 17 esiti sbagliati in 5 gruppi; controllo 576/576 | Rifatta qui: identica |
| 8 riproduzioni degli esiti; 613 + 69 prove mirate | Rifatte qui: identiche |
| Conteggi statici: 96 `id()`, 94 metodi / 447 chiamate, 126 / 239 / 47 scritture, test 113 file | Rifatti qui: identici |
| La suite di test esegue 200 dei 212 tipi di effetto usati dalle carte | Misurato qui: 200/212 |
| Copie: Black Market, Pyke, Kennen, Kha'Zix, Shadow Clone, Twilight Reveler, Relentless Pursuit, contatori | Riproduzioni piccole rifatte qui; Black Market e combattimento anche con script propri |
| Riven Deserter dopo Temporal Breach (D65) | Riprodotto qui con uno script proprio |
| D62 (pass dopo un'abilità Add), D64 ("se lo uccide") | Codice letto qui |
| Sonda grande sulle copie (3.123 punti), D63, previsioni sulle golden | **Non** rifatti qui |

## 4. Le fasi

Ogni fase: un branch e una PR. Ogni correzione di comportamento: un commit con
il suo test di deviazione. Le golden non si rigenerano per avere il verde: si
spiega la prima divergenza, poi si decide.

### Fase 0: reti di sicurezza
- Test rossi `xfail(strict=True)` in `tests/audit/` per D59-D68, dalle
  riproduzioni dei rapporti (come il primo passaggio dell'audit).
- Modalità rigorosa nei test: un'eccezione dentro un effetto fa fallire il
  test (oggi è ignorata in silenzio e la partita può restare modificata a metà).
- Tracce deterministiche: il tracciatore semina gli agenti come la factory e
  registra decisioni, scelte (bersagli, modi), chain e risoluzioni; accendere
  la traccia non deve cambiare la partita (va verificato).
- Le 28 golden restano; si aggiungono tracce di decisione per D62 e D63.
- La rete vera sono i test (200/212 tipi di effetto); le partite dei sei mazzi
  ne eseguono 53: servono per i tempi e le sequenze, non per la copertura.

### Fase 1: identità, passo A (D66-D68), cioè le copie
- Nelle tre memorie (`once_per_turn_used`, `combat_designated`,
  `conquer_return`) si salva l'oggetto invece del suo indirizzo `id()`: le copie
  lo ricollegano da sole. La partita vera non cambia (Riven resta com'è: passo B).
- Previsione della revisione: nessuna delle 28 golden cambia.
- Verifica: i test D66-D68 passano; la sonda sulle copie torna a 0 divergenze.
- Da decidere: una copia con un `GameLoop` nuovo azzera `units_played` e
  `spells_cast` (il `Result` di una copia).
- Perché per prima: è piccola, non cambia la partita vera, e la ricerca smette
  di giocare copie sbagliate proprio con i mazzi in uso (Kha'Zix Mutating
  Horror e Shadow Clone nel mazzo Kha'Zix, Pyke Returned nel mazzo Evelynn).

### Fase 2: esiti delle azioni (D59-D62)
Rapporto `design_action_outcomes`, in commit separati:
1. un esito esplicito (applicata, rifiutata, movimento chiuso, pass) e chi
   agisce dopo, introdotto "in ombra": nessun cambio, 28 golden identiche;
2. finestre annidate (D59): l'abilità scelta in reazione o in showdown con un
   movimento in sospeso si esegue; lo showdown dovuto non si perde e non si apre
   dentro una chain. Non basta toglierla dal menu: violerebbe §430.3;
3. gear e nascondere (D60, D61): l'esito viene dal fatto che l'azione è
   avvenuta, non dalla mano o dai conteggi;
4. la serie dei pass dopo un'abilità Add (D62): una golden cambia nella traccia
   delle decisioni (3 occasioni in più), non nel risultato.
Tutti i chiamanti usano lo stesso esito: partita vera, `base_agent`,
`net_mcts`, ISMCTS, coach.

### Fase 3: movimento atomico (D63)
Il gruppo di unità si sceglie prima dei trigger (§144.3). Cambia come
`random` e `simple_trade` scelgono i gruppi: guardare prima le due golden
indicate dalla revisione; i loro risultati finali non sono previsti.

### Fase 4: morti effettive (D64), poi registro e coach
`_route_deaths` restituisce le morti vere (dopo le sostituzioni); "se lo
uccide" e gli XP usano quelle. Poi registro delle partite e commento del coach
(errori di narrazione, non di regole; vedi BACKLOG).

### Fase 5: identità, passo B (D65)
Identità secondo le regole: un cambio di zona crea un oggetto nuovo (§124 e
seguenti, tabella nel rapporto `design_stable_identity`, sezione 2). Fiducia
media nel progetto: prima i test della sezione 4 di quel rapporto.

### Fase 6: struttura
Solo dopo le fasi 1-5. Resta valido il problema misurato nella v1: `loop.py`
8.448 righe in una classe; gli effetti usano 94 metodi interni del motore (447
chiamate) e scrivono direttamente nello stato; i test chiamano circa 141 metodi
interni. Cambia il criterio di riuscita:
- conta chi possiede le modifiche di chain, zone e tempi, non i trattini bassi
  né le righe (quelli restano numeri diagnostici);
- una sola procedura per far avanzare la partita, usata dal gioco vero e dalla
  ricerca;
- `loop.py` si divide per ultimo, controllando che nessun metodo sia definito
  in due pezzi.

## 5. Protezione del lavoro
- Punto di partenza: `main` dopo la PR che aggiunge questo file. Il tag
  `pre-ristrutturazione`, se creato, indica `e72318e`: stesso codice.
- `main` cambia solo con il merge di una PR verificata e l'ok dell'utente. Mai
  push diretti né force push su `main`.
- Branch corti, una fase o un fix per volta; tracce e impronte di riferimento
  si rigenerano dal `main` di partenza di ogni fase.

## 6. Cosa non fare
- Dividere `loop.py` o rinominare metodi insieme a un fix di comportamento.
- Correggere bug di passaggio: ogni cambio di comportamento è una deviazione,
  con test e commit propri.
- Rigenerare golden per avere il verde; togliere o saltare test.
- Sostituire un controllo sui conteggi con un'altra impronta parziale.
- "Sistemare" i controlli prima/dopo che la revisione ha trovato sani:
  canalizzare rune, Minefield, scelta dei modi, presenza sul campo.
- Toccare training e rete: fuori perimetro.

## 7. Avanzamento
- [ ] Fase 0: test rossi D59-D68, modalità rigorosa, tracce deterministiche
- [ ] Fase 1: identità passo A (D66-D68)
- [ ] Fase 2: esiti delle azioni (D59-D62)
- [ ] Fase 3: movimento atomico (D63)
- [ ] Fase 4: morti effettive (D64), registro e coach
- [ ] Fase 5: identità passo B (D65)
- [ ] Fase 6: struttura
