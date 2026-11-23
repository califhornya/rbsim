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
            other => not_ported!("_check_condition", "condition type {other}"),
        })
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
