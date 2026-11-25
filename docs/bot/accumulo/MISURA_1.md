# MISURA 1 - §8 accumulo: frequenza e profondità di ricerca (25/11)

Solo misura, nessun codice toccato. Checkpoint `runs/sett/ekris_s12/ckpt_040000.pt` (non committato).
## Cosa è stato lanciato
- `episodi.py --matchup {ES,EK} --semi 1-40 --posti A B --esempi 500`: 80 partite per matchup, tutte (nessuna riduzione),
  138 iterazioni (campione della pagina), sonda accesa. Profilo regole: `6427b90+D72-D80` (default di `decisione_rs`,
  `REGOLE_D72_D80`), usato da `episodi.py` e dai `rifai --autonoma`. I `rifai --pagina` rigiocano col profilo salvato nel
  file (`6427b90+D72-D77`), non col D80.
- I file pagina hanno i mazzi con percorsi assoluti del Mac di Matteo: per rigiocarli ho creato il link
  `/Users/mateo/projects/rbsim2026/rbsim-rust` -> repo (fuori dal repo). Il file 154531 è salvato senza iterazioni
  (-> 42 come all'epoca): per lui 42 138 500 2000. Gli altri 138 500 2000.
## 1. Frequenza (§8: unità giocata/mossa su campo già controllato, senza nemici, avversario ne controlla un altro)
| matchup | partite | decisioni esaminate | episodi §8 | tasso | partite con >=1 |
|---|---|---|---|---|---|
| ES | 80 | 2833 | 380 | 13,4% | 73/80 |
| EK | 80 | 2852 | 356 | 12,5% | 71/80 |
Play/Move: ES 307/73, EK 305/51; picco ai turni 7-13.
Margine = Might del campione già sul campo (l'avversario ha 0):
| matchup | 1-2 | 3-5 | 6-9 | 10-14 | 15+ | mediana | p10 | p90 | max |
|---|---|---|---|---|---|---|---|---|---|
| ES | 6 | 46 | 84 | 100 | 144 | 12 | 5 | 22 | 32 |
| EK | 10 | 49 | 79 | 96 | 122 | 11 | 4 | 21 | 31 |
Punti del campione al momento (campione-avversario): ES avanti 108, pari 165, indietro 107; EK avanti 143, pari 153,
indietro 60. Punti del campione 2-5 nell'80% dei casi. Quindi: spesso il margine è ampio (>=10 nel 64%) e non si è in vantaggio.
## 2. Profondità vs valutazione (5 episodi autonomi, 138/500/2000; alt = "Play X" cioè in base / Move su campo avv.)
| episodio | margine, punti | 138 riproduce | scelta 500 | scelta 2000 | alt visite/q a 138 / 500 / 2000 | BF q |
|---|---|---|---|---|---|---|
| ES:4:a k13 t9 Play Pyke to BF0 | 3, 3-4 | sì | =orig | Play Reckless Innovator to BF0 | 16/-.56, 52/-.56, 154/-.56 | -.52 |
| EK:2:a k10 t5 Play Fizz to BF0 | 6, 3-1 | sì | =orig | =orig | 6/.68, 19/.68, 57/.68 | .73 |
| ES:1:b k7 t6 Play Pyke to BF0 | 13, 2-2 | sì | Hide Gutter Guardian @BF0 | =orig | 5/.03, 15/.03, 35/.03 | .14-.17 |
| EK:8:a k16 t9 Play Bedeviling Stranger to BF0 | 22, 4-3 | sì | =orig | =orig | 47/.74, 157/.74, 535/.74 | .75 |
| ES:4:a(B) k24 t12 Move Rengar base->BF1 | 8, 6-4 | sì | =orig | =orig | Move->BF0 (avv.) 10/.80, 31/.80, 86/.80 | .85 |
A 500/2000 nessuna scelta porta l'unità in base o sul campo avversario. "In base" è sempre nel menu e visitata
(4-17% delle visite), q 0,01-0,14 sotto BF. Per il Move l'unica alternativa nel menu era il campo avversario (.80 vs .85).
Raw: `raw/ep{1,3,4,5}_*.json` (ep2, 364 KB, non salvato: >200 KB).
## 3. Partite salvate di Matteo (campione = posto opposto a `info.seat`): 13 decisioni §8, tutte riprodotte a 138
| file / turno (k) | scelta a 500 | scelta a 2000 | alt "in base" visite/q a 138 / 500 / 2000 |
|---|---|---|---|
| 154531 t9 (4) Pit Rookie BF0 | =orig | =orig | 1/.52, 3/.58, 168/.96 (BF q .96) |
| 154531 t11 (8) Ruin Runner BF1 | Kinkou Initiate | Kinkou Initiate | 19/.82, 47/.82, 97/.82 (BF .85, resta 1o/2o) |
| 154531 t13 (13) Faefolk BF1 (a 138 e 2000 Cast Rampage) | =orig | Cast Rampage | 7/.95, 17/.95, 118/.99 (BF .99) |
| 201243 t6 (4) Pit Rookie BF0 | =orig | =orig | 1/-.10, 1/-.10, 8/.12 (BF .30) |
| 201243 t6 (7) Sett Kingpin BF0 | =orig | =orig | 24/-.21, 64/-.21, 157/-.21 (BF -.11) |
| 201243 t8 (11) Trifarian Captain BF0 | =orig | =orig | 10/-.64, 35, 137 (BF -.62) |
| 201243 t10 (13) Fiora BF0 | =orig | =orig | 3/-.45, 12/-.40, 31/-.40 (BF -.31) |
| 203513 t6 (6) Zed BF1 (segnalato) | =orig | =orig | 0/-, 0/-, 1/-.15 (BF -.05, 1998 visite su 2000) |
| 203513 t8 (8) Reckless Innovator BF1 | Fizz Trickster BF1 | Fizz Trickster BF1 | 1/-.16, 2/-.16, 27/.16 (BF .22) |
| 203513 t10 (11) Fizz BF1 | =orig | =orig | 16/-.26, 32/-.26, 69/-.26 (BF -.14) |
| 203513 t10 (15) Traveling Merchant BF1 | Cast Up from the Deep @BF0 | idem @BF1 | in base 48/-.23, 148, 438 (BF1 23/-.19, 90, 401) |
| 204705 t10 (20) Trifarian Captain BF1 | =orig | =orig | in base 103/.94, 376, 1526 (BF1 6/.94, 22, 94) |
| 204705 t16 (44) Pit Rookie BF0 | =orig | =orig | 35/.79, 119/.79, 414/.79 (BF .80) |
201243 (campione Sett, posto A): §8 ai turni 6,6,8,10, nessuno al 12. Raw: `raw/pg_*.json`.
## Conclusioni
- §8 è frequente (circa 1 decisione su 8 in entrambi i matchup), con margini grandi e punteggio non favorevole.
- Più ricerca non lo corregge: su 18 episodi (5+13) a 2000 la stessa unità non va mai in base/sul campo avversario;
  la scelta cambia in 5/18 (a 500 in 4/18), sempre verso altre mosse (altra unità, Hide, magia). A 2000 l'alt "in base"
  ha spesso q uguale a quella su BF: `table_value` non distingue, decidono prior e spareggio.
- Anomalia: la scelta non è l'argmax delle visite (203513 t10 Merchant e 204705 t10 Captain: scelto "to BF1" con 23 e 6
  visite contro 48 e 103 di "in base"). Da verificare in `search.rs` come si sceglie la mossa finale.
