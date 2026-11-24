//! py: loop.py _check_condition — the condition types the ported cards use
//! (inventory: scripts/rust/inventario.py). Any other type is NotPorted.

use serde_json::Value;

use crate::game::*;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

impl Game {
    /// py: _check_condition(cond, card, actor, opponent, extra)
    pub fn check_condition(&mut self, cond: Option<&Value>, card: CardId, actor: Side, extra: Option<&Extra>) -> R<bool> {
        let Some(cond) = cond.filter(|c| crate::cards::truthy(Some(c))) else { return Ok(true) };
        if crate::cards::truthy(cond.get("negate")) {
            let mut c2 = cond.as_object().cloned().unwrap_or_default();
            c2.remove("negate");
            let v = Value::Object(c2);
            return Ok(!self.check_condition(Some(&v), card, actor, extra)?);
        }
        let ctype = cond.get("type").and_then(|t| t.as_str()).unwrap_or("");
        let empty = serde_json::Map::new();
        let params = cond.get("params").and_then(|p| p.as_object()).unwrap_or(&empty);
        let side = actor;
        let ex_default = Extra::default();
        let extra = extra.unwrap_or(&ex_default);
        Ok(match ctype {
            "kicker_paid" => self.gs.card(card).kicker_paid.unwrap_or(false),
            "showed_off" => self.gs.card(card).showed_off.unwrap_or(false),
            "not" => {
                let c = params.get("condition").cloned();
                !self.check_condition(c.as_ref(), card, actor, Some(extra))?
            }
            "not_your_turn" => side != self.gs.active,
            "triggering_card_from_zone" => {
                let trig = matches!(extra.get("triggering_card"), Some(x) if *x != XVal::None);
                let from_zone = match extra.get("from_zone") {
                    Some(XVal::Str(s)) => s.clone(),
                    Some(XVal::None) => "None".into(),
                    None => "hand".into(),
                    Some(_) => "?".into(),
                };
                let want = params.get("zone").map(crate::lp_phases::py_str).unwrap_or_else(|| "None".into());
                trig && from_zone == want
            }
            "all_of" => {
                let conds: Vec<Value> = params.get("conditions").and_then(|c| c.as_array()).cloned().unwrap_or_default();
                let mut ok = true;
                for c in conds {
                    if !self.check_condition(Some(&c), card, actor, Some(extra))? {
                        ok = false;
                        break;
                    }
                }
                ok
            }
            "moved_to_battlefield" | "moved_from_battlefield" => {
                let k = if ctype == "moved_to_battlefield" { "moved_to" } else { "moved_from" };
                match extra.get(k) {
                    None | Some(XVal::None) => false,
                    Some(XVal::Str(s)) => s != "base",
                    Some(_) => true,
                }
            }
            "played_to_battlefield_this_turn" => {
                let t = self.gs.turn;
                self.gs.battlefields.iter().any(|bf| bf.plays_here.get(&side).map_or(-1, |p| p.0) == t)
            }
            "enemy_alone_here" | "one_on_one_here" => {
                let Some(bf) = extra.bf("battlefield") else { return Ok(false) };
                let enemies = self.gs.battlefields[bf].units_for(side.other()).len();
                if ctype == "enemy_alone_here" {
                    enemies == 1
                } else {
                    enemies == 1 && self.gs.battlefields[bf].units_for(side).len() == 1
                }
            }
            "this_is_at_battlefield" => self
                .gs
                .battlefields
                .iter()
                .any(|bf| bf.units_for(side).iter().any(|&u| self.gs.ucard(u) == card)),
            "friendly_mighty_unit_here" => {
                // "When you conquer here with one or more MIGHTY units" (Sunken Temple).
                match extra.bf("battlefield") {
                    Some(bf) => self.gs.battlefields[bf].units_for(side).iter().any(|&u| self.gs.unit_might(u) >= 5),
                    None => false,
                }
            }
            "you_already_played_another_card_this_turn" => {
                // Another card than this one: a LEGION card's own play is already
                // counted while its "when you play me" resolves.
                self.gs.played_cards_this_turn[side.idx()].iter().any(|&c| c != card)
            }
            "friendly_total_might_at_least" => {
                // Combined might of the actor's OTHER units (Kinkou Initiate).
                let total: i64 = self
                    .friendly_units(side)
                    .into_iter()
                    .filter(|&u| self.gs.ucard(u) != card)
                    .map(|u| self.gs.unit_might(u))
                    .sum();
                total >= threshold(params, 0)
            }
            "this_is_mighty" => {
                // Mighty = 5+ Might now (§ MIGHTY), not the printed number.
                match self.find_unit_by_card(card) {
                    Some(u) => self.gs.unit_might(u) >= 5,
                    None => self.gs.might(card).unwrap_or(0) >= 5,
                }
            }
            "you_have_n_or_more_units_here" => {
                let Some(bf) = extra.bf("battlefield") else { return Ok(false) };
                if self.gs.players[side.idx()].base_units.iter().any(|&u| self.gs.ucard(u) == card) {
                    return Ok(false); // a unit in base isn't at a battlefield
                }
                let units = self.gs.battlefields[bf].units_for(side).to_vec();
                let mut n = units.len() as i64;
                if crate::cards::truthy(params.get("with_gear")) {
                    // "2 or more other friendly units and/or gear at my battlefield" (Steadfast Outrider)
                    n += self.gs.battlefields[bf].gear[side.idx()].len() as i64;
                    n += units.iter().map(|&u| self.gs.units[u.i()].gear.len() as i64).sum::<i64>();
                }
                n >= threshold(params, 0)
            }
            "undamaged_this_turn" => {
                // "if I haven't been dealt damage this turn" (Affectionate Poro)
                match self.find_unit_by_card(card) {
                    Some(u) => self.gs.units[u.i()].damaged_turn != self.gs.turn,
                    None => false,
                }
            }
            "played_from_hand" => {
                // "If you played this from your hand" (Back Off)
                self.gs.card(card).played_from.as_deref().unwrap_or("hand") == "hand"
            }
            "has_all_pet_tags" => {
                // "if your units have all of the following tags among them - Bird,
                // Cat, Dog, and Poro" (Ivern Friend to All): _friendly_units_of (no legend units).
                let tags: std::collections::HashSet<String> =
                    self.friendly_units_of(side).into_iter().flat_map(|u| self.gs.unit_tags(u)).collect();
                ["Bird", "Cat", "Dog", "Poro"].iter().all(|t| tags.contains(*t))
            }
            other => not_ported!("_check_condition", "condition type {other}"),
        })
    }

