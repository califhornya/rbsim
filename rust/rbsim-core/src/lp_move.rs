//! py: loop.py — the trash, the Standard Move and moves by effects, move
//! triggers, staged showdowns and the held move.

use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _to_trash(owner, card)
    pub fn to_trash(&mut self, owner: Side, card: CardId) -> R<()> {
        if self.gs.card(card).empowered == Some(true) {
            self.gs.card_mut(card).empowered = Some(false);
        }
        if !self.gs.card_is_token(card) {
            self.put_in_trash(owner, card, true)?;
        }
        Ok(())
    }

    /// py: _trash_banishes
    pub fn trash_banishes(&self, owner: Side, card: Option<CardId>) -> bool {
        self.side_has_passive(owner, "trash_to_banish") || card.map_or(false, |c| self.has_effect(c, "trash_to_banish"))
    }

    /// py: _put_in_trash(owner, card, leaving=False)
    pub fn put_in_trash(&mut self, owner: Side, card: CardId, leaving: bool) -> R<()> {
        if self.trash_banishes(owner, if leaving { Some(card) } else { None }) {
            not_ported!("_put_in_trash", "trash_to_banish (Endless Riches)");
        }
        self.gs.player_mut(owner).trash.push(card);
        Ok(())
    }

    /// py: _standard_move(unit, side, src, dst)
    pub fn standard_move(&mut self, unit: UnitId, side: Side, src: usize, dst: usize) -> R<()> {
        let base_index = self.gs.battlefields.len();
        let src_bf = if src == base_index { None } else { Some(src) };
        let dst_bf = if dst == base_index { None } else { Some(dst) };
        self.exhaust(unit, Some(side), src_bf)?;
        let t = self.gs.turn;
        let count = match self.gs.move_group {
            Some((gt, gs_, gd, c)) if gt == t && gs_ == side && gd == dst => c + 1,
            _ => 1,
        };
        self.gs.move_group = Some((t, side, dst, count));
        if count == 3 {
            self.fire_units_trigger("on_three_exhausted", side, None, None, None)?;
        }
        let prev_controller = dst_bf.and_then(|d| self.gs.battlefields[d].controller());
        if let Some(d) = dst_bf {
            if self.gs.pending_move != Some((dst, side)) {
                self.gs.battlefields[d].prev_controller = Some(prev_controller);
            }
        }
        match dst_bf {
            None => self.gs.player_mut(side).base_units.push(unit),
            Some(d) => {
                self.gs.battlefields[d].add_unit(side, unit);
                self.gs.battlefields[d].contest(side, prev_controller);
            }
        }
        self.fire_move_triggers(unit, side, src_bf, dst_bf)?;
        let Some(d) = dst_bf else { return Ok(()) };
        let b = &mut self.gs.battlefields[d];
        let gained = prev_controller != Some(side) && b.controller() == Some(side);
        if gained || (!b.units[0].is_empty() && !b.units[1].is_empty()) {
            b.contested_this_turn = true;
            if self.gs.pending_move.is_none() {
                self.gs.pending_move = Some((dst, side));
            }
        }
        Ok(())
    }

    /// py: _fire_move_triggers(unit, side, src_bf, dst_bf)
    pub fn fire_move_triggers(&mut self, unit: UnitId, side: Side, src_bf: Option<usize>, dst_bf: Option<usize>) -> R<()> {
        self.gs.unit_mut(unit).moves_this_turn += 1;
        let here = dst_bf.unwrap_or(0);
        let mut extra = Extra::default();
        extra.set("battlefield", XVal::Bf(here));
        extra.set("moved_from", match src_bf { Some(b) => XVal::Bf(b), None => XVal::Str("base".into()) });
        extra.set("moved_to", match dst_bf { Some(b) => XVal::Bf(b), None => XVal::Str("base".into()) });
        extra.set("triggering_unit", XVal::Unit(unit));
        let dst_index = dst_bf;
        let pm = self.gs.pending_move;
        let held = match (pm, dst_index) {
            (Some((d, s)), Some(di)) => d == di && s == side,
            _ => false,
        };
        if !held {
            let c = self.gs.ucard(unit);
            self.fire_units_trigger("on_enemy_unit_moves", side.other(), None, Some(c), Some(extra.clone()))?;
        }
        let mut cards = vec![self.gs.ucard(unit)];
        cards.extend(self.gs.unit(unit).gear.iter().copied());
        for c in cards {
            self.resolve_triggered_effects(c, "on_move", here, side, Some(extra.clone()))?;
        }
        let left: Vec<UnitId> = match src_bf {
            Some(s) => self.gs.battlefields[s].units_for(side).clone(),
            None => self.gs.player(side).base_units.clone(),
        };
        for f in left {
            if f != unit && self.has_effect(self.gs.ucard(f), "follow_move") {
                not_ported!("_fire_move_triggers", "follow_move (Stealthy Pursuer)");
            }
        }
        if let Some(s) = src_bf {
            if let Some(bc) = self.gs.battlefields[s].card {
                self.resolve_triggered_effects(bc, "on_unit_moves_from_here", s, side, Some(extra.clone()))?;
            }
        }
        Ok(())
    }

    /// py: _move_unit_by_effect(unit, dst_bf)
    pub fn move_unit_by_effect(&mut self, unit: UnitId, dst_bf: Option<usize>, mover: Side) -> R<bool> {
        let Some((side, src_bf)) = self.locate_unit(unit) else { return Ok(false) };
        if src_bf == dst_bf {
            return Ok(false);
        }
        if self.gs.reg.regole.d78()
            && (self.gs.unit(unit).cant_move_any_turn == self.gs.turn
                || (self.gs.unit(unit).cant_move_turn == self.gs.turn && mover == side))
        {
            // D78 (profile 6427b90+D72-D80): "can't move this turn" (Vex Apathetic,
            // Hunker Down) negates an effect's move too (Vex: only its controller's); the rest of the spell resolves.
            crate::registry::conta(78);
            return Ok(false);
        }
        if dst_bf.is_none() && !self.can_move_to_base(unit, src_bf) {
            return Ok(false);
        }
        match src_bf {
            None => self.gs.player_mut(side).base_units.retain(|&u| u != unit),
            Some(s) => self.gs.battlefields[s].remove_unit(side, unit),
        }
        match dst_bf {
            None => self.gs.player_mut(side).base_units.push(unit),
            Some(d) => {
                let prev = self.gs.battlefields[d].controller();
                self.gs.battlefields[d].add_unit(side, unit);
                self.effect_arrival(d, side, prev);
            }
        }
        self.fire_move_triggers(unit, side, src_bf, dst_bf)?;
        Ok(true)
    }

    /// py: _effect_arrival
    pub fn effect_arrival(&mut self, bf: usize, side: Side, prev: Option<Side>) {
        let b = &mut self.gs.battlefields[bf];
        b.contest(side, prev);
        let gained = prev != Some(side) && b.controller() == Some(side);
        if !(gained || (!b.units[0].is_empty() && !b.units[1].is_empty())) {
            return;
        }
        b.contested_this_turn = true;
        b.prev_controller = Some(prev);
        self.stage_showdown(bf, side);
    }

    /// py: _run_staged_showdowns
    pub fn run_staged_showdowns(&mut self) -> R<()> {
        while !self.gs.staged_showdowns.is_empty() && !self.gs.showdown_active && self.gs.chain.is_empty()
            && self.gs.pending_move.is_none()
        {
            let (dst, side) = self.gs.staged_showdowns.remove(0);
            if self.gs.battlefields[dst].contested_by != Some(side) {
                continue;
            }
            if !self.gs.battlefields[dst].units_for(side).is_empty() {
                self.run_showdown(dst, Some(side))?;
            } else {
                self.gs.battlefields[dst].establish_control();
            }
        }
        Ok(())
    }

    /// py: _flush_pending_move
    pub fn flush_pending_move(&mut self) -> R<()> {
        let Some((dst, side)) = self.gs.pending_move else { return Ok(()) };
        self.gs.pending_move = None;
        let b = &mut self.gs.battlefields[dst];
        if b.units_for(side).is_empty() && b.contested_by == Some(side) {
            b.establish_control();
            return Ok(());
        }
        self.run_showdown(dst, Some(side))
    }
}
