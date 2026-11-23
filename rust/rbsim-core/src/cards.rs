//! Card and unit queries (py: cards.Card methods, combat.UnitInPlay
//! properties): static data from the registry, play state from the arenas.

use serde_json::{Map, Value};

use crate::model::*;
use crate::registry::{CardSpec, Inst};
use crate::types::*;

pub const ASSAULT_EQUALS_SHIELD: &str = "ASSAULT = SHIELD";

/// py: Card.has_keyword on a keyword list.
pub fn kw_has(list: &[String], keyword: &str) -> bool {
    let kw = keyword.to_uppercase();
    list.iter().any(|k| {
        let ku = k.to_uppercase();
        ku == kw || ku.starts_with(&(kw.clone() + " "))
    })
}

/// py: UnitInPlay._kw_amount
pub fn kw_amount(k: &str, kw: &str) -> i64 {
    let ku = k.to_uppercase();
    if ku == kw {
        return 1;
    }
    if ku.starts_with(&(kw.to_string() + " ")) {
        return ku[kw.len()..].trim().parse::<i64>().unwrap_or(1);
    }
    0
}

/// py: Card.keyword_value on a keyword list.
pub fn kw_value(list: &[String], keyword: &str) -> i64 {
    let kw = keyword.to_uppercase();
    for k in list {
        let ku = k.to_uppercase();
        if ku == kw {
            return 1;
        }
        if ku.starts_with(&(kw.clone() + " ")) {
            return ku[kw.len()..].trim().parse::<i64>().unwrap_or(1);
        }
    }
    0
}

impl GameState {
    pub fn spec(&self, c: CardId) -> &CardSpec {
        &self.reg.cards[self.cards[c.i()].spec as usize]
    }
    pub fn inst(&self, c: CardId) -> &Inst {
        self.spec(c).inst.as_ref().expect("card without instance data")
    }
    pub fn name(&self, c: CardId) -> &str {
        &self.spec(c).name
    }
    pub fn class(&self, c: CardId) -> CardClass {
        self.inst(c).class
    }
    pub fn category(&self, c: CardId) -> CardType {
        self.inst(c).category
    }
    pub fn is_unit_card(&self, c: CardId) -> bool {
        self.class(c) == CardClass::Unit
    }
    pub fn is_spell(&self, c: CardId) -> bool {
        self.class(c) == CardClass::Spell
    }
    pub fn is_gear_card(&self, c: CardId) -> bool {
        self.class(c) == CardClass::Gear
    }
    pub fn is_legend_card(&self, c: CardId) -> bool {
        self.class(c) == CardClass::Legend
    }
    /// py: cards.is_gear
    pub fn is_gear(&self, c: CardId) -> bool {
        self.class(c) == CardClass::Gear || self.inst(c).also_gear
    }
    pub fn keywords(&self, c: CardId) -> &Vec<String> {
        &self.inst(c).keywords
    }
    pub fn tags(&self, c: CardId) -> &Vec<String> {
        &self.inst(c).tags
    }
    /// py: card.effects (dicts)
    pub fn effects(&self, c: CardId) -> &Vec<Map<String, Value>> {
        &self.inst(c).effects
    }
    pub fn has_keyword(&self, c: CardId, kw: &str) -> bool {
        kw_has(&self.inst(c).keywords, kw)
    }
    pub fn keyword_value(&self, c: CardId, kw: &str) -> i64 {
        kw_value(&self.inst(c).keywords, kw)
    }
    /// py: card.might (None for a card without Might)
    pub fn might(&self, c: CardId) -> Option<i64> {
        self.cards[c.i()].might_override.or(self.inst(c).might)
    }
    pub fn cost_energy(&self, c: CardId) -> i64 {
        self.inst(c).cost_energy
    }
    pub fn cost_power(&self, c: CardId) -> Option<i64> {
        self.inst(c).cost_power
    }
    pub fn cost_power_domain(&self, c: CardId) -> Option<Domain> {
        self.inst(c).cost_power_domain
    }
    pub fn domain(&self, c: CardId) -> Option<Domain> {
        self.inst(c).domain
    }
    pub fn card_is_token(&self, c: CardId) -> bool {
        self.cards[c.i()].is_token.unwrap_or(false)
    }

    // ------------------------------------------------------------- units ---

