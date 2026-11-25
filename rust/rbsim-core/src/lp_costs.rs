//! py: loop.py — cost helpers (reductions, EQUIP costs, showdown / gear /
//! generic power payments), reveal-from-top offers, AMBUSH champion,
//! first-play-here triggers.

use regex::Regex;
use std::sync::OnceLock;

use crate::cards::{py_int, truthy};
use crate::game::*;
use crate::lp_phases::py_str;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

pub const PASSIVE_FRIENDLY_TARGETS: [&str; 8] =
    ["self", "this", "actor", "ally", "allies", "friendly", "friendly_unit", "all_friendly_units_here"];

/// py: the dict _equip_cost returns.
#[derive(Clone, Debug, PartialEq)]
pub struct EquipCost {
    pub energy: i64,
    /// domain name (lowercase) -> n, in text order
    pub domain_power: Vec<(String, i64)>,
    pub generic: i64,
    pub recycle: i64,
    pub kill_friendly: bool,
    pub spend_xp: i64,
    pub or_exhaust: bool,
}

fn re(p: &'static str, cell: &'static OnceLock<Regex>) -> &'static Regex {
    cell.get_or_init(|| Regex::new(p).unwrap())
}

/// py: _equip_cost's parse of the rules text.
pub fn parse_equip_cost(text: &str) -> Option<EquipCost> {
    static EQ: OnceLock<Regex> = OnceLock::new();
    static TOK: OnceLock<Regex> = OnceLock::new();
    static REC: OnceLock<Regex> = OnceLock::new();
    static KILL: OnceLock<Regex> = OnceLock::new();
    static XP: OnceLock<Regex> = OnceLock::new();
    static ORX: OnceLock<Regex> = OnceLock::new();
    let m = re(r"(?is)\bequip\b(.*?)\(", &EQ).captures(text)?;
    let clause = m.get(1).unwrap().as_str();
    let mut c = EquipCost { energy: 0, domain_power: Vec::new(), generic: 0, recycle: 0, kill_friendly: false, spend_xp: 0, or_exhaust: false };
    for t in re(r"\[([^\]]+)\]", &TOK).captures_iter(clause) {
        let t = t.get(1).unwrap().as_str().trim().to_lowercase();
        if !t.is_empty() && t.chars().all(|ch| ch.is_ascii_digit()) {
            c.energy += t.parse::<i64>().unwrap_or(0);
        } else if ["fury", "calm", "mind", "body", "chaos", "order"].contains(&t.as_str()) {
            if let Some(e) = c.domain_power.iter_mut().find(|(d, _)| *d == t) {
                e.1 += 1;
            } else {
                c.domain_power.push((t, 1));
            }
        } else if t == "rune" {
            c.generic += 1;
        }
    }
    if let Some(r) = re(r"(?i)recycle\s+(\d+)", &REC).captures(clause) {
        c.recycle = r.get(1).unwrap().as_str().parse().unwrap_or(0);
    }
    c.kill_friendly = re(r"(?i)kill a friendly", &KILL).is_match(clause);
    if let Some(r) = re(r"(?i)spend\s+(\d+)\s*xp", &XP).captures(clause) {
        c.spend_xp = r.get(1).unwrap().as_str().parse().unwrap_or(0);
    }
    c.or_exhaust = re(r"(?i)\bor exhaust a friendly unit", &ORX).is_match(clause);
    Some(c)
}

