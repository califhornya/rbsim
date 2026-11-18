# Questions for the external reviewer: the bootstrap net (19/11)

Branch `claude/rbsim2026-boot1-results-373ku0`. Results: `docs/bot/RETE.md`,
section "Risultati di boot1". Earlier self-play runs: `docs/archivio/
SESSIONE_2026-11-13.md` (run 3, run 4).

## Setup in short
- **Search** (`riftbound/ai/net_mcts.py`): PUCT over the active player's own
  turn only (their actions until they pass); a leaf is scored by a value, no
  rollouts; the opponent's turn is not searched. Hidden information (opponent's
  hand and deck, own deck) is re-determinized every iteration. `backup="best"`:
  a node is worth the best of its children, a line's end the mean of its
  visits. Root move choice under "best": **max Q**, not most visits
  (`_play`, line ~596). Every decision is searched again.
- **Hand-written bot** (`riftbound/ai/handwritten.py`): that search with equal
  priors and `table_value` (points, battlefields, Might that lasts, cards).
  0.80 against simple_trade, 0.97 against random.
- **Net** (`riftbound/ai/net.py`): one embedding per card plus a zone
  embedding plus features, pooled per zone, MLP trunk, policy and value heads.
  Trained on 2,000 games of the bot against itself (Evelynn vs Kha'Zix, 100
  iterations per decision; 30% of decisions sampled, about 14 per game),
  split by seed 1,600 / 200 / 200 (train / epoch choice / final test).
  Targets: the bot's move and the game result. In play, `NetAgent` = the same
  search with the net's priors and value.

## Results (Mac, 18/11)
1. Who wins, on the 200 test games (squared error, 1 = no information): net
   0.466, hand value 0.559. Turns 1-4 / 5-8 / 9+: net 0.514 / 0.396 / 0.485,
   hand 0.761 / 0.516 / 0.516.
2. Four positions with a known right move: net 24/24, 24/24, 24/24, 17/24;
   bot 24/24 in all four.
3. Against the bot, 100 pairs (same seed, net once in each seat), 0.4 s of CPU
   per move each: **0.460 ± 0.053** (95%). With Evelynn 0.63 (bot vs itself
   0.69), with Kha'Zix 0.29 (0.31). Iterations per decision: net 94, bot 114.
4. Against simple_trade: net 0.86, bot 0.80 (200 games each).

The agreed rule was: continue to self-play only if (1) is better **and** (3)
reaches 0.55. So we stopped. Self-play runs 3 and 4 (13/11) also plateaued
at about the same level (0.72-0.80 against simple_trade, net 60 vs net 10 at
0.49). Three attempts, one search: we suspect the search is the ceiling.

## Questions
1. **Better value, same play.** What is the most likely reason a value that
   predicts results clearly better gives no gain in play? Our candidates: (a)
   the imitated priors push the search onto the bot's own moves; (b) accuracy
   on positions from the bot's games is not accuracy in ranking the options of
   one decision; (c) 18% fewer iterations; (d) something in the search.
2. **Max-Q root choice with uneven priors.** Under "best" the root plays the
   child with the highest Q. With the net's priors, low-prior children get few
   visits, so their Q is a max over a few determinized samples: a winner's
   curse. Is that a plausible cause of (3)? Cheapest fix to try: most visits,
   a lower confidence bound, or a minimum number of visits?
3. **"best" backup with one determinization per iteration.** Each line sees
   different hidden cards, and a node takes the max over lines: optimistic,
   and close to strategy fusion. How much would you expect this to cap
   strength whatever the value is, and what is the cheapest check (e.g. "mean"
   backup, or K determinizations shared by every line)?
4. **The decisive test.** We plan one test: the bot with the net's value and
   equal priors (same search), 100 pairs against the bot, pre-registered: ≥
   0.55 → that is the new bot and self-play starts from it; about 0.50 → the
   net path closes. Is this the right test? Equal CPU or equal iterations? Is
   100 pairs (±0.053) enough for that decision?
5. **An offline metric that predicts play.** Instead of squared error over
   positions, something like: at held-out decision points, does the value
   rank the root options the way a long search does (e.g. the bot with 2,000
   iterations), top-1 agreement? Sound and cheap, or is there a better one?
6. **Next step if (4) fails.** The search only looks at one's own turn (a
   simulated opponent turn was tried: 0.44, worse; `docs/bot/
   TURNO_AVVERSARIO.md`). With a Mac M1 Max and a few nights, what would you
   change first in the search, and what would you expect it to buy?