    pub fn ucard(&self, u: UnitId) -> CardId {
        self.units[u.i()].card
    }
    /// py: UnitInPlay._printed_might
    pub fn unit_printed_might(&self, u: UnitId) -> i64 {
        let unit = &self.units[u.i()];
        if unit.gear_unit && self.class(unit.card) != CardClass::Unit {
            return self.cost_energy(unit.card);
        }
        self.might(unit.card).unwrap_or(0)
    }
    /// py: UnitInPlay.base_might
    pub fn unit_base_might(&self, u: UnitId) -> i64 {
        if let Some(o) = self.units[u.i()].base_might_override {
            return o;
        }
        self.unit_printed_might(u)
    }
    fn gear_bonus(&self, u: UnitId) -> i64 {
        let unit = &self.units[u.i()];
        let mut b = 0;
        for &g in &unit.gear {
            for e in self.effects(g) {
                if e.get("effect").and_then(|v| v.as_str()) == Some("grant_might") && !truthy(e.get("condition")) {
                    b += e.get("amount").map(py_int).unwrap_or(0);
                }
            }
        }
        b += unit.equip_bonus_mult * unit.gear.iter().map(|&g| self.might(g).unwrap_or(0)).sum::<i64>();
        b
    }
    /// py: UnitInPlay._might
    pub fn unit_might_x(&self, u: UnitId, this_turn: bool) -> i64 {
        let unit = &self.units[u.i()];
        let gb = self.gear_bonus(u);
        let (base, turn) = if this_turn {
            (self.unit_base_might(u), unit.bonus_might + unit.temporary_might + unit.combat_might)
        } else {
            (self.unit_printed_might(u), 0)
        };
        (base + turn + unit.might_counters + unit.aura_might + unit.passive_might + gb).max(0)
    }
    /// py: UnitInPlay.might
    pub fn unit_might(&self, u: UnitId) -> i64 {
        self.unit_might_x(u, true)
    }
    /// py: UnitInPlay.lasting_might
    pub fn unit_lasting_might(&self, u: UnitId) -> i64 {
        self.unit_might_x(u, false)
    }
    /// py: UnitInPlay.is_gear
    pub fn unit_is_gear(&self, u: UnitId) -> bool {
        let unit = &self.units[u.i()];
        unit.gear_unit || self.inst(unit.card).also_gear
    }
    /// py: UnitInPlay.tags
    pub fn unit_tags(&self, u: UnitId) -> Vec<String> {
        let unit = &self.units[u.i()];
        let mut t: Vec<String> = self.tags(unit.card).clone();
        t.extend(unit.extra_tags.iter().cloned());
        for &g in &unit.gear {
            t.extend(self.inst(g).grants_tags.iter().cloned());
        }
        t
    }
    /// py: UnitInPlay.has_keyword
    pub fn unit_has_keyword(&self, u: UnitId, keyword: &str) -> bool {
        let unit = &self.units[u.i()];
        if self.has_keyword(unit.card, keyword) {
            return true;
        }
        let kw = keyword.to_uppercase();
        unit.passive_keywords
            .iter()
            .chain(unit.turn_keywords.iter())
            .chain(unit.granted_keywords.iter())
            .chain(unit.combat_keywords.iter())
            .any(|k| {
                let ku = k.to_uppercase();
                ku == kw || ku.starts_with(&(kw.clone() + " "))
            })
    }
    /// py: UnitInPlay.keyword_value
    pub fn unit_keyword_value(&self, u: UnitId, keyword: &str) -> i64 {
        let unit = &self.units[u.i()];
        let copies = unit
            .gear
            .iter()
            .map(|&g| {
                self.effects(g)
                    .iter()
                    .filter(|e| e.get("effect").and_then(|v| v.as_str()) == Some("copy_unit_text"))
                    .count() as i64
            })
            .sum::<i64>();
        let base = self.keyword_value(unit.card, keyword) * (1 + copies);
        let kw = keyword.to_uppercase();
        let passive: i64 = unit.passive_keywords.iter().map(|k| kw_amount(k, &kw)).sum();
        let mut given: i64 = unit
            .turn_keywords
            .iter()
            .chain(unit.granted_keywords.iter())
            .chain(unit.combat_keywords.iter())
            .filter(|k| k.as_str() != ASSAULT_EQUALS_SHIELD)
            .map(|k| kw_amount(k, &kw))
            .sum();
        if kw == "ASSAULT" && unit.turn_keywords.iter().any(|k| k == ASSAULT_EQUALS_SHIELD) {
            given += self.unit_keyword_value(u, "SHIELD");
        }
        base + passive + given
    }
    /// py: player.ready_base_units
    pub fn ready_base_units(&mut self, s: Side) {
        let ids = self.players[s.idx()].base_units.clone();
        for u in ids {
            self.units[u.i()].ready = true;
        }
    }
    /// py: Battlefield.ready_side
    pub fn ready_side(&mut self, bf: usize, s: Side) {
        let ids = self.battlefields[bf].units[s.idx()].clone();
        for u in ids {
            self.units[u.i()].ready = true;
        }
    }
}

/// Python truthiness of a JSON value (None / missing is false).
pub fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().map_or(false, |x| x != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// py: int(x) for a JSON number or numeric string (0 otherwise).
pub fn py_int(v: &Value) -> i64 {
    match v {
        Value::Number(n) => n.as_i64().unwrap_or_else(|| n.as_f64().map(|f| f as i64).unwrap_or(0)),
        Value::String(s) => s.trim().parse::<i64>().unwrap_or(0),
        Value::Bool(b) => *b as i64,
        _ => 0,
    }
}