impl Game {
    /// py: _cost_reduction(card, actor, power=False)
    pub fn cost_reduction(&mut self, card: CardId, actor: Side, power: bool) -> R<i64> {
        let specs = self.gs.spec(card).effects.clone();
        if specs.is_empty() {
            return Ok(0);
        }
        let mut total: i64 = 0;
        for es in specs {
            if es.trigger != "cost_modifier" || es.effect != "reduce_cost" {
                continue;
            }
            if !self.check_condition(es.condition.as_ref(), card, actor, None)? {
                continue;
            }
            if power {
                let mut per = es.params.get("power").map(py_int).unwrap_or(0);
                if per != 0 && truthy(es.params.get("amount_source")) {
                    let ctx = Ctx::new(card, actor, 0);
                    let mut p = serde_json::Map::new();
                    p.insert("amount_source".into(), es.params["amount_source"].clone());
                    per *= self.effect_amount(&ctx, &p)?;
                }
                total += per;
            } else if truthy(es.params.get("amount_source")) {
                let ctx = Ctx::new(card, actor, 0);
                let per = es.params.get("amount").map(py_int).filter(|&x| x != 0).unwrap_or(1);
                total += per * self.effect_amount(&ctx, &es.params)?;
            } else {
                total += es.params.get("amount").map(py_int).unwrap_or(0);
            }
            if !power && es.params.get("min_cost").map_or(false, |v| !v.is_null()) {
                let mc = py_int(&es.params["min_cost"]);
                total = total.min((self.gs.cost_energy(card) - mc).max(0));
            }
        }
        Ok(total.max(0))
    }

    /// py: _equip_cost(gear) (None: not an Equipment)
    pub fn equip_cost(&self, gear: CardId) -> Option<EquipCost> {
        let spec = self.gs.spec(gear);
        let text = spec.raw.get("effect").and_then(|v| v.as_str()).unwrap_or("");
        if text.is_empty() {
            return None;
        }
        parse_equip_cost(text)
    }

    /// py: _equip_cost_for
    pub fn equip_cost_for(&self, gear: CardId, unit: UnitId, cost: &EquipCost) -> EquipCost {
        if !self.has_effect(gear, "equip_less_by_might") {
            return cost.clone();
        }
        let mut c = cost.clone();
        c.energy = (c.energy - self.gs.unit_might(unit).max(0)).max(0);
        c
    }

    /// py: _equip_targets
    pub fn equip_targets(&mut self, ap: Side, gear: CardId, cost: &EquipCost) -> R<Vec<UnitId>> {
        let units = self.friendly_units_of(ap);
        if !self.has_effect(gear, "equip_less_by_might") {
            return Ok(if self.can_pay_equip(ap, cost)? { units } else { Vec::new() });
        }
        let mut out = Vec::new();
        for u in units {
            let c = self.equip_cost_for(gear, u, cost);
            if self.can_pay_equip(ap, &c)? {
                out.push(u);
            }
        }
        Ok(out)
    }

    /// py: _can_pay_equip
    pub fn can_pay_equip(&mut self, ap: Side, cost: &EquipCost) -> R<bool> {
        if cost.or_exhaust && !self.can_pay_equip_resources(ap, cost) {
            not_ported!("_can_pay_equip", "EQUIP or exhaust a friendly unit");
        }
        Ok(self.can_pay_equip_resources(ap, cost))
    }

    /// py: _can_pay_equip_resources
    pub fn can_pay_equip_resources(&self, ap: Side, cost: &EquipCost) -> bool {
        let p = self.gs.player(ap);
        let mut earmark = p.earmarked_power_gear;
        if p.energy() < cost.energy {
            return false;
        }
        let gnr = (cost.generic - earmark).max(0);
        earmark = (earmark - cost.generic).max(0);
        if !self.can_pay_generic_power(ap, gnr) {
            return false;
        }
        for (d, n) in &cost.domain_power {
            let need = (n - earmark).max(0);
            earmark = (earmark - n).max(0);
            if need != 0 && !p.can_pay_cost(0, Some(need), Domain::from_py(d)) {
                return false;
            }
        }
        if cost.recycle != 0 && (p.trash.len() as i64) < cost.recycle {
            return false;
        }
        if cost.kill_friendly && self.first_friendly_unit_on_board(ap).is_none() {
            return false;
        }
        if cost.spend_xp != 0 && self.gs.get_xp(ap) < cost.spend_xp {
            return false;
        }
        true
    }

