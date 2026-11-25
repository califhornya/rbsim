//! py: effects.py — target resolution and filters shared by the handlers
//! (_resolve_targets, has_valid_target, _passes_filter, _zone_card_matches,
//! _zone_effect_card_ok, _amount, _units_where, _fallback_units,
//! _source_unit, _gear_entries, move candidates and destinations).

use serde_json::{Map, Value};

use crate::cards::{py_int, truthy};
use crate::game::*;
use crate::lp_phases::py_str;
use crate::lp_triggers::Ctx;
use crate::model::*;
use crate::not_ported;
use crate::types::*;

pub const BOTH_SIDES_TARGETS: [&str; 6] = ["battlefield", "both", "both_players", "everyone", "all_units", "all_units_here"];
pub const CHOOSER_TARGETS: [&str; 5] = ["chosen_unit", "chosen", "any_unit", "a_unit", "unit"];
pub const FRIENDLY_TARGET_ALIASES: [&str; 9] =
    ["actor", "ally", "allies", "self", "this", "friendly", "friendly_unit", "all_friendly_units_here", "all_units_here"];
pub const ENEMY_TARGET_ALIASES: [&str; 5] = ["opponent", "enemy", "enemy_unit", "all_enemy_units_here", "chosen_enemy"];

pub fn everywhere_target(t: &str) -> Option<(&'static str, &'static str)> {
    Some(match t {
        "all_friendly_units_anywhere" => ("friendly", "anywhere"),
        "all_enemy_units_anywhere" => ("enemy", "anywhere"),
        "all_units_anywhere" => ("both", "anywhere"),
        "all_units_in_bases" => ("both", "base"),
        "enemy_unit_in_base" => ("enemy", "base"),
        _ => return None,
    })
}

pub fn is_single_unit_target(t: &str) -> bool {
    CHOOSER_TARGETS.contains(&t) || t == "enemy_unit" || t == "friendly_unit"
}

/// A gear in play (py: _gear_entries row): (owner side, holder, gear).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum GearHolder {
    Unit(UnitId),
    Base,
    Bf(usize),
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum GearRef {
    Card(CardId),
    Deployed(GearId),
}

pub fn sget<'a>(spec: &'a Map<String, Value>, k: &str) -> Option<&'a Value> {
    spec.get(k).filter(|v| !v.is_null())
}

pub fn sstr(spec: &Map<String, Value>, k: &str, default: &str) -> String {
    match spec.get(k) {
        None => default.to_string(),
        Some(v) => py_str(v),
    }
}

impl Game {
    /// py: EffectContext._player_for_target (sides); "chosen_player" asks.
    pub fn player_for_target(&mut self, ctx: &Ctx, target: &str) -> R<Side> {
        let key = target.to_lowercase();
        if FRIENDLY_TARGET_ALIASES.contains(&key.as_str()) {
            return Ok(ctx.actor);
        }
        if ENEMY_TARGET_ALIASES.contains(&key.as_str()) {
            return Ok(ctx.opponent);
        }
        if CHOOSER_TARGETS.contains(&key.as_str()) {
            return Ok(ctx.actor);
        }
        if key == "chosen_player" {
            let opts = [Opt::Side(ctx.opponent), Opt::Side(ctx.actor)];
            return match self.choose("player", ctx.actor, &opts, Opt::Side(ctx.opponent), Some(ctx.card))? {
                Opt::Side(s) => Ok(s),
                _ => unreachable!(),
            };
        }
        Err(EngineError::Py(format!("ValueError: Unknown player target '{target}'")))
    }

    /// py: EffectContext._units_for_target
    pub fn units_for_target(&mut self, ctx: &Ctx, target: &str) -> R<Vec<UnitId>> {
        let s = self.player_for_target(ctx, target)?;
        Ok(self.gs.battlefields[ctx.bf].units_for(s).clone())
    }

