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
da 700.000.
Fermata a 40 seed (160 partite, decisione dell'utente: non vale 8 ore qui).
Sett: RS 0,45, S 0,30, R 0,73, - 0,60. Differenze da RS (IC 95%, appaiate):
S -0,15 ± 0,13, R +0,28 ± 0,20, - +0,15 ± 0,18. Con il bot a mano come pilota,
rimandare solo Rampage (tenere Showstopper) sembra meglio della scelta della
rete, tenere Rampage peggio: il contrario dell'ipotesi su Rampage. Tre
confronti senza correzione (con Bonferroni R resta sopra RS di poco: ±0,24);
indizio da confermare, non risultato. La deviazione standard della
differenza appaiata è ~0,6 a seed: per ±0,05 servono ~500 seed.
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

## 7. Il campione nella pagina coach: Call to Glory e Punch First sprecate (25/11)

Osservata da Matteo giocando a mano (`scripts/coach.py`, campione
`ckpt_040000.pt` a 0,4 s, motore Python). Posizione non salvata: la pagina non
tiene lo stato completo; la prossima volta "Segnala un problema" sul momento.

- **Posizione.** Sett (Matteo) contro Sett (campione), turno 11, punti 5-3 per
  Matteo. Il campione sposta Sett Kingpin dalla base a Packed Amphitheater,
  controllato da Matteo: showdown. Kingpin a 6 (5 + 1 del campo per i
  campioni; nessun buff). Di Matteo lì: un'unità di Might 2 (e Pillaged
  Armory); Matteo ha 1 energia e una carta in mano (Fiora Victorious).
- **Giocata.** Prima di qualsiasi mossa di Matteo, il campione lancia Call to
  Glory (REACTION, +3 Might fino a fine turno) sul Kingpin, pagando le 3
  energie (non ha un buff da spendere): una carta per uno scontro già vinto
  6 a 2.
- **Poi.** Sempre prima di una mossa di Matteo, Punch First (ACTION, +5 fino
  a fine turno; 1 energia e 2 Power Body): Kingpin a 14 contro 2. In tutto
  due carte, 4 energie e 2 Power per uno scontro che vinceva a 6.
- **Atteso (Matteo).** Passare e aspettare la reazione dell'avversario; Call
  to Glory è una REACTION: si gioca dopo, solo se serve, quando la reazione
  dell'avversario rimette in discussione il vantaggio di Might.
- **Ipotesi, non verificate.** La ricerca dello showdown guarda un passo
  (`reaction_iterations`) su copie con la mano di Matteo ricampionata: in
  alcune Matteo ha un trucco e il +3 lo copre, e il valore di "tenere la
  reazione per dopo" non si vede in un passo. `table_value` pesa il tavolo
  più delle carte in mano; l'energia avanzata si perde a fine turno, quindi
  il costo visto è solo la carta. A 0,4 s le visite sono poche.
- **Cosa si esclude.** Non è il +5 visto come guadagno: `table_value` conta
  la Might che resta oltre il turno (`handwritten._m`, `lasting_might`).
  Resta il prezzo: energia e Power avanzati si perdono a fine turno, e una
  carta in mano vale 0,03 contro 0,30 del controllo di un campo e 0,05 per
  punto di Might che resta lì. Come assicurazione contro un trucco della mano
  ricampionata di Matteo, una carta costa poco; ogni showdown è una ricerca a
  un passo, quindi lo stesso conto si ripete a ogni decisione.
- **Da misurare.** Uno scenario con questa posizione (`docs/bot/scenari.json`,
  `riftbound/ai/scenari.py`), ripetuto con semi diversi: quante volte il
  campione lancia Call to Glory o Punch First per primo, se cambia con il
  budget e con il peso delle carte in mano in `table_value`.

## 8. Il campione accumula unità sul campo che tiene (25/11)

Osservata da Matteo giocando a mano (Evelynn contro il campione con Sett,
`ckpt_040000.pt` a 0,4 s, motore Python 6427b90). Posizione non salvata.

- **Posizione.** Turno 11, il campione a 3 contro 4 prima del punto del
  turno (poi 4-4): tiene Packed Amphitheater con Might 24, Matteo tiene
  Monastery of Hirana. Il campione gioca Rengar Trophy Hunter lì invece che
  in base. Turno 15, 6-6: di nuovo lì Vi Peacekeeper (Might 31 sul campo,
  0 di Matteo).