    /// py: _check_condition._friendly_units — battlefield units, base units, legend units.
    pub fn friendly_units(&self, side: Side) -> Vec<UnitId> {
        let mut us: Vec<UnitId> = Vec::new();
        for bf in &self.gs.battlefields {
            us.extend(bf.units_for(side).iter().copied());
        }
        us.extend(self.gs.players[side.idx()].base_units.iter().copied());
        us.extend(self.legend_units(side));
        us
    }

    /// py: _find_unit_by_card
    pub fn find_unit_by_card(&self, card: CardId) -> Option<UnitId> {
        for bf in &self.gs.battlefields {
            for &u in bf.units[0].iter().chain(bf.units[1].iter()) {
                if self.gs.ucard(u) == card {
                    return Some(u);
                }
            }
        }
        for p in &self.gs.players {
            for &u in &p.base_units {
                if self.gs.ucard(u) == card {
                    return Some(u);
                }
            }
        }
        for lu in self.legend_units(Side::A).into_iter().chain(self.legend_units(Side::B)) {
            if self.gs.ucard(lu) == card {
                return Some(lu);
            }
        }
        None
    }
}

/// py: _check_condition._threshold — the first numeric of n/amount/count/value/threshold.
fn threshold(params: &serde_json::Map<String, Value>, default: i64) -> i64 {
    for key in ["n", "amount", "count", "value", "threshold"] {
        if let Some(v) = params.get(key) {
            if let Some(i) = v.as_i64() {
                return i;
            }
            if let Some(f) = v.as_f64() {
                return f.trunc() as i64;
            }
        }
    }
    default
}
