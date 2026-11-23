//! py: loop.py — recycling, banishing notes, attaching Equipment, move
//! taxes, who can be chosen / moved / readied, combat keywords, Gold bonus.

use serde_json::{Map, Value};

use crate::cards::py_int;
use crate::game::*;
use crate::model::*;
use crate::types::*;

impl Game {
    /// py: _locate_unit_or_gear
    pub fn locate_unit_or_gear(&self, card: CardId, side: Side) -> bool {
        self.find_unit_by_card(card).is_some()
            || self.gs.player(side).base_gear.contains(&card)
            || self.controlled_attached_gear(side).contains(&card)
    }

    /// py: _recyclable(player, kind=None)
    pub fn recyclable(&self, player: Side, kind: &Option<String>) -> Vec<CardId> {
        self.gs
            .player(player)
            .trash
            .iter()
            .copied()
            .filter(|&c| match kind {
                None => true,
                Some(k) => {
                    let mut spec = Map::new();
                    spec.insert("filter".into(), Value::String(k.clone()));
                    self.zone_effect_card_ok(c, &spec)
                }
            })
            .collect()
    }

    /// py: _recycle_from_trash(player, n, kind=None)
    pub fn recycle_from_trash(&mut self, player: Side, n: i64, kind: &Option<String>) -> R<()> {
        let cands: Vec<CardId> = self.recyclable(player, kind).into_iter().take(n.max(0) as usize).collect();
        let mut moved = 0;
        for c in cands {
            let p = self.gs.player_mut(player);
            if let Some(i) = p.trash.iter().position(|&x| x == c) {
                p.trash.remove(i);
            }
            p.deck.cards.insert(0, c);
            moved += 1;
        }
        if moved > 0 {
            self.note_recycled(player)?;
        }
        Ok(())
    }

    /// py: _note_recycled
    pub fn note_recycled(&mut self, side: Side) -> R<()> {
        self.fire_units_trigger("on_recycle", side, None, None, None)
    }

    /// py: _note_banished(side, count=1)
    pub fn note_banished(&mut self, side: Side) -> R<()> {
        self.fire_units_trigger("on_banish_own", side, None, None, None)
    }

    /// py: _fire_attached
    pub fn fire_attached(&mut self, unit: UnitId, side: Side) -> R<()> {
        let bf = self.locate_unit(unit).and_then(|(_, b)| b).unwrap_or(0);
        let t = self.gs.turn;
        for g in self.gs.unit(unit).gear.clone() {
            if self.gs.card(g).attached_to != Some(unit) {
                self.gs.card_mut(g).attached_to = Some(unit);
                self.gs.card_mut(g).attached_turn = Some(t);
            }
        }
        let uc = self.gs.ucard(unit);
        self.resolve_triggered_effects(uc, "on_equipment_attached", bf, side, Some(crate::lp_phases::bf_extra(bf)))?;
        for g in self.gs.unit(unit).gear.clone() {
            let mut ex = crate::lp_phases::bf_extra(bf);
            ex.set("triggering_unit", XVal::Unit(unit));
            self.resolve_triggered_effects(g, "on_attached", bf, side, Some(ex))?;
        }
        Ok(())
    }

    /// py: _move_tax(payer, dst_bf) -> (energy, power)
    pub fn move_tax(&self, payer: Side, dst_bf: Option<usize>) -> (i64, i64) {
        let Some(d) = dst_bf else { return (0, 0) };
        let (mut e, mut p) = (0, 0);
        for &dg in &self.gs.battlefields[d].gear[payer.other().idx()] {
            for es in self.gs.spec(self.gs.dgear[dg.i()].card).effects.iter() {
                if es.effect == "move_tax_here" {
                    e += es.params.get("energy").map(py_int).unwrap_or(1);
                    p += es.params.get("power").map(py_int).unwrap_or(1);
                }
            }
        }
        (e, p)
    }

    /// py: _can_pay_move_tax
    pub fn can_pay_move_tax(&self, payer: Side, dst_bf: usize) -> bool {
        let (e, p) = self.move_tax(payer, Some(dst_bf));
        self.gs.player(payer).energy() >= e && self.can_pay_generic_power(payer, p)
    }