- **Atteso (Matteo).** Con un campo già al sicuro, le unità nuove servono
  per entrare nel campo dell'avversario: Rengar e Vi sono fatti per questo.
- **Cosa c'è nel codice.**
  - `handwritten.table_value` (la valutazione del campione): 0,05 per punto
    di Might su un campo, senza limite, contro 0,03 in base. Un campione
    giocato sul proprio campo vale (6 + 1 di Packed Amphitheater) × 0,05 =
    0,35, in base 6 × 0,03 = 0,18: accumulare è premiato anche quando il
    campo è già al sicuro.
  - Un'unità su un campo torna solo in base (nessuno spostamento da campo a
    campo senza GANKING): accumulare lì la blocca per un turno in più.
  - La ricerca del turno non vede l'attacco del turno dopo: il valore di
    avere unità in base, pronte a entrare, non compare.
  - Rengar: sul motore della pagina (6427b90, D72 aperto) non si può giocare
    su un campo dove ci sono solo nemici; l'ingresso diretto nel campo di
    Matteo non era fra le mosse. Sul profilo corretto (Rust) sì.
- **Da misurare.** Scenario da questa posizione (`docs/bot/scenari.json`), con
  semi diversi: dove gioca Rengar e Vi (base o campo già tenuto) e quanto
  spesso attacca il campo avversario nei turni dopo.
- **Possibili correzioni (da provare in arena, coppie a posti scambiati).**
  Rendimento decrescente della Might oltre quella che serve a tenere il
  campo; Might in base pesata come minaccia per il turno dopo; un termine
  per la corsa ai punti quando i campi sono uno a testa.
- **Esito (26/11).** Più iterazioni non correggono (`docs/bot/accumulo/MISURA_1.md`): è la valutazione. Ridurre sempre il
  Might in eccesso (`accumulo`) peggiora (EK 0,431, ES 0,465); una minaccia logistica (`minaccia`, `corsa`) non cambia le
  mosse; `rimonta` (solo quando a campi fermi si perde la corsa ai punti: Might in base verso il campo avversario più
  debole, eccesso sul campo sicuro ridotto, i propri campi minacciati prima) vince: EK 0,522, ES 0,533, gli altri 8
  matchup 0,515-0,607 (semi nuovi, `docs/bot/accumulo/risultati/`). Default della pagina dal 26/11 (`coach.py --valutazione`).
- **Prova di Matteo (26/11).** Partita 013325 (Evelynn-Sett, `rimonta`, `6427b90+D72-D81`, probabilmente la prima
  delle due): vinta 8 a 4 in 14 turni. Alla domanda «quale giocata di Sett ti ha costretto a spendere una carta o a
  difendere il campo prima dell'ottavo punto?»: nessuna, «non ho trovato molte difficoltà». L'unica occasione è il T9
  (SEGNALAZIONI 28): schianto contro Vex, Sett su Bandle e Vi in AMBUSH, che la ricerca ha provato 1 volta su 5000.

## 9. Prima togliere il pezzo che blocca, poi giocare (26/11)

Da Matteo (partita 013325, Evelynn-Sett, T9; SEGNALAZIONI 28).

- **Il ragionamento atteso (Matteo).** «Ho qualcosa che può entrare accelerato, o con una meccanica come Vi o
  Rengar (AMBUSH)? Se sì, prima devo sbarazzarmi di Vex, l'elemento che blocca: come faccio?» Non una mossa
  precisa, un ordine: si toglie il pezzo che punisce le proprie giocate, poi si gioca.
- **Che cosa ha fatto il campione.** Vi in base con Vex vivo (Vi stordita: non si muove né combatte nel turno), poi
  Sett su Valley, poi Kinkou + Punch First su Bandle uccidono Vex e Momentary Companion. Vex è morto nello stesso turno,
  ma dopo: invertire l'ordine lasciava Vi libera di entrare in AMBUSH nello showdown di Bandle.
