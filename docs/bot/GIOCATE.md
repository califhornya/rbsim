# Le giocate dei bot: la partita 35.010 e oltre (23/11)

Origine: il controllo di Astra sul replay della partita 35.010 di
`runs/sett/ekris_s12` (Evelynn-Sett, seed 121035009, pesi `ckpt_035008`, la
stessa rete ai due lati, campionata, senza ricerca) e le sue cinque domande.
Qui: che cosa è osservato, dove, e che cosa resta da misurare sul Mac.

Dove si è lavorato: un container senza `runs/` (niente pesi) e senza torch,
sul commit 01d4cb0 (ramo `claude/rbsim2026-boot1-results-373ku0`).
`riftbound/` è identico tra 3fefc8b (il replay) e 01d4cb0: il codice di
Switcheroo esaminato è quello del replay. Non è verificato che il processo
sul Mac giri su questo codice: `scripts/diag/switcheroo_casi.py`, lanciato
lì, lo dice in pochi secondi. Arena: non toccata.

## 1. Switcheroo nel motore (osservato)

"Swap the Might of two units at the same battlefield this turn." Le due unità
sono bersagli (§355.7-355.10), "at the same battlefield" è la restrizione del
gruppo (§355.11). `effects._swap_might` cerca prima una coppia amica-nemica in
cui la nemica ha più Might; senza, non fa nulla; con, lascia scegliere un campo
qualsiasi con due unità e due unità qualsiasi lì.
`python scripts/diag/switcheroo_casi.py`, tavoli costruiti:

| caso | testo e regole | motore |
|---|---|---|
| due amiche sole su un campo | scambio valido | offerta, si paga, nessuno scambio |
| amica 5 contro nemica 2 | valido | offerta, si paga, nessuno scambio |
| due nemiche, una 5 con 3 danni | valido (a 1 Might con 3 danni muore) | offerta, si paga, nessuno scambio |
| nessun campo con due unità | §355.8: non si gioca | offerta, si paga, nessuno scambio |
| tavolo del replay, Valley | valido (Evelynn e Pyke allo stesso campo) | come nel replay: Evelynn 3, Pyke 2 |
| replay, Bandle, Vex con Fiora a 6 (MIGHTY: DEFLECT) senza il potere della tassa | §809.1.c: Fiora non si può scegliere | scelta gratis: Vex 6, Fiora 4 |
| come sopra, con un potere in più | tassa pagata | tassa pagata |
| da coperto a Bandle, scelta Valley | §811.1.d.2: i bersagli a Bandle | scambio a Valley |