    /// py: _card_category_name
    pub fn card_category_name(&self, c: CardId) -> &'static str {
        self.gs.category(c).name()
    }

    /// py: _zone_card_matches(card, tf)
    pub fn zone_card_matches(&self, card: CardId, tf: &Value) -> bool {
        let Some(tf) = tf.as_object().filter(|o| !o.is_empty()) else { return true };
        let cat = self.card_category_name(card);
        if truthy(tf.get("is_unit")) && !matches!(cat, "UNIT" | "CHAMPION" | "LEGEND") {
            return false;
        }
        if truthy(tf.get("is_spell")) && cat != "SPELL" {
            return false;
        }
        if truthy(tf.get("is_gear")) && !self.gs.is_gear(card) {
            return false;
        }
        if truthy(tf.get("is_champion")) && cat != "CHAMPION" {
            return false;
        }
        if truthy(tf.get("is_legend")) && cat != "LEGEND" {
            return false;
        }
        if let Some(v) = tf.get("card_type") {
            if cat != py_str(v).to_uppercase() {
                return false;
            }
        }
        if let Some(v) = tf.get("subtype") {
            if !self.gs.tags(card).contains(&py_str(v)) {
                return false;
            }
        }
        if let Some(v) = tf.get("subtype_any") {
            let any: Vec<String> = v.as_array().map(|a| a.iter().map(py_str).collect()).unwrap_or_default();
            if !self.gs.tags(card).iter().any(|t| any.contains(t)) {
                return false;
            }
        }
        if truthy(tf.get("not_spell")) && cat == "SPELL" {
            return false;
        }
        if let Some(v) = tf.get("might_at_least") {
            if self.gs.might(card).unwrap_or(0) < py_int(v) {
                return false;
            }
        }
        true
    }

    /// py: _card_domains
    pub fn card_domains(&self, card: CardId) -> Vec<String> {
        let raw = self.gs.spec(card).raw.get("domain").filter(|v| !v.is_null()).map(py_str).unwrap_or_default();
        let mut out: Vec<String> = raw.split_whitespace().map(|p| p.to_uppercase()).collect();
        if let Some(d) = self.gs.domain(card) {
            let n = d.name().to_string();
            if !out.contains(&n) {
                out.push(n);
            }
        }
        out
    }

    /// py: _passes_filter(unit, tf, ctx) (unit None: AttributeError in Python)
    pub fn passes_filter_opt(&mut self, unit: Option<UnitId>, tf: &Value, ctx: &Ctx) -> R<bool> {
        match unit {
            Some(u) => self.passes_filter(u, tf, ctx),
            None => Err(EngineError::Py("AttributeError: None unit in filter".into())),
        }
    }

    /// py: _passes_filter(unit, tf, ctx)
    pub fn passes_filter(&mut self, unit: UnitId, tf: &Value, ctx: &Ctx) -> R<bool> {
        let Some(tf) = tf.as_object().filter(|o| !o.is_empty()) else { return Ok(true) };
        let card = self.gs.ucard(unit);
        if truthy(tf.get("exclude_self")) && card == ctx.card {
            return Ok(false);
        }
        if let Some(v) = tf.get("has_keyword") {
            if !self.gs.unit_has_keyword(unit, &py_str(v)) {
                return Ok(false);
            }
        }
        if let Some(v) = tf.get("lacks_keyword") {
            if self.gs.unit_has_keyword(unit, &py_str(v)) {
                return Ok(false);
            }
        }
        let cat = self.card_category_name(card);
        let u = self.gs.unit(unit).clone();
        if truthy(tf.get("is_gear")) && !self.gs.is_gear(card) {
            return Ok(false);
        }
        if truthy(tf.get("is_spell")) && cat != "SPELL" {
            return Ok(false);
        }
        if truthy(tf.get("is_unit")) && !matches!(cat, "UNIT" | "CHAMPION" | "LEGEND") {
            return Ok(false);
        }
        if truthy(tf.get("moved_this_turn")) && u.moves_this_turn == 0 {
            return Ok(false);
        }
        if truthy(tf.get("is_token")) && !u.is_token {
            return Ok(false);
        }
        if truthy(tf.get("non_token")) && u.is_token {
            return Ok(false);
        }
        if truthy(tf.get("is_legend")) && cat != "LEGEND" {
            return Ok(false);
        }
        if truthy(tf.get("is_champion")) && cat != "CHAMPION" {
            return Ok(false);
        }
        if let Some(v) = tf.get("card_type") {
            if cat != py_str(v).to_uppercase() {
                return Ok(false);
            }
        }
        let tags = self.gs.unit_tags(unit);
        if let Some(v) = tf.get("subtype") {
            if !tags.contains(&py_str(v)) {
                return Ok(false);
            }
        }
        if let Some(v) = tf.get("subtype_any") {
            let any: Vec<String> = v.as_array().map(|a| a.iter().map(py_str).collect()).unwrap_or_default();
            if !tags.iter().any(|t| any.contains(t)) {
                return Ok(false);
            }
        }
        if truthy(tf.get("is_buffed")) && u.might_counters <= 0 {
            return Ok(false);
        }
        if truthy(tf.get("is_damaged")) && u.damage <= 0 {
            return Ok(false);
        }
        if truthy(tf.get("is_attacking")) {
            not_ported!("_passes_filter", "is_attacking");
        }
        if let Some(d) = tf.get("domain").filter(|v| truthy(Some(v))) {
            if !self.card_domains(card).contains(&py_str(d).to_uppercase()) {
                return Ok(false);
            }
        }
        if truthy(tf.get("is_empowered")) && !u.empowered {
            return Ok(false);
        }
        if let Some(v) = tf.get("not_subtype").filter(|v| truthy(Some(v))) {
            if tags.contains(&py_str(v)) {
                return Ok(false);
            }
        }
        if truthy(tf.get("fury_threatened")) || truthy(tf.get("has_named_tag")) {
            not_ported!("_passes_filter", "fury_threatened / has_named_tag");
        }
        if truthy(tf.get("not_it")) {
            if let Some(XVal::List(it)) = ctx.extra.get("it") {
                if it.iter().any(|x| *x == XVal::Unit(unit)) {
                    return Ok(false);
                }
            }
        }
        if truthy(tf.get("is_exhausted")) && u.ready {
            return Ok(false);
        }
        if truthy(tf.get("is_ready")) && !u.ready {
            return Ok(false);
        }
        let m = self.gs.unit_might(unit);
        if truthy(tf.get("is_mighty")) && m < 5 {
            return Ok(false);
        }
        if let Some(v) = tf.get("might_at_most") {
            if m > py_int(v) {
                return Ok(false);
            }
        }
        if truthy(tf.get("at_battlefield")) {
            match self.locate_unit(unit) {
                Some((_, Some(_))) => {}
                _ => return Ok(false),
            }
        }
        if let Some(v) = tf.get("might_at_least") {
            if m < py_int(v) {
                return Ok(false);
            }
        }
        if truthy(tf.get("might_less_than_self")) {
            if let Some(src) = self.source_unit(ctx) {
                if m >= self.gs.unit_might(src) {
                    return Ok(false);
                }
            }
        }
        Ok(true)
    }

    /// py: _source_unit(ctx)
    pub fn source_unit(&self, ctx: &Ctx) -> Option<UnitId> {
        let mut units: Vec<UnitId> = Vec::new();
        for bf in &self.gs.battlefields {
            units.extend(bf.units[0].iter().copied());
            units.extend(bf.units[1].iter().copied());
        }
        units.extend(self.gs.player(ctx.actor).base_units.iter().copied());
        if let Some(&u) = units.iter().find(|&&u| self.gs.ucard(u) == ctx.card) {
            return Some(u);
        }
        let gear = units.into_iter().find(|&u| self.gs.unit(u).gear.contains(&ctx.card));
        if gear.is_none() && self.gs.reg.regole.corrette() {
            // D76 (profile 6427b90+D72-D76): "me" of a legend's ability is its
            // legend unit (Sett The Boss: "When you conquer, ready me").
            let legend = self.legend_units(ctx.actor).into_iter().find(|&l| self.gs.ucard(l) == ctx.card);
            if legend.is_some() {
                crate::registry::conta(76);
            }
            return legend;
        }
        gear
    }

    /// py: _friendly_units(ctx)
    pub fn ctx_friendly_units(&self, ctx: &Ctx) -> Vec<UnitId> {
        self.friendly_units_of(ctx.actor)
    }

    /// py: _units_at(ctx, side, where)
    pub fn units_at(&self, ctx: &Ctx, side: Side, where_: &str) -> Vec<UnitId> {
        if where_ == "here" {
            return self.gs.battlefields[ctx.bf].units_for(side).clone();
        }
        let mut units = Vec::new();
        if where_ == "battlefield" || where_ == "anywhere" {
            for bf in &self.gs.battlefields {
                units.extend(bf.units_for(side).iter().copied());
            }
        }
        if where_ == "base" || where_ == "anywhere" {
            units.extend(self.gs.player(side).base_units.iter().copied());
        }
        units
    }

    /// py: _units_where(ctx, side, where)
    pub fn units_where(&self, ctx: &Ctx, side: Side, where_: &str) -> R<Vec<UnitId>> {
        let here = self.gs.battlefields[ctx.bf].units_for(side).clone();
        if where_.is_empty() {
            return Ok(here);
        }
        if where_ == "base" {
            return Ok(self.gs.player(side).base_units.clone());
        }
        if where_ == "it_location" || where_ == "moved_bfs" {
            not_ported!("_units_where", "{where_}");
        }
        let mut out = here;
        for (i, bf) in self.gs.battlefields.iter().enumerate() {
            if i != ctx.bf {
                out.extend(bf.units_for(side).iter().copied());
            }
        }
        if where_ == "anywhere" {
            out.extend(self.gs.player(side).base_units.iter().copied());
        }
        Ok(out)
    }

    /// py: _choosable(ctx, units)
    pub fn choosable(&self, ctx: &Ctx, units: &[UnitId]) -> R<Vec<UnitId>> {
        let mut out = Vec::new();
        for &u in units {
            if self.can_choose(u, ctx.actor, Some(ctx.card))? {
                out.push(u);
            }
        }
        Ok(out)
    }

    /// py: _fallback_units(ctx, target, bias)
    pub fn fallback_units(&mut self, ctx: &Ctx, target: &str, bias: &str) -> R<Vec<UnitId>> {
        let (me, them) = (ctx.actor, ctx.opponent);
        let sides: Vec<Side> = if CHOOSER_TARGETS.contains(&target) {
            if bias == "enemy" { vec![them, me] } else { vec![me, them] }
        } else {
            match self.player_for_target(ctx, target) {
                Ok(s) => vec![s],
                Err(EngineError::Py(_)) => return Ok(Vec::new()),
                Err(e) => return Err(e),
            }
        };
        let mut units = Vec::new();
        for s in sides {
            for (i, bf) in self.gs.battlefields.iter().enumerate() {
                if i != ctx.bf {
                    units.extend(bf.units_for(s).iter().copied());
                }
            }
            units.extend(self.gs.player(s).base_units.iter().copied());
        }
        Ok(units)
    }

    fn it_list(ctx: &Ctx) -> Vec<UnitId> {
        match ctx.extra.get("it") {
            Some(XVal::List(v)) => v.iter().filter_map(|x| if let XVal::Unit(u) = x { Some(*u) } else { None }).collect(),
            _ => Vec::new(),
        }
    }

    /// py: _resolve_targets(ctx, spec, bias="none", prefer=None)
    pub fn resolve_targets(&mut self, ctx: &mut Ctx, spec: &Map<String, Value>, bias: &str,
                           prefer: Option<&dyn Fn(&Game, UnitId) -> i64>) -> R<Vec<UnitId>> {
        let target = sstr(spec, "target", "actor").to_lowercase();
        let scope = sstr(spec, "scope", "single").to_lowercase();
        if matches!(target.as_str(), "self" | "this" | "me") {
            return Ok(self.source_unit(ctx).into_iter().collect());
        }
        if target == "triggering_unit" {
            return Ok(ctx.extra.unit("triggering_unit").into_iter().collect());
        }
        if target == "friendly_units_with_it" {
            not_ported!("_resolve_targets", "friendly_units_with_it");
        }
        if target == "it" {
            let it = Self::it_list(ctx);
            return Ok(it.into_iter().filter(|&u| self.locate_unit(u).is_some()).collect());
        }
        let mut where_ = sstr(spec, "where", "").to_lowercase();
        if spec.get("where").map_or(false, |v| v.is_null()) {
            where_ = "none".into();
        }
        let mut units: Vec<UnitId>;
        if let Some((who, w)) = everywhere_target(&target) {
            where_ = w.to_string();
            let sides: Vec<Side> = match who {
                "friendly" => vec![ctx.actor],
                "enemy" => vec![ctx.opponent],
                _ => vec![ctx.actor, ctx.opponent],
            };
            units = Vec::new();
            for s in sides {
                units.extend(self.units_at(ctx, s, &where_));
            }
        } else if BOTH_SIDES_TARGETS.contains(&target.as_str()) {
            let b = &self.gs.battlefields[ctx.bf];
            units = b.units[0].iter().chain(b.units[1].iter()).copied().collect();
        } else if CHOOSER_TARGETS.contains(&target.as_str()) {
            let friendly = self.units_where(ctx, ctx.actor, &where_)?;
            let enemy = self.units_where(ctx, ctx.opponent, &where_)?;
            units = if bias == "enemy" { enemy.into_iter().chain(friendly).collect() } else { friendly.into_iter().chain(enemy).collect() };
        } else if !where_.is_empty() {
            let s = self.player_for_target(ctx, &target)?;
            units = self.units_where(ctx, s, &where_)?;
        } else {
            units = self.units_for_target(ctx, &target)?;
        }
        let hidden = self.gs.card(ctx.card).hidden_bf;
        if let Some(h) = hidden {
            if where_ != "base" && !target.starts_with("all") && !BOTH_SIDES_TARGETS.contains(&target.as_str())
                && everywhere_target(&target).is_none()
            {
                let at = &self.gs.battlefields[h];
                units.retain(|u| at.units[0].contains(u) || at.units[1].contains(u));
            }
        }
        let tf = sget(spec, "target_filter").filter(|v| truthy(Some(v))).cloned();
        if let Some(tf) = &tf {
            let mut kept = Vec::new();
            for u in units {
                if self.passes_filter(u, tf, ctx)? {
                    kept.push(u);
                }
            }
            units = kept;
        }
        if units.is_empty() && scope == "single" && !target.starts_with("all") && where_.is_empty() && hidden.is_none()
            && !self.gs.is_spell(ctx.card) && !truthy(spec.get("here")) && !BOTH_SIDES_TARGETS.contains(&target.as_str())
        {
            units = self.fallback_units(ctx, &target, bias)?;
            if let Some(tf) = &tf {
                let mut kept = Vec::new();
                for u in units {
                    if self.passes_filter(u, tf, ctx)? {
                        kept.push(u);
                    }
                }
                units = kept;
            }
        }
        if units.is_empty() {
            if scope == "single" {
                ctx.extra.set("it", XVal::List(Vec::new()));
            }
            return Ok(Vec::new());
        }
        if scope != "single" || target.starts_with("all") {
            return Ok(units);
        }
        let mut units = self.choosable(ctx, &units)?;
        let side_of = |g: &Game, u: UnitId| g.locate_unit(u).map(|w| w.0);
        if let Some(pref) = prefer {
            if !units.is_empty() {
                let lead = side_of(self, units[0]);
                let mut keyed: Vec<(bool, i64, usize, UnitId)> =
                    units.iter().enumerate().map(|(i, &u)| (side_of(self, u) != lead, pref(self, u), i, u)).collect();
                keyed.sort_by(|a, b| (a.0, a.1).cmp(&(b.0, b.1)).then(a.2.cmp(&b.2)));
                units = keyed.into_iter().map(|k| k.3).collect();
            }
        }
        let count = sget(spec, "count").map(py_int).filter(|&c| c != 0).unwrap_or(1).max(1) as usize;
        let mut picks: Vec<UnitId> = units.iter().copied().take(count).collect();
        if truthy(spec.get("up_to")) && bias != "none" {
            let want = if bias == "enemy" { ctx.opponent } else { ctx.actor };
            picks.retain(|&u| side_of(self, u) == Some(want));
        }
        if truthy(spec.get("same_location")) {
            not_ported!("_resolve_targets", "same_location");
        }
        let opts: Vec<Opt> = units.iter().map(|&u| Opt::Unit(u)).collect();
        let pk: Vec<Opt> = picks.iter().map(|&u| Opt::Unit(u)).collect();
        let up_to = if truthy(spec.get("up_to")) { Some(count as i64) } else { None };
        let kind = format!("target:{}", sstr(spec, "effect", "?"));
        let got = self.choose_many(&kind, ctx.actor, &opts, &pk, Some(ctx.card), up_to, None)?;
        let picked: Vec<UnitId> = got.iter().filter_map(|o| if let Opt::Unit(u) = o { Some(*u) } else { None }).collect();
        self.note_chosen(ctx.card, ctx.actor, &picked)?;
        ctx.extra.set("it", XVal::List(picked.iter().map(|&u| XVal::Unit(u)).collect()));
        Ok(picked)
    }

    /// py: has_valid_target(ctx, spec) -> None | bool
    pub fn has_valid_target(&mut self, ctx: &Ctx, spec: &Map<String, Value>) -> R<Option<bool>> {
        let effect = sstr(spec, "effect", "None");
        let mut ctx = ctx.clone();
        match effect.as_str() {
            "counter_spell" => return Ok(Some(!self.counter_targets(&ctx, spec).is_empty())),
            "kill_unit_or_gear" => {
                let (u, g) = self.unit_or_gear_options(&ctx, spec)?;
                return Ok(Some(!u.is_empty() || !g.is_empty()));
            }
            "stun_or_return_attacker" => not_ported!("has_valid_target", "{effect}"),
            "play_token" if sget(spec, "location").map(py_str).as_deref() == Some("enemy_occupied") => {
                not_ported!("has_valid_target", "play_token enemy_occupied")
            }
            "sequence" => {
                let steps: Vec<Value> = sget(spec, "steps").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                let mut found: Vec<Option<bool>> = Vec::new();
                for sub in steps {
                    if let Some(o) = sub.as_object() {
                        if o.get("target").and_then(|v| v.as_str()) != Some("it") {
                            found.push(self.has_valid_target(&ctx, o)?);
                        }
                    }
                }
                return Ok(if found.contains(&Some(false)) {
                    Some(false)
                } else if found.contains(&Some(true)) {
                    Some(true)
                } else {
                    None
                });
            }
            "attach_equipment" | "ready_gear" | "move_self_to_weaker_enemy_battlefield" | "champion_to_hand" | "akali_retreat"
            | "ward_unit" | "return_friendly_to_hand" | "play_one_banished_with_this" => {
                not_ported!("has_valid_target", "{effect}")
            }
            _ => {}
        }
        if effect == "reveal_play_top" && truthy(spec.get("kill_friendly")) {
            not_ported!("has_valid_target", "reveal_play_top");
        }
        let target = sstr(spec, "target", "").to_lowercase();
        let single = sstr(spec, "scope", "single").to_lowercase() == "single";
        if effect == "give_gear_temporary" && truthy(spec.get("or_unit")) {
            not_ported!("has_valid_target", "give_gear_temporary");
        }
        if single
            && (effect == "return_gear_to_hand" || effect == "give_gear_temporary"
                || (effect == "kill_gear" && ["", "none", "chosen_unit", "gear", "enemy_gear", "chosen_gear"].contains(&target.as_str())))
        {
            let mut entries = self.gear_entries(&ctx, true, true);
            if target == "enemy_gear" {
                entries.retain(|e| e.0 == ctx.opponent);
            }
            let tf = sget(spec, "target_filter").cloned().unwrap_or(Value::Object(Map::new()));
            return Ok(Some(entries.iter().any(|e| self.gear_matches(e.2, &tf))));
        }
        if single && (effect == "return_from_trash" || effect == "play_from_trash") && ["", "none", "friendly_unit"].contains(&target.as_str()) {
            let tf = match sget(spec, "target_filter").filter(|v| truthy(Some(v))) {
                Some(v) => v.clone(),
                None if target == "friendly_unit" => serde_json::json!({"is_unit": true}),
                None => Value::Object(Map::new()),
            };
            return Ok(Some(self.gs.player(ctx.actor).trash.iter().any(|&c| self.zone_card_matches(c, &tf))));
        }
        if !single || !is_single_unit_target(&target) {
            return Ok(None);
        }
        if effect == "move_unit" || effect == "move_units_to_base" {
            return Ok(Some(!self.move_candidates(&ctx, spec, effect == "move_units_to_base")?.is_empty()));
        }
        let mut s2 = spec.clone();
        s2.insert("scope".into(), Value::String("all".into()));
        let units = self.resolve_targets(&mut ctx, &s2, "none", None)?;
        Ok(Some(!self.choosable(&ctx, &units)?.is_empty()))
    }

    /// py: _unit_or_gear_options(ctx, spec) — kill_unit_or_gear's choices: (units,
    /// gear cards) passing its filter, the opponent's (with `side: any` the
    /// actor's too), `where: here` or anywhere.
    pub fn unit_or_gear_options(&mut self, ctx: &Ctx, spec: &Map<String, Value>) -> R<(Vec<UnitId>, Vec<CardId>)> {
        let tf = sget(spec, "target_filter").filter(|v| truthy(Some(v))).cloned().unwrap_or(Value::Object(Map::new()));
        let here = sget(spec, "where").and_then(|v| v.as_str()) == Some("here");
        let sides: Vec<Side> = if sget(spec, "side").and_then(|v| v.as_str()) == Some("any") {
            vec![ctx.opponent, ctx.actor]
        } else {
            vec![ctx.opponent]
        };
        let (mut units, mut gear) = (Vec::new(), Vec::new());
        for side in sides {
            let at = self.units_at(ctx, side, if here { "here" } else { "anywhere" });
            for u in self.choosable(ctx, &at)? {
                if self.passes_filter(u, &tf, ctx)? {
                    units.push(u);
                }
            }
            for e in self.gear_entries(ctx, true, true) {
                if e.0 != side || !self.gear_matches(e.2, &tf) {
                    continue;
                }
                let ok_here = match e.1 {
                    GearHolder::Bf(b) => b == ctx.bf,
                    GearHolder::Unit(u) => self.gs.battlefields[ctx.bf].units_for(side).contains(&u),
                    GearHolder::Base => false,
                };
                if !here || ok_here {
                    gear.push(self.gear_card(e.2));
                }
            }
        }
        Ok((units, gear))
    }

    /// py: _counterable(card, spec) — the printed cost within the card's limits.
    pub fn counterable(&self, card: CardId, spec: &Map<String, Value>) -> bool {
        let lim = |k: &str, d: i64| sget(spec, k).map(py_int).unwrap_or(d);
        let power = self.gs.cost_power(card).unwrap_or(0);
        self.gs.cost_energy(card) <= lim("max_energy", 99) && lim("min_power", 0) <= power && power <= lim("max_power", 99)
    }

    /// py: _chose_mine(ctx, item, only_one) — an opponent's chain item whose
    /// declared choices include one of our units or gear (Not So Fast).
    pub fn chose_mine(&self, ctx: &Ctx, idx: usize, only_one: bool) -> bool {
        let item = &self.gs.chain[idx];
        if item.player == ctx.actor {
            return false;
        }
        let mine_units = self.units_at(ctx, ctx.actor, "anywhere");
        let mine_gear: Vec<CardId> =
            self.gear_entries(ctx, false, false).into_iter().filter(|e| e.0 == ctx.actor).map(|e| self.gear_card(e.2)).collect();
        let mut hits: Vec<Opt> = Vec::new();
        if let Some(d) = &item.declared {
            for (_, (_k, _n, got)) in &d.items {
                let xs: Vec<Opt> = match got {
                    Chosen::One(o) => vec![o.clone()],
                    Chosen::Many(v) => v.clone(),
                };
                for x in xs {
                    let x = match x {
                        Opt::Tuple(v) if !v.is_empty() => v.last().unwrap().clone(),
                        o => o,
                    };
                    // getattr(x, "card", x): a unit's or deployed gear's card, else x itself.
                    let card = match &x {
                        Opt::Unit(u) => Some(self.gs.ucard(*u)),
                        Opt::Gear(g) => Some(self.gs.dgear[g.i()].card),
                        Opt::Card(c) => Some(*c),
                        _ => None,
                    };
                    let unit_hit = matches!(&x, Opt::Unit(u) if mine_units.contains(u));
                    if (unit_hit || card.map_or(false, |c| mine_gear.contains(&c))) && !hits.contains(&x) {
                        hits.push(x);
                    }
                }
            }
        }
        // Repulse: "that chooses it and no other friendly unit" (only_one).
        if only_one { hits.len() == 1 } else { !hits.is_empty() }
    }

    /// py: _uncounterable(side) — an EMPOWERED unit with "uncounterable" (Mel Newly Awakened).
    pub fn uncounterable(&self, side: Side) -> bool {
        self.friendly_units_of(side).into_iter().any(|u| self.gs.unit(u).empowered && self.has_effect(self.gs.ucard(u), "uncounterable"))
    }

    /// py: _counter_targets(ctx, spec) — indices of the chain items counter_spell may choose.
    pub fn counter_targets(&self, ctx: &Ctx, spec: &Map<String, Value>) -> Vec<usize> {
        let mine = truthy(sget(spec, "enemy_choosing_mine"));
        let only_one = truthy(sget(spec, "only_one"));
        let mut out = Vec::new();
        for (i, it) in self.gs.chain.iter().enumerate() {
            if it.card == ctx.card {
                continue;
            }
            let spell = self.gs.is_spell(it.card) && it.ability.is_none()
                && self.counterable(it.card, spec) && !self.has_effect(it.card, "cant_be_countered");
            if !(spell || (mine && it.ability.is_some())) {
                continue;
            }
            if self.uncounterable(it.player) {
                continue;
            }
            if mine && !self.chose_mine(ctx, i, only_one) {
                continue;
            }
            out.push(i);
        }
        out
    }

    /// py: _gear_entries(ctx, enemy_first, units=False)
    pub fn gear_entries(&self, ctx: &Ctx, enemy_first: bool, units: bool) -> Vec<(Side, GearHolder, GearRef)> {
        let order = if enemy_first { [ctx.opponent, ctx.actor] } else { [ctx.actor, ctx.opponent] };
        let mut entries = Vec::new();
        for side in order {
            let mut in_play: Vec<UnitId> = Vec::new();
            for bf in &self.gs.battlefields {
                in_play.extend(bf.units_for(side).iter().copied());
            }
            in_play.extend(self.gs.player(side).base_units.iter().copied());
            for &u in &in_play {
                for &g in &self.gs.unit(u).gear {
                    entries.push((side, GearHolder::Unit(u), GearRef::Card(g)));
                }
            }
            for &g in &self.gs.player(side).base_gear {
                entries.push((side, GearHolder::Base, GearRef::Card(g)));
            }
            for (i, bf) in self.gs.battlefields.iter().enumerate() {
                for &dg in &bf.gear[side.idx()] {
                    entries.push((side, GearHolder::Bf(i), GearRef::Deployed(dg)));
                }
            }
            if units {
                for &u in &in_play {
                    if self.gs.unit_is_gear(u) {
                        entries.push((side, GearHolder::Unit(u), GearRef::Card(self.gs.ucard(u))));
                    }
                }
            }
        }
        entries
    }

    pub fn gear_card(&self, g: GearRef) -> CardId {
        match g {
            GearRef::Card(c) => c,
            GearRef::Deployed(d) => self.gs.dgear[d.i()].card,
        }
    }

    /// py: _gear_matches
    pub fn gear_matches(&self, g: GearRef, tf: &Value) -> bool {
        let c = self.gear_card(g);
        let e = self.gs.cost_energy(c);
        if let Some(v) = tf.get("energy_at_most") {
            if e > py_int(v) {
                return false;
            }
        }
        if let Some(v) = tf.get("energy_at_least") {
            if e < py_int(v) {
                return false;
            }
        }
        if let Some(d) = tf.get("domain").filter(|v| truthy(Some(v))) {
            // "an enemy Chaos unit or gear" (Decree of Unity)
            return self.card_domains(c).contains(&py_str(d).to_uppercase());
        }
        true
    }

    /// py: _amount(ctx, spec): the amount sources of the ported cards.
    pub fn effect_amount(&mut self, ctx: &Ctx, spec: &Map<String, Value>) -> R<i64> {
        match sget(spec, "amount_source").filter(|v| truthy(Some(v))) {
            None => Ok(spec.get("amount").map(py_int).unwrap_or(0)),
            Some(Value::String(s)) if s == "other_battlefields_controlled" => {
                // "for each other battlefield you or allies control" (Seat of Power);
                // bf.control() records control on each other battlefield.
                let here = ctx.extra.bf("battlefield").unwrap_or(ctx.bf);
                let mut n = 0;
                for i in 0..self.gs.battlefields.len() {
                    if i != here && self.gs.battlefields[i].control() == Some(ctx.actor) {
                        n += 1;
                    }
                }
                Ok(n)
            }
            Some(Value::String(s)) if s == "n_distinct_tags_among_friendlies" => {
                // `tags`: only these count ("Bird, Cat, Dog, and Poro": Friendship).
                let only: Vec<String> = match spec.get("tags") {
                    Some(Value::Array(a)) => a.iter().map(py_str).collect(),
                    _ => Vec::new(),
                };
                let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
                for u in self.ctx_friendly_units(ctx) {
                    for t in self.gs.unit_tags(u) {
                        if only.is_empty() || only.contains(&t) {
                            seen.insert(t);
                        }
                    }
                }
                Ok(seen.len() as i64)
            }
            Some(src) => not_ported!("_amount", "amount_source {}", py_str(src)),
        }
    }

    /// py: _zone_effect_card_ok(card, spec) (`filter` / `target_filter`)
    pub fn zone_effect_card_ok(&self, card: CardId, spec: &Map<String, Value>) -> bool {
        self.zone_effect_card_ok_impl(card, spec)
    }

    /// _zone_effect_card_ok(card, {"target_filter": tf})
    pub fn zone_effect_card_ok_tf(&self, card: CardId, tf: &Value) -> bool {
        let mut m = Map::new();
        m.insert("target_filter".into(), tf.clone());
        self.zone_effect_card_ok_impl(card, &m)
    }

    /// py: _move_candidates(ctx, spec, to_base_verb) -> (side, unit)
    pub fn move_candidates(&mut self, ctx: &Ctx, spec: &Map<String, Value>, to_base: bool) -> R<Vec<(Side, UnitId)>> {
        let (me, them) = (ctx.actor, ctx.opponent);
        let target = sstr(spec, "target", "friendly_unit").to_lowercase();
        let mut cands: Vec<(Side, UnitId)>;
        if matches!(target.as_str(), "self" | "this" | "me") {
            cands = self.source_unit(ctx).map(|u| vec![(me, u)]).unwrap_or_default();
        } else if target == "it" {
            cands = Self::it_list(ctx).into_iter().filter_map(|u| self.locate_unit(u).map(|w| (w.0, u))).collect();
        } else {
            let enemy = target.contains("enemy") || target.contains("opponent");
            let friendly = target.contains("friendly") || target.contains("ally") || target.contains("actor");
            let default_from = if to_base || target.ends_with("_here") { "here" } else { "anywhere" };
            let frm = sstr(spec, "from", default_from).to_lowercase();
            let sides: Vec<Side> = if enemy { vec![them] } else if friendly { vec![me] } else { vec![them, me] };
            cands = Vec::new();
            for s in sides {
                for u in self.units_at(ctx, s, &frm) {
                    cands.push((s, u));
                }
            }
        }
        if let Some(tf) = sget(spec, "target_filter").filter(|v| truthy(Some(v))).cloned() {
            let mut kept = Vec::new();
            for (s, u) in cands {
                if self.passes_filter(u, &tf, ctx)? {
                    kept.push((s, u));
                }
            }
            cands = kept;
        }
        cands.retain(|&(s, u)| !(self.gs.unit(u).unmovable_by_enemies && s != me));
        if !target.starts_with("all") {
            let chooser = if sstr(spec, "mover", "") == "opponent" { them } else { me };
            let mut kept = Vec::new();
            for (s, u) in cands {
                if self.can_choose(u, chooser, Some(ctx.card))? {
                    kept.push((s, u));
                }
            }
            cands = kept;
        }
        let mut out = Vec::new();
        for (s, u) in cands {
            if !self.move_destinations(ctx, spec, to_base, s, u)?.is_empty() {
                out.push((s, u));
            }
        }
        Ok(out)
    }

    /// py: _move_dest_kind
    pub fn move_dest_kind(&self, ctx: &Ctx, spec: &Map<String, Value>, to_base: bool, side: Side) -> String {
        match sget(spec, "destination") {
            Some(d) => py_str(d).to_lowercase(),
            None => if to_base || side == ctx.opponent { "base".into() } else { "battlefield".into() },
        }
    }

    /// py: _move_destinations -> battlefields, None = base
    pub fn move_destinations(&mut self, ctx: &Ctx, spec: &Map<String, Value>, to_base: bool, side: Side, unit: UnitId)
                             -> R<Vec<Option<usize>>> {
        let dest = self.move_dest_kind(ctx, spec, to_base, side);
        let cur = self.locate_unit(unit).and_then(|w| w.1);
        if dest == "base" {
            return Ok(if cur.is_some() { vec![None] } else { Vec::new() });
        }
        if dest == "here" || dest == "this_battlefield" {
            return Ok(if cur != Some(ctx.bf) { vec![Some(ctx.bf)] } else { Vec::new() });
        }
        if matches!(dest.as_str(), "same_as_last_move" | "stunned_at" | "deployed_at" | "defended_at") {
            let key = if dest == "same_as_last_move" { "last_move_dst" } else { dest.as_str() };
            return Ok(match ctx.extra.bf(key) {
                Some(b) if cur != Some(b) => vec![Some(b)],
                _ => Vec::new(),
            });
        }
        if dest == "to_or_from_base" && cur.is_some() {
            return Ok(vec![None]);
        }
        let others: Vec<usize> = (0..self.gs.battlefields.len()).filter(|&b| Some(b) != cur).collect();
        Ok(match dest.as_str() {
            "any" => {
                let mut v: Vec<Option<usize>> = if cur.is_some() { vec![None] } else { Vec::new() };
                v.extend(others.into_iter().map(Some));
                v
            }
            "friendly_occupied" => others.into_iter().filter(|&b| !self.gs.battlefields[b].units_for(ctx.actor).is_empty()).map(Some).collect(),
            "controlled_battlefield" => {
                let hidden = self.gs.card(ctx.card).hidden_bf;
                let mut v = Vec::new();
                for b in others {
                    if self.gs.battlefields[b].control() == Some(ctx.actor) && (hidden.is_none() || hidden == Some(b)) {
                        v.push(Some(b));
                    }
                }
                v
            }
            "enemy_occupied" => others.into_iter().filter(|&b| !self.gs.battlefields[b].units_for(ctx.opponent).is_empty()).map(Some).collect(),
            "open" => {
                let last = ctx.extra.bf("last_move_dst");
                if let Some(l) = last {
                    if sstr(spec, "scope", "").to_lowercase() == "all" {
                        return Ok(if cur != Some(l) { vec![Some(l)] } else { Vec::new() });
                    }
                }
                others
                    .into_iter()
                    .filter(|&b| {
                        let bb = &self.gs.battlefields[b];
                        bb.units[0].is_empty() && bb.units[1].is_empty() && bb.controller().is_none()
                    })
                    .map(Some)
                    .collect()
            }
            _ => others.into_iter().map(Some).collect(),
        })
    }

    /// py: _attack_value
    pub fn attack_value(&self, side: Side, unit: UnitId, bf: usize) -> i64 {
        let b = &self.gs.battlefields[bf];
        let mine: i64 = b.units_for(side).iter().filter(|&&u| u != unit).map(|&u| self.gs.unit_might(u)).sum();
        let theirs: i64 = b.units_for(side.other()).iter().map(|&u| self.gs.unit_might(u)).sum();
        if theirs != 0 && mine + self.gs.unit_might(unit) >= theirs {
            return 3;
        }
        let ctl = b.controller_held();
        if theirs == 0 && ctl != Some(side) {
            return 2;
        }
        if ctl == Some(side) {
            return 1;
        }
        0
    }

    /// py: _take_off_board(ctx, unit) -> where it was
    pub fn take_off_board(&mut self, unit: UnitId) -> Option<(Side, Option<usize>)> {
        let w = self.locate_unit(unit)?;
        match w.1 {
            None => self.gs.player_mut(w.0).base_units.retain(|&u| u != unit),
            Some(b) => {
                let l = self.gs.battlefields[b].units_for_mut(w.0);
                if let Some(p) = l.iter().position(|&u| u == unit) {
                    l.remove(p);
                }
            }
        }
        Some(w)
    }
}

impl Battlefield {
    /// py: bf.control() without the &mut (control() notes control first; the
    /// value is the same as held_by after _note_control).
    pub fn controller_held(&self) -> Option<Side> {
        let mut b = self.clone();
        b.control()
    }
}