    /// py: _pay_equip
    pub fn pay_equip(&mut self, ap: Side, cost: &EquipCost) -> R<bool> {
        if !self.can_pay_equip(ap, cost)? {
            return Ok(false);
        }
        if cost.or_exhaust {
            not_ported!("_pay_equip", "EQUIP or exhaust");
        }
        let e = self.gs.player(ap).energy() - cost.energy;
        self.gs.player_mut(ap).set_energy(e);
        let gnr = cost.generic;
        let use_ = gnr.min(self.gs.player(ap).earmarked_power_gear);
        self.gs.player_mut(ap).earmarked_power_gear -= use_;
        self.pay_generic_power(ap, gnr - use_)?;
        for (d, n) in &cost.domain_power {
            let use_ = (*n).min(self.gs.player(ap).earmarked_power_gear);
            self.gs.player_mut(ap).earmarked_power_gear -= use_;
            if n - use_ != 0 {
                self.gs.player_mut(ap).pay_cost(0, Some(n - use_), Domain::from_py(d));
            }
        }
        self.recycle_from_trash(ap, cost.recycle, &None)?;
        if cost.kill_friendly {
            not_ported!("_pay_equip", "EQUIP kill a friendly unit");
        }
        if cost.spend_xp != 0 {
            self.gs.add_xp(ap, -cost.spend_xp);
        }
        Ok(true)
    }

    /// py: _can_pay_showdown
    pub fn can_pay_showdown(&self, p: Side, energy: i64, power: Option<i64>, domain: Option<Domain>) -> bool {
        let pl = self.gs.player(p);
        if pl.energy() + pl.earmarked_energy_showdown < energy {
            return false;
        }
        if power.unwrap_or(0) != 0 && domain.is_some() {
            return pl.can_pay_cost(0, power, domain);
        }
        true
    }

    /// py: _pay_showdown
    pub fn pay_showdown(&mut self, p: Side, energy: i64, power: Option<i64>, domain: Option<Domain>) -> bool {
        if !self.can_pay_showdown(p, energy, power, domain) {
            return false;
        }
        let pl = self.gs.player_mut(p);
        let from_earmark = energy.min(pl.earmarked_energy_showdown);
        pl.earmarked_energy_showdown -= from_earmark;
        pl.pay_cost(energy - from_earmark, power, domain)
    }

    /// py: _can_pay_gear
    pub fn can_pay_gear(&self, ap: Side, energy: i64, power: Option<i64>, domain: Option<Domain>) -> bool {
        let p = self.gs.player(ap);
        if p.energy() < energy {
            return false;
        }
        let pw = power.unwrap_or(0);
        if pw == 0 {
            return true;
        }
        let remaining = (pw - p.earmarked_power_gear).max(0);
        if remaining == 0 {
            return true;
        }
        match domain {
            None => self.can_pay_generic_power(ap, remaining),
            Some(d) => p.can_pay_cost(0, Some(remaining), Some(d)),
        }
    }

    /// py: _pay_gear
    pub fn pay_gear(&mut self, ap: Side, energy: i64, power: Option<i64>, domain: Option<Domain>) -> R<bool> {
        if !self.can_pay_gear(ap, energy, power, domain) {
            return Ok(false);
        }
        let e = self.gs.player(ap).energy() - energy;
        self.gs.player_mut(ap).set_energy(e);
        let pw = power.unwrap_or(0);
        if pw != 0 {
            let from_earmark = pw.min(self.gs.player(ap).earmarked_power_gear);
            self.gs.player_mut(ap).earmarked_power_gear -= from_earmark;
            let remaining = pw - from_earmark;
            if remaining != 0 {
                match domain {
                    None => {
                        self.pay_generic_power(ap, remaining)?;
                    }
                    Some(d) => {
                        self.gs.player_mut(ap).pay_cost(0, Some(remaining), Some(d));
                    }
                }
            }
        }
        Ok(true)
    }