Quattro deviazioni, da registrare come **D71** (proposta, non applicata):
a) giocabile senza due unità allo stesso campo (`has_valid_target` non conosce
`swap_might`: per la legalità ha sempre bersagli); b) il controllo preliminare
annulla scambi validi (due amiche, due nemiche, amica più forte); c) da
coperto il campo non è ristretto (§811.1.d.2); d) i bersagli non passano da
`_can_choose`: DEFLECT non pagabile, "can't be chosen" ignorati.
Nel replay (dalla mano, dice l'utente) nessuna delle quattro spiega la mossa:
lo scambio a Valley è legale. Ma (a) e (b) fanno sprecare la carta nel
training: nelle 8 partite del bot a mano finite finora (sezione 4), Kha'Zix
lancia Switcheroo con Zed 6 e Fizz 3 soli a Zaun Warrens: pagata, nulla.
Correzione proposta: in `_HAS_OPTION` un campo con due unità sceglibili (da
coperto: quello); in `_swap_might` nessun controllo preliminare, campi e unità
filtrati da `_can_choose`, il suggerimento di base resta la coppia
vantaggiosa se c'è. Un test in `tests/audit/` per ciascuna delle quattro.
Effetto: cambiano le partite con Switcheroo (Evelynn 2 copie, Kha'Zix 1):
golden da rigenerare con motivo, e le misure dopo il fix non sono confrontabili
uno a uno con quelle di prima. Da fare dopo l'arena, se l'utente decide.

## 2. Lo showdown del turno 5

Osservato da Astra (replay): Bandle, Vex 4 (Evelynn) contro Irresistible
Faefolk 1 e Fiora Victorious 6; Valley, Evelynn 2 e Pyke 3; la rete gioca
Switcheroo, sceglie Valley al 98,16%, Evelynn al 25,28%.
Aritmetica dai testi (Fiora: a 5+ Might ha DEFLECT, GANKING, SHIELD; SHIELD
+1 in difesa; turno 5 con A che comincia: è di Evelynn, Sett difende), ipotetica
finché non si vede il tavolo vero (abilità della leggenda, altri effetti):
- senza scambio, o con quello a Valley: Vex 4 contro 1 + 6 + 1 = 8, Vex muore;
- Vex con Fiora: Vex 6, Fiora 4 (non più MIGHTY: niente SHIELD): 6 contro 5,
  Vex vive e uccide entrambe, Pyke a Valley fa un Gold;
- Vex con Faefolk o Faefolk con Fiora: Vex muore lo stesso.
Quindi la mossa giusta, se c'era, era Vex con Fiora, e costava una [rune] in
più per DEFLECT. Se Evelynn non l'aveva, nessuno Switcheroo serviva: tenerlo
era meglio. Il motore l'avrebbe lasciata fare gratis (1d): per la rete
l'opzione c'era. Il 98% su Valley è una preferenza forte, non un'estrazione
sfortunata: la rete non lega Switcheroo al combattimento in corso.

Il bot completo delle arene non usa la rete per questa scelta. `PPOPriorAgent`
mette i prior della rete solo nei menu (principale, reazione, showdown); il
campo e i bersagli di una spell li cerca la ricerca con prior uguali
(`net_mcts._TreeChooser`, `cprior = 1/n`) e li valuta `table_value`. Il 98%
non arriva all'arena; arriva invece la scelta di giocare Switcheroo, se il
prior la spinge.
Che cosa fa il bot in quella posizione: da misurare sul Mac (sezione 6). Indizio
dal bot a mano qui: 3 Switcheroo in showdown su 3 sono stati mia contro sua al
campo dello showdown, con guadagno 1, 1 e 7 di Might (8 partite EK).

## 3. Il mulligan di Sett (in corso, qui)

`scripts/diag/mulligan_mano.py`. Mano fissata: Rampage, First Mate,
Showstopper, Irresistible Faefolk; bracci: rimanda Rampage e Showstopper (RS,
la rete al 95%), solo Showstopper (S: tiene Rampage), solo Rampage (R), niente
(-). Stesso seed per i quattro bracci (stesso mazzo mescolato dal seed, le
quattro carte in cima; le pescate di rimpiazzo dalla cima e le rimandate in
fondo, §117); nessun pilota conosce l'ordine (la ricerca determinizza).
Avversario e pilota: il bot a mano a 0,4 s per mossa da entrambi i lati (non
il campione: qui non ci sono i pesi). Chi comincia: alternato per seed. Seed
da 700.000, 300 previsti (1.200 partite, ~9 ore qui con 4 processi).
Parziale a 22 seed: RS 0,59, S 0,36, R 0,73, - 0,59; differenze da RS con IC
95% di ±0,22-0,27: **nessuna conclusione**. La deviazione standard della
differenza appaiata è ~0,53 a seed: per ±0,05 servono ~430 seed per braccio.
Limiti: un'unica mano; il valore di un mulligan dipende da come il pilota
gioca dopo (qui il bot a mano: la risposta vale per lui, non per un umano né
per la rete); 0,4 s a tempo, quindi la forza dipende dal carico della
macchina, ugualmente per i bracci.

## 4. Quanto è diffuso (in corso)

`scripts/diag/giocate.py campione`: partite nuove con seed dichiarati (da
800.000 + 1.000 x indice del matchup), chi comincia alternato; per ogni
decisione la probabilità della mossa giocata; rilevatori: ogni Switcheroo
risolto nella partita vera (con chi, dove, se lo showdown era altrove, se non
ha scambiato) e le carte giocate in base quando la stessa era offerta su un
campo; esempi completi (carte, risorse, campi, finestra) in `ESEMPI.txt`.
Qui gira sul bot a mano (12 partite per EK, ER, EI, ES); la rete va misurata
sul Mac (sezione 6). Finora 8 partite EK: Switcheroo 4 volte, 3 in showdown
mia contro sua al campo giusto, 1 senza effetto (il difetto 1b).

## 5. Che cosa il percorso attuale può e non può dimostrare

- La rete che si vede nei replay è la politica del training: campionata, e da
  sola fa 0,425 contro il bot a mano. Che giochi male in assoluto è atteso;
  che sbagli con il 98% (Switcheroo) è un errore suo, non dell'esplorazione.
  Il Vex in base era invece un'estrazione al 22%, e a 40.000 la rete
  preferisce la sequenza buona (94%): su una posizione, non una misura.
- Il campione delle arene è un altro oggetto: ricerca a mano + prior della
  rete. Le promozioni dicono "più forte del campione precedente, a 0,4 s,
  su questi mazzi". La catena parte dal bot a mano (0,80 contro
  simple_trade, 0,97 contro random); nessuna misura contro un umano.
- Il self-play premia ciò che batte la rete stessa e l'archivio. Gli errori
  che entrambi i lati fanno (Switcheroo fuori dallo showdown) non vengono
  puniti, quindi non si correggono; il limite noto del campione è la
  valutazione a mano e l'orizzonte di un turno (PIANO_FORZA).
- I difetti del motore entrano nel training: Switcheroo giocabile a vuoto
  insegna che la carta vale poco.
- Per sapere se è un avversario utile per Matteo servono misure ancorate a
  un umano: i giudizi di GIUDIZI.md e gli scenari (`scenari.json`) sul
  campione; posizioni delle sue partite RiftAtlas con la sua mossa (il
  registratore c'è); poche partite vere contro di lui, registrate; e un
  pannello di "errori evidenti" scritto da lui (come questo Switcheroo) su
  cui il campione deve scegliere bene.

## 6. Da lanciare sul Mac, ad arena finita

Le arene contano il tempo (0,4 s per mossa): niente in parallelo.

    R=runs/sett/ekris_s12
    python scripts/diag/switcheroo_casi.py
    python scripts/diag/giocate.py partita --seed 121035009 --starter a --matchup ES \
        --ckpt $R/ckpt_035008.pt --confronta $R/ckpt_040000.pt
    # nel file: il numero # dello showdown con Switcheroo, poi
    python scripts/diag/giocate.py bot --seed 121035009 --starter a --matchup ES \
        --ckpt $R/ckpt_035008.pt --decisione N \
        --prior $R/ckpt_040000.pt runs/rengar/ekr_s8/ckpt_020032.pt --volte 10
    python scripts/diag/giocate.py campione --ckpt $R/ckpt_040000.pt --partite 20 --out runs/giocate/rete
    python scripts/diag/giocate.py campione --prior runs/rengar/ekr_s8/ckpt_020032.pt \
        --partite 6 --out runs/giocate/campione

La prima riga di `partita` dice se la ricostruzione coincide con quella di
Astra (vince Sett 8-4 al turno 12, 71 decisioni); chi comincia ("a") è
ricavato da `batch_games` (partita "self", indice 4.376 tra le ES: pari, comincia A;
Astra conta 71 scelte con la stessa regola: una scelta a opzione unica non conta).
Lo script `giocate.py` è collaudato qui con reti finte (riproduzione
identica due volte, anche con il journal acceso; il passaggio al bot): con
le reti vere non è stato eseguito.
