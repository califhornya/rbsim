# Riftbound Tournament Rules — match-relevant excerpt

Verbatim from the official Riftbound Tournament Rules, revision 2026-10-09
(supplied by the user as the riftbound.gg page, 2026-10-25). Only the sections the
simulator models are kept; the Tournament Rules take precedence over the Core
Rules for competitions (104.1). Implemented in `riftbound/core/match.py`.

## 402. Deck Size
- 402.1. In a constructed event, players must use a Main Deck of exactly 40 cards
  (including a chosen champion), 1 Legend, 12 runes, and exactly 3 battlefields
  each with a unique name.

## 403. Sideboard
- 403.1. In certain competitions, players may have a group of additional cards
  (outside of their starting configuration) called a sideboard.
- 403.2. Sideboard size and contents are dictated by the competition format.
- 403.3. Limits on copies of named cards as defined by competition format apply
  to the combination of Main Deck and sideboard.
- 403.4. Players may use sideboard cards to modify their deck in between games of
  a match. In constructed, sideboard cards must be exchanged 1 for 1 with Main
  Deck cards.
  - 403.4.a. During that time, a player may change their Chosen Champion to one
    from their sideboard or Main Deck that meets the deckbuilding rules of the
    competition format.
  - 403.4.b. In constructed formats, a player may not change their Runes, Legend,
    or Battlefields at any point after deck registration.
  - 403.4.c. After the sideboarding process, a player's Main Deck must meet deck
    size requirements dictated by the competition format.
- 403.5. Players may not use sideboard cards in the first game of a match.
- 403.8. A player's deck and sideboard must be returned to their registered
  states before the first game of the next match.
- 403.9. If a match completely skips the first game due to a penalty, neither
  player may sideboard for the following game.
- 403.10. If a game ends in a draw, neither player may sideboard for the
  following game.
- 403.11. If a game restarts due to an in-game effect or due to corrective action
  by judges, the state of each player's deck and sideboard must remain the same
  in the restarted game.

## 404. Match
- 404.1. A match of Riftbound consists of a series of games that are played until
  one side has won a predetermined number of games.
- 404.2. Most matches of Riftbound are "best of 3," meaning the predetermined
  number of games to win is 2.
- 404.3. Games that end in a draw do not count toward this goal.
- 404.4. If the competition round ends (due to time limits) prior to any side
  achieving the goal, the winner of the match is the one who has won the most
  games.
- 404.5. If all sides have equal game wins, the match is a draw.

## 406. Start of Game Procedure (excerpt)
- 406.1.a. In competitions where sideboards are allowed, players may exchange
  cards from their main deck and their sideboard after each game of a match.
- 406.1.b. If a game ends in a draw, players must use the same battlefields for
  the following game. *(Not used in practice, per the user. In the simulator a
  draw only happens when time runs out, which ends the match, so the "game after
  a draw" rules — 403.10, 406.1.b, 407.4 — never come up.)*
- 406.1.c. If a game ends due to a game loss penalty after players have selected
  and revealed their battlefields, players must use different battlefields for
  any following games in the match.
- 406.1.h. For "best of 1" competitions the head judge may use an altered setup:
  each player randomly selects one of their three battlefields; the designated
  player (407) chooses to go first or last; players then sideboard as if between
  games of a "best of 3". *(Not modeled.)*

## 407. Play First Rule
- 407.1. For the first game of a match, a designated player decides whether they
  wish to play first or last.
- 407.2. Any random method that is agreed upon by all players in the current game
  may be used to determine the designated player.
  - 407.2.a. At high OPL, during playoff matches that occur following the end of
    Swiss rounds, the higher ranked player from the Swiss rounds is automatically
    the designated player for the first game of each match.
- 407.4. For games after the first game of a match, the loser of the previous game
  gets to choose if they play first or last. If the previous game was a draw, the
  starting play from the previous game is maintained.

## 408. End of Match Procedure (excerpt)
- 408.2. If the time limit for a competition round is reached before a winner is
  determined, the player whose turn it is finishes their turn.
  - 408.2.a. After that player's turn is complete, three additional turns are
    played, and then the match ends.
  - 408.2.b. If the game is incomplete at the end of the additional turns, a
    player is declared the winner of the game if they have a point lead of two or
    more. If no player has a point lead of two or more, the game is a draw.
  - 408.2.d. If the players are between games when the round time ends, no new
    game is started.
- 408.3. The winner of a match is the first player who reaches the appropriate
  game win score.
  - 408.3.a. If neither player has reached that score by the end of the end of
    match procedure, the player with more game wins wins the match.
  - 408.3.b. If players are tied on game wins, the match is a draw.

*(Riftbound has no turn limit. A best of 3 has a 60-minute cap (per the user). The
simulator converts the clock to turns across the whole match at an estimated
1⅓ minutes per turn (45 turns) and applies 408.2 when it runs out; its per-game
`max_turns` is only a stall guard and counts as the time running out. In practice
this is how a 1-1 match gets decided in game 3.)*

## 601.1.c. Constructed sideboards
- 601.1.c.1. A player's sideboard can include 10 or fewer cards.
- 601.1.c.2. A sideboard can consist only of valid Main Deck cards.
- 601.1.c.3. Limits on copies of named cards apply to the combination of main
  deck and sideboard.
- 601.1.c.4. A player may change their Chosen Champion to one from their sideboard
  or main deck that matches their Legend whenever sideboarding would be allowed.

## 601.3. Standard (as of this revision)
Origins supplemental set in Proving Grounds (OGS), Origins (OGN), Spiritforged
(SFD), Unleashed (UNL), Vendetta (VEN), Radiance (RAD; released October 23rd, 2026).