    /// py: _spell_chooses_friendly
    pub fn spell_chooses_friendly(&self, card: CardId) -> bool {
        self.gs
            .spec(card)
            .effects
            .iter()
            .any(|es| PASSIVE_FRIENDLY_TARGETS.contains(&es.target.clone().unwrap_or_default().to_lowercase().as_str()))
    }

    /// py: _bf_cost_reduction(card, target_lane) -> (energy, power)
    pub fn bf_cost_reduction(&self, card: CardId, lane: i64) -> (i64, i64) {
        if lane < 0 || lane as usize >= self.gs.battlefields.len() {
            return (0, 0);
        }
        let Some(bc) = self.gs.battlefields[lane as usize].card else { return (0, 0) };
        let (mut e, mut p) = (0, 0);
        for es in self.gs.spec(bc).effects.iter() {
            if es.trigger != "passive" || es.effect != "reduce_cost_here" {
                continue;
            }
            if es.params.get("requires_target").and_then(|v| v.as_str()) == Some("friendly")
                && !self.spell_chooses_friendly(card)
            {
                continue;
            }
            let amt = es.params.get("amount").map(py_int).unwrap_or(1);
            if es.params.get("resource").and_then(|v| v.as_str()) == Some("power") {
                p += amt;
            } else {
                e += amt;
            }
        }
        (e, p)
    }

    /// py: _can_pay_generic_power
    pub fn can_pay_generic_power(&self, actor: Side, n: i64) -> bool {
        if n <= 0 {
            return true;
        }
        let p = self.gs.player(actor);
        let doms: Vec<Domain> = p.power_pool.keys().copied().collect();
        p.can_pay_power_of(n, &doms)
    }

    /// py: _can_pay_energy_and_generic
    pub fn can_pay_energy_and_generic(&self, actor: Side, energy: i64, power: i64, domain: Option<Domain>) -> bool {
        if self.gs.player(actor).energy() < energy {
            return false;
        }
        if domain.is_some() && power != 0 {
            return self.gs.player(actor).can_pay_cost(0, Some(power), domain);
        }
        self.can_pay_generic_power(actor, power)
    }

    /// py: _pay_energy_and_generic
    pub fn pay_energy_and_generic(&mut self, actor: Side, energy: i64, power: i64, domain: Option<Domain>) -> R<bool> {
        if !self.can_pay_energy_and_generic(actor, energy, power, domain) {
            return Ok(false);
        }
        let e = self.gs.player(actor).energy() - energy;
        self.gs.player_mut(actor).set_energy(e);
        if domain.is_some() && power != 0 {
            let ok = self.gs.player_mut(actor).pay_cost(0, Some(power), domain);
            self.drain_rune_recycles()?;
            return Ok(ok);
        }
        self.pay_generic_power(actor, power)
    }

    /// py: _pay_generic_power
    pub fn pay_generic_power(&mut self, actor: Side, n: i64) -> R<bool> {
        if n <= 0 {
            return Ok(true);
        }
        let doms: Vec<Domain> = self.gs.player(actor).power_pool.keys().copied().collect();
        for d in &doms {
            if self.gs.player(actor).can_pay_cost(0, Some(n), Some(*d)) {
                let ok = self.gs.player_mut(actor).pay_cost(0, Some(n), Some(*d));
                self.drain_rune_recycles()?;
                return Ok(ok);
            }
        }
        if !self.gs.player(actor).can_pay_power_of(n, &doms) {
            return Ok(false);
        }
        let ok = self.gs.player_mut(actor).pay_power_of(n, &doms);
        self.drain_rune_recycles()?;
        Ok(ok)
    }

