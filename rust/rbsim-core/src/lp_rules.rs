//! py: loop.py — play restrictions, points and victory, passives counted
//! by side, discarding, leaving the board.

use crate::cards::py_int;
use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _play_forbidden(actor, card)
    pub fn play_forbidden(&mut self, actor: Side, card: CardId) -> R<bool> {
        let side = actor;
        let t = self.gs.turn;
        if self.gs.cant_play_cards_turn.get(&side) == Some(&t) {
            return Ok(true);
        }
        if self.gs.is_spell(card) && self.gs.cant_play_spells_turn.get(&side) == Some(&t) {
            return Ok(true);
        }
        if self.has_effect(card, "requires_friendly_gear") || self.has_effect(card, "requires_pet") {
            not_ported!("_play_forbidden", "requires_friendly_gear / requires_pet");
        }
        for es in self.gs.spec(card).effects.clone() {
            if let Some(ac) = es.additional_cost.as_ref().filter(|v| crate::cards::truthy(Some(v))) {
                if !self.additional_cost_optional(card) && !self.pay_one_additional_cost_x(card, actor, ac, true)? {
                    return Ok(true);
                }
            }
            if es.effect == "play_restriction"
                && self.gs.turns_taken[side.idx()] < es.params.get("min_turn").map(py_int).unwrap_or(0)
            {
                return Ok(true);
            }
        }
        if self.gs.is_spell(card) {
            // "While I'm at a battlefield, opponents can't play spells with that name" (Fallen Feline)
            let name = self.gs.name(card).to_string();
            for u in self.units_at_battlefields_with(side.other(), "name_spell") {
                if self.gs.card(self.gs.ucard(u)).named_spell.as_deref() == Some(name.as_str()) {
                    return Ok(true);
                }
            }
        }
        Ok(false)
    }

    /// py: _points_allowed(side, n, how, bf=None)
    pub fn points_allowed(&mut self, side: Side, n: i64, how: &str, bf: Option<usize>) -> R<i64> {
        if !self.units_at_battlefields_with(side.other(), "opponents_cant_gain_points").is_empty() {
            return Ok(0);
        }
        if (how == "conquer" || how == "hold") && bf.is_some() {
            if let Some(c) = self.gs.battlefields[bf.unwrap()].card {
                for es in self.gs.spec(c).effects.iter() {
                    if es.effect == "no_score_before_turn"
                        && self.gs.turns_taken[side.idx()] < es.params.get("turn").map(py_int).unwrap_or(3)
                    {
                        return Ok(0);
                    }
                }
            }
        }
        if (how == "conquer" || how == "hold") && n == 1 && self.gs.turns_taken[side.idx()] <= 2
            && self.all_units_in_play().iter().any(|&u| self.has_effect(self.gs.ucard(u), "early_score_draws"))
        {
            not_ported!("_points_allowed", "early_score_draws (Otterpus)");
        }
        let points = self.gs.points[side.idx()];
        if how == "conquer" && points + n >= self.gs.victory_score {
            let any_unscored = (0..self.gs.battlefields.len())
                .any(|i| Some(i) != bf && !self.gs.battlefields[i].scored_this_turn[side.idx()]);
            if any_unscored {
                self.draw_one(side, true)?;
                return Ok(0);
            }
        }
        Ok(n)
    }

    /// py: _gain_points
    pub fn gain_points(&mut self, side: Side, n: i64, how: &str, bf: Option<usize>) -> R<i64> {
        if self.gs.reg.regole.d80() && self.gs.winner.is_some() {
            // D80 (profile 6427b90+D72-D80): the game is over at the winning
            // point, the points after it (a second hold, a trigger) aren't gained.
            if n > 0 {
                crate::registry::conta(80);
            }
            return Ok(0);
        }
        let n = self.points_allowed(side, n, how, bf)?;
        self.gs.points[side.idx()] += n;
        self.note_winner();
        Ok(n)
    }

    /// py: _note_winner
    pub fn note_winner(&mut self) {
        let gs = &mut self.gs;
        if gs.winner.is_some() {
            return;
        }
        let [a, b] = gs.points;
        if a >= gs.victory_score && a > b {
            gs.winner = Some(Side::A);
        } else if b >= gs.victory_score && b > a {
            gs.winner = Some(Side::B);
        }
    }

    /// py: _victory -> the winner once someone won
    pub fn victory(&mut self) -> Option<Side> {
        self.note_winner();
        self.gs.winner
    }

    /// py: _passive_count
    pub fn passive_count(&self, side: Side, verb: &str) -> i64 {
        self.sources_in_play(side)
            .into_iter()
            .map(|(src, _)| self.card_effects_auto(src).iter().filter(|es| es.trigger == "passive" && es.effect == verb).count() as i64)
            .sum()
    }

    /// py: _side_has_passive
    pub fn side_has_passive(&self, side: Side, verb: &str) -> bool {
        self.sources_in_play(side)
            .into_iter()
            .any(|(src, _)| self.gs.spec(src).effects.iter().any(|es| es.trigger == "passive" && es.effect == verb))
    }

    /// py: _discard(player, card)
    pub fn discard(&mut self, player: Side, card: CardId) -> R<()> {
        if !self.gs.player(player).hand.contains(&card) {
            return Ok(());
        }
        self.gs.player_mut(player).hand.retain(|&c| c != card);
        self.put_in_trash(player, card, false)?;
        self.gs.discarded_this_turn[player.idx()] = true;
        self.resolve_triggered_effects(card, "on_discarded", 0, player, Some(crate::lp_phases::bf_extra(0)))?;
        if self.discard_depth > 0 {
            if !self.discard_sides.contains(&player) {
                self.discard_sides.push(player);
            }
        } else {
            self.fire_units_trigger("on_you_discard", player, None, Some(card), None)?;
        }
        Ok(())
    }

    /// py: _discard_choice(side, player, cands, source=None)
    pub fn discard_choice(&mut self, side: Side, cands: &[CardId], source: Option<CardId>) -> R<CardId> {
        self.discard_choice_for(side, side, cands, source)
    }

    pub fn discard_choice_for(&mut self, side: Side, player: Side, cands: &[CardId], source: Option<CardId>) -> R<CardId> {
        let gs = &self.gs;
        let pick = if side == player {
            let key = |c: CardId| (!self.has_trigger(c, "on_discarded"), gs.cost_energy(c) + gs.cost_power(c).unwrap_or(0), gs.might(c).unwrap_or(0));
            let mut best = cands[0];
            for &c in &cands[1..] {
                if key(c) < key(best) {
                    best = c;
                }
            }
            best
        } else {
            let key = |c: CardId| (gs.cost_energy(c), gs.might(c).unwrap_or(0));
            let mut best = cands[0];
            for &c in &cands[1..] {
                if key(c) > key(best) {
                    best = c;
                }
            }
            best
        };
        let opts: Vec<Opt> = cands.iter().map(|&c| Opt::Card(c)).collect();
        match self.choose("discard", side, &opts, Opt::Card(pick), source)? {
            Opt::Card(c) => Ok(c),
            _ => unreachable!(),
        }
    }

    /// py: _discard_event (context manager) around `f`
    pub fn discard_event<T>(&mut self, f: impl FnOnce(&mut Game) -> R<T>) -> R<T> {
        if self.discard_depth == 0 {
            self.discard_sides.clear();
        }
        self.discard_depth += 1;
        let out = f(self);
        self.discard_depth -= 1;
        if self.discard_depth == 0 {
            let mut sides = std::mem::take(&mut self.discard_sides);
            sides.sort();
            for s in sides {
                self.fire_units_trigger("on_you_discard", s, None, None, None)?;
            }
            self.discard_sides.clear();
        }
        out
    }

    /// py: _fire_leaves_board(card, owner_side, bf)
    pub fn fire_leaves_board(&mut self, card: CardId, owner_side: Side, bf: usize) -> R<()> {
        self.resolve_triggered_effects(card, "leaves_board", bf, owner_side, Some(crate::lp_phases::bf_extra(bf)))?;
        // _return_stolen_gear: nothing in EK steals gear (Akshan Mischievous).
        Ok(())
    }
}
