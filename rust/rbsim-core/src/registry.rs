//! The card registry, from the JSON exported by `riftbound/rs/export_registry.py`
//! (the resolved CARD_REGISTRY: all_cards.json + cards_registry.py).

use serde_json::{Map, Value};
use std::collections::HashMap;
use std::rc::Rc;

use crate::types::{CardClass, CardType, Domain};

/// py: cards_registry.EffectSpec (frozen). `to_dict` and `merged` as Python computes them.
#[derive(Debug, PartialEq)]
pub struct EffectSpec {
    pub effect: String,
    pub trigger: String,
    pub timing: Option<String>,
    pub condition: Option<Value>,
    pub target: Option<String>,
    pub target_filter: Option<Value>,
    pub scope: Option<String>,
    pub duration: Option<String>,
    pub optional: bool,
    pub cost: Option<Value>,
    pub scaling: Option<Value>,
    pub additional_cost: Option<Value>,
    pub params: Map<String, Value>,
    pub to_dict: Map<String, Value>,
    pub merged: Map<String, Value>,
    /// (card name, index) in the registry; None for a spec made in play.
    pub origin: Option<(String, usize)>,
    /// How the canonical dump names it (canon.spec_ref).
    pub spec_ref: String,
}

pub type Spec = Rc<EffectSpec>;

#[derive(Debug)]
pub struct CardSpec {
    pub name: String,
    pub category: Option<CardType>,
    pub domain: Option<Domain>,
    pub cost_energy: i64,
    pub cost_power: Option<i64>,
    pub cost_power_domain: Option<Domain>,
    pub might: Option<i64>,
    pub damage: Option<i64>,
    pub keywords: Vec<String>,
    pub tags: Vec<String>,
    pub effects: Vec<Spec>,
    pub raw: Map<String, Value>,
    /// What instantiate() puts on the card in play.
    pub inst: Option<Inst>,
}

#[derive(Debug, Clone)]
pub struct Inst {
    pub class: CardClass,
    pub category: CardType,
    pub might: Option<i64>,
    pub cost_energy: i64,
    pub cost_power: Option<i64>,
    pub cost_power_domain: Option<Domain>,
    pub domain: Option<Domain>,
    pub keywords: Vec<String>,
    pub tags: Vec<String>,
    /// The card's `effects` (list of dicts: EffectSpec.to_dict).
    pub effects: Vec<Map<String, Value>>,
    pub damage: Option<i64>,
    pub repeat_cost: Value,
    pub flow_cost: Value,
    pub grants_tags: Vec<String>,
    pub also_gear: bool,
}

pub struct Registry {
    pub cards: Vec<CardSpec>,
    pub by_name: HashMap<String, usize>,
}

fn s_opt(v: &Value) -> Option<String> {
    v.as_str().map(|s| s.to_string())
}
fn v_opt(v: &Value) -> Option<Value> {
    if v.is_null() { None } else { Some(v.clone()) }
}
fn obj(v: &Value) -> Map<String, Value> {
    v.as_object().cloned().unwrap_or_default()
}
fn strs(v: &Value) -> Vec<String> {
    v.as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect()).unwrap_or_default()
}

impl Registry {
    pub fn from_json(text: &str) -> Result<Registry, String> {
        let root: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
        let mut cards = Vec::new();
        let mut by_name = HashMap::new();
        for c in root["cards"].as_array().ok_or("registry: no cards")? {
            let name = c["name"].as_str().unwrap_or("").to_string();
            let effects: Vec<Spec> = c["effects"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .enumerate()
                        .map(|(i, e)| {
                            Rc::new(EffectSpec {
                                effect: e["effect"].as_str().unwrap_or("").to_string(),
                                trigger: e["trigger"].as_str().unwrap_or("on_play").to_string(),
                                timing: s_opt(&e["timing"]),
                                condition: v_opt(&e["condition"]),
                                target: s_opt(&e["target"]),
                                target_filter: v_opt(&e["target_filter"]),
                                scope: s_opt(&e["scope"]),
                                duration: s_opt(&e["duration"]),
                                optional: e["optional"].as_bool().unwrap_or(false),
                                cost: v_opt(&e["cost"]),
                                scaling: v_opt(&e["scaling"]),
                                additional_cost: v_opt(&e["additional_cost"]),
                                params: obj(&e["params"]),
                                to_dict: obj(&e["to_dict"]),
                                merged: obj(&e["merged"]),
                                origin: Some((name.clone(), i)),
                                spec_ref: e["spec_ref"].as_str().unwrap_or("").to_string(),
                            })
                        })
                        .collect()
                })
                .unwrap_or_default();
            let inst = if c["inst"].is_null() {
                None
            } else {
                let i = &c["inst"];
                Some(Inst {
                    class: CardClass::from_py(i["class"].as_str().unwrap_or("")),
                    category: CardType::from_py(i["category"].as_str().unwrap_or("")).unwrap_or(CardType::Unit),
                    might: i["might"].as_i64(),
                    cost_energy: i["cost_energy"].as_i64().unwrap_or(0),
                    cost_power: i["cost_power"].as_i64(),
                    cost_power_domain: i["cost_power_domain"].as_str().and_then(Domain::from_py),
                    domain: i["domain"].as_str().and_then(Domain::from_py),
                    keywords: strs(&i["keywords"]),
                    tags: strs(&i["tags"]),
                    effects: i["effects"].as_array().map(|a| a.iter().map(obj).collect()).unwrap_or_default(),
                    damage: i["damage"].as_i64(),
                    repeat_cost: i["repeat_cost"].clone(),
                    flow_cost: i["flow_cost"].clone(),
                    grants_tags: strs(&i["grants_tags"]),
                    also_gear: i["also_gear"].as_bool().unwrap_or(false),
                })
            };
            let spec = CardSpec {
                name: name.clone(),
                category: c["category"].as_str().and_then(CardType::from_py),
                domain: c["domain"].as_str().and_then(Domain::from_py),
                cost_energy: c["cost_energy"].as_i64().unwrap_or(0),
                cost_power: c["cost_power"].as_i64(),
                cost_power_domain: c["cost_power_domain"].as_str().and_then(Domain::from_py),
                might: c["might"].as_i64(),
                damage: c["damage"].as_i64(),
                keywords: strs(&c["keywords"]),
                tags: strs(&c["tags"]),
                effects,
                raw: obj(&c["raw"]),
                inst,
            };
            by_name.insert(name, cards.len());
            cards.push(spec);
        }
        Ok(Registry { cards, by_name })
    }

    pub fn get(&self, name: &str) -> Option<&CardSpec> {
        self.by_name.get(name).map(|&i| &self.cards[i])
    }
    pub fn index(&self, name: &str) -> Option<usize> {
        self.by_name.get(name).copied()
    }
}