    /// py: _pay_move_tax
    pub fn pay_move_tax(&mut self, payer: Side, dst_bf: usize) -> R<bool> {
        if !self.can_pay_move_tax(payer, dst_bf) {
            return Ok(false);
        }
        let (e, p) = self.move_tax(payer, Some(dst_bf));
        let en = self.gs.player(payer).energy() - e;
        self.gs.player_mut(payer).set_energy(en);
        self.pay_generic_power(payer, p)
    }

    /// py: _group_move_toll
    pub fn group_move_toll(&self, side: Side, dst: usize) -> i64 {
        if dst >= self.gs.battlefields.len() {
            return 0;
        }
        match self.gs.move_group {
            Some((t, s, d, _)) if t == self.gs.turn && s == side && d == dst => {}
            _ => return 0,
        }
        self.gs.battlefields[dst]
            .units_for(side.other())
            .iter()
            .filter(|&&u| self.has_effect(self.gs.ucard(u), "group_move_toll"))
            .count() as i64
    }

    /// py: _can_choose(unit, chooser, source=None)
    pub fn can_choose(&self, unit: UnitId, chooser: Side, source: Option<CardId>) -> R<bool> {
        let Some((ws, _)) = self.locate_unit(unit) else { return Ok(true) };
        if ws == chooser {
            return Ok(true);
        }
        let u = self.gs.unit(unit);
        if u.unchoosable || u.cant_be_chosen_turn == self.gs.turn {
            return Ok(false);
        }
        if self.choices_noted {
            return Ok(true);
        }
        let tax = self.deflect_tax(unit, chooser, source)?;
        Ok(tax == 0 || self.can_pay_generic_power(chooser, tax))
    }

    /// py: _can_move_to_base
    pub fn can_move_to_base(&self, unit: UnitId, src_bf: Option<usize>) -> bool {
        if self.gs.unit(unit).no_move_to_base {
            return false;
        }
        if let Some(s) = src_bf {
            if let Some(c) = self.gs.battlefields[s].card {
                if self.gs.spec(c).effects.iter().any(|es| es.effect == "no_moves_to_base_from_here") {
                    return false;
                }
            }
        }
        true
    }

    /// py: _can_ready
    pub fn can_ready(&self, unit: UnitId) -> bool {
        if self.gs.unit(unit).cant_ready {
            return false;
        }
        match self.locate_unit(unit) {
            None => true,
            Some((s, _)) => !self.readying_blocked(s),
        }
    }

    /// py: _readying_blocked
    pub fn readying_blocked(&self, side: Side) -> bool {
        let other = side.other();
        self.gs
            .battlefields
            .iter()
            .any(|bf| bf.units_for(other).iter().any(|&u| self.has_effect(self.gs.ucard(u), "warden_no_ready")))
    }

    /// py: _gangplank_redirect — EK: nobody has it.
    pub fn gangplank_redirect(&self, unit: UnitId) -> bool {
        let _ = unit;
        false
    }

    /// py: _in_combat
    pub fn in_combat(&self, unit: UnitId) -> bool {
        match self.locate_unit(unit) {
            Some((_, Some(b))) => self.gs.battlefields[b].combat_started && self.gs.battlefields[b].combat_designated.contains(&unit),
            _ => false,
        }
    }

    /// py: _refresh_combat_keywords
    pub fn refresh_combat_keywords(&mut self) {
        for i in 0..self.gs.battlefields.len() {
            let started = self.gs.battlefields[i].combat_started;
            let attacker = self.gs.battlefields[i].combat_attacker;
            let mods: Vec<(UnitId, i64)> = if started { self.combat_might_mods(i, attacker) } else { Vec::new() };
            for side in Side::BOTH {
                for u in self.gs.battlefields[i].units_for(side).clone() {
                    let bm = if started && self.gs.battlefields[i].combat_designated.contains(&u) {
                        let kw = if Some(side) == attacker { "ASSAULT" } else { "SHIELD" };
                        self.gs.unit_keyword_value(u, kw) + mods.iter().find(|(x, _)| *x == u).map(|m| m.1).unwrap_or(0)
                    } else {
                        0
                    };
                    self.gs.unit_mut(u).bonus_might = bm;
                }
            }
        }
        for side in Side::BOTH {
            for u in self.gs.player(side).base_units.clone() {
                self.gs.unit_mut(u).bonus_might = 0;
            }
        }
    }

    /// py: _gold_bonus
    pub fn gold_bonus(&self, side: Side) -> bool {
        self.legend_with(side, "gold_bonus", false).is_some() && self.gs.points[side.idx()] >= self.gs.victory_score - 3
    }
}