    /// py: _offer_reveal_from_top (EK: no card has on_reveal_from_top)
    pub fn offer_reveal_from_top(&mut self, _actor: Side, cards: &[CardId]) -> R<Vec<CardId>> {
        for &c in cards {
            if self.gs.spec(c).effects.iter().any(|e| e.trigger == "on_reveal_from_top") {
                not_ported!("_offer_reveal_from_top", "on_reveal_from_top (Nocturne)");
            }
        }
        Ok(Vec::new())
    }

    /// py: _ambush_legal_lanes
    pub fn ambush_legal_lanes(&self, side: Side) -> Vec<usize> {
        let Some(champ) = self.gs.champion[side.idx()] else { return Vec::new() };
        if self.gs.champion_deployed[side.idx()] || !self.gs.has_keyword(champ, "AMBUSH") {
            return Vec::new();
        }
        let enemy_ok = self.ambush_enemy_ok(champ);
        let mut lanes = Vec::new();
        for (i, bf) in self.gs.battlefields.iter().enumerate() {
            if !bf.units_for(side).is_empty() || (enemy_ok && !bf.units_for(side.other()).is_empty()) {
                lanes.push(i);
            }
        }
        lanes
    }

    /// The card's AMBUSH reaches battlefields where there are enemy units
    /// (`enemy_ok` on its `ambush` effect: Rengar Trophy Hunter).
    pub fn ambush_enemy_ok(&self, card: CardId) -> bool {
        self.gs
            .spec(card)
            .effects
            .iter()
            .any(|e| e.trigger == "passive" && e.effect == "ambush" && truthy(e.params.get("enemy_ok")))
    }

    /// py: _deploy_ambush_champion
    pub fn deploy_ambush_champion(&mut self, side: Side, lane: usize) -> R<bool> {
        if !self.ambush_legal_lanes(side).contains(&lane) {
            return Ok(false);
        }
        let champ = self.gs.champion[side.idx()].unwrap();
        let (energy, power) = self.effective_cost(champ, side, None)?;
        let energy = (energy - self.destination_discount(champ, Some(lane as i64), side)?).max(0);
        if !self.pay_card(side, champ, energy, power, None)? {
            return Ok(false);
        }
        self.gs.champion_deployed[side.idx()] = true;
        self.play_unit(champ, side, Some(lane), "champion")?;
        if self.gs.reg.regole.corrette() {
            // D73: the battlefield's passives before the showdown's first decision.
            self.recompute_passives()?;
        }
        let bf = &mut self.gs.battlefields[lane];
        if !bf.units[0].is_empty() && !bf.units[1].is_empty() {
            bf.contested_this_turn = true;
            self.run_showdown(lane, Some(side))?;
        }
        Ok(true)
    }

    /// py: _fire_first_play_here
    pub fn fire_first_play_here(&mut self, side: Side, bf: usize, card: CardId, unit: Option<UnitId>) -> R<()> {
        let Some(bc) = self.gs.battlefields[bf].card else { return Ok(()) };
        let Some(es) = self.gs.spec(bc).effects.iter().find(|e| e.trigger == "on_first_unit_here").cloned() else {
            return Ok(());
        };
        let token = match unit {
            Some(u) => self.gs.unit(u).is_token,
            None => self.gs.card_is_token(card),
        };
        let ok = if es.params.get("plays").map(py_str).as_deref() == Some("unit_or_gear") {
            self.gs.is_unit_card(card) || self.gs.is_gear_card(card)
        } else {
            self.gs.is_unit_card(card) && !token
        };
        if !ok || self.gs.battlefields[bf].first_unit_here[side.idx()] {
            return Ok(());
        }
        self.gs.battlefields[bf].first_unit_here[side.idx()] = true;
        if es.effect != "move_ally_here_to_base" {
            let mut ex = crate::lp_phases::bf_extra(bf);
            ex.set("triggering_card", XVal::Card(card));
            return self.resolve_triggered_effects(bc, "on_first_unit_here", bf, side, Some(ex));
        }
        not_ported!("_fire_first_play_here", "move_ally_here_to_base (Star Spring)")
    }
}