- **Perché la ricerca non lo vede.** Lo stordimento dura il turno: a fine turno Vi stordita in base vale quanto Vi
  libera in base, e la valutazione dà lo stesso valore ai due ordini (q 0,12 per «Vi in base» e «Sett su Valley»).
  L'ordine conta solo se Vi fa qualcosa in questo turno, una linea di 3-4 mosse (schianto, Sett su Bandle, AMBUSH)
  il cui primo passo ha avuto 1 visita su 5000 (q -0,76: Kinkou da solo contro 18 Might, prima di vedere Punch First).
- **Da misurare.** In `scripts/rust/episodi.py` un rilevatore: il campione gioca un'unità mentre un Vex avversario è su
  un campo (l'unità viene stordita) e Vex muore più tardi nello stesso turno = ordine sbagliato; anche: unità
  giocata e stordita senza che Vex muoia. Autonome ES ed EK sul Mac col campione: quanto spesso succede, poi `rifai`
  sugli episodi. Correzioni solo dopo la misura, una alla volta (dopo §7).
- **Esperimento sul Mac (26/11, `docs/bot/esperimenti/`, schema di Astra).** T9 di 013325, k=10, stessi mondi nelle
  4 condizioni.
  - Continuazioni campione contro campione, 100 mondi per prima mossa (poi mosse libere): Vi in base 5/100,
    Kinkou su Bandle 2/100 (differenza -3 [-9, +3]), Sett su Valley 0/100 (-5 [-11, -0]). La posizione era già
    persa per Sett; il primo passo di Matteo non risulta migliore.
  - Ricerca: con le finestre «Vi in base» sale da q 0,12 a 0,40 (Punch First del campione in 2139 simulazioni su
    4894) e «Sett su Valley» scende a -0,27: l'ordine ora conta. Senza finestre a 1000 iterazioni sceglieva Sett su
    Valley (la peggiore nelle continuazioni), con le finestre Vi in base a 1000 e 5000. Con la quota Kinkou riceve
    100 visite, Punch First in 91, Vi in AMBUSH in 15, e resta a q -0,75.
  - La linea intera di Matteo (`guidata`) si è fermata al passo 4: dopo uno spostamento serve «Pass» per chiudere
    la mossa e aprire lo showdown; la sequenza non lo aveva. Da rifare, con una continuazione che la impone tutta.
  - Rilevatore §9 (campione `storica`, 50 partite, posto B): ES 105 occasioni, Vex uccisa dopo 15, ordine giusto 3;
    EK 114 occasioni, uccisa dopo 14, ordine giusto 2. L'ordine sbagliato è ~5 volte più frequente di quello giusto.
- **Secondo giro (26/11, Astra).** Arena `rimonta`+finestre contro `rimonta`, 138 iterazioni, 800 coppie per matchup
  (`docs/bot/finestre/arena_20261126_1056/`): ES 0,474 (0,454-0,494), EK 0,531 (0,513-0,550), blocco 0,503
  (0,489-0,516): NON PASSA, effetti opposti nei due matchup. Il T9 a 138 con le finestre: Vi in base (q 0,24), Sett su
  Valley -0,27, Kinkou 1 visita. Rilevatore per turni unici con scelta possibile (50 partite, posto B): ES `rimonta`
  ordine sbagliato 12, giusto 2, Vex sopravvive 45 (su 60); con finestre 14 / 2 / 40 (57). EK 7 / 2 / 59 (71); con
  finestre 13 / 3 / 51 (69). Le finestre non insegnano a togliere Vex prima: lo stordimento finisce col turno e la
  valutazione di fine turno non lo vede. La linea condizionale di Matteo (Punch First solo se risponde, danni su
  Vex) non è ancora misurata: due errori nella sequenza e nel comando (zsh conta gli array da 1).
- **La linea di Matteo, misurata (26/11, `t9_guidata4_*`, `t9_continua4`).** Armory su Kinkou (4), Kinkou su Bandle,
  Punch First solo se l'avversario risponde (nel 26% dei mondi), danni su Vex: Vex muore per primo, Sett The Boss
  salva Kinkou, e il campione prende comunque il punto di Valley (3-3 a fine turno). Su 100 mondi appaiati: linea di
  Matteo 6 (poi finestre 7), Vi in base 5 (poi finestre 8); differenze -1..-3 punti, intervalli ±8. Le linee sono
  equivalenti entro la misura: la posizione era decisa (Sett vince 5-8 su 100 comunque). Per il §9 conta la
  frequenza (rilevatore), non questo turno.
