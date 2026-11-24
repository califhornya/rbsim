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

/// py: cards_registry._EFFECT_TOP_LEVEL_FIELDS
const TOP_FIELDS: [&str; 11] =
    ["trigger", "timing", "condition", "target", "target_filter", "scope", "duration", "optional", "cost", "scaling", "additional_cost"];

/// py: json.dumps(v, sort_keys=True) (default separators, ensure_ascii).
pub fn py_dumps_sorted(v: &Value) -> String {
    fn esc(s: &str, out: &mut String) {
        out.push('"');
        for ch in s.chars() {
            match ch {
                '"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                '\t' => out.push_str("\\t"),
                '\u{8}' => out.push_str("\\b"),
                '\u{c}' => out.push_str("\\f"),
                c if (c as u32) < 0x20 || (c as u32) > 0x7e => {
                    let mut buf = [0u16; 2];
                    for u in c.encode_utf16(&mut buf) {
                        out.push_str(&format!("\\u{:04x}", u));
                    }
                }
                c => out.push(c),
            }
        }
        out.push('"');
    }
    fn w(v: &Value, out: &mut String) {
        match v {
            Value::Null => out.push_str("null"),
            Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
            Value::Number(n) => out.push_str(&n.to_string()),
            Value::String(s) => esc(s, out),
            Value::Array(a) => {
                out.push('[');
                for (i, x) in a.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    w(x, out);
                }
                out.push(']');
            }
            Value::Object(m) => {
                let mut keys: Vec<&String> = m.keys().collect();
                keys.sort();
                out.push('{');
                for (i, k) in keys.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    esc(k, out);
                    out.push_str(": ");
                    w(&m[k.as_str()], out);
                }
                out.push('}');
            }
        }
    }
    let mut out = String::new();
    w(v, &mut out);
    out
}

impl EffectSpec {
    /// py: EffectSpec.from_dict(data) — a spec made in play (a reflexive "then"):
    /// no origin; its canonical name is its value (no registry spec is equal
    /// to one with trigger "reflexive"). A `condition` (normalized in Python) is
    /// not ported.
    pub fn from_dict(data: &Map<String, Value>) -> Result<EffectSpec, String> {
        let mut d: Map<String, Value> = data.clone();
        if let Some(Value::Object(nested)) = data.get("params") {
            let mut m = nested.clone();
            for (k, v) in data {
                if k != "params" {
                    m.insert(k.clone(), v.clone());
                }
            }
            d = m;
        }
        let effect = match d.get("effect") {
            Some(Value::String(s)) => s.trim().to_string(),
            _ => return Err("an effect specification without a string 'effect'".into()),
        };
        if d.contains_key("condition") {
            return Err("EffectSpec.from_dict with a condition".into());
        }
        let get = |k: &str| d.get(k).cloned();
        let mut params = Map::new();
        for (k, v) in &d {
            if k != "effect" && !TOP_FIELDS.contains(&k.as_str()) {
                params.insert(k.clone(), v.clone());
            }
        }
        let field = |k: &str| -> Value {
            match k {
                "trigger" => get(k).unwrap_or_else(|| Value::String("on_play".into())),
                "optional" => get(k).unwrap_or(Value::Bool(false)),
                _ => get(k).unwrap_or(Value::Null),
            }
        };
        for k in TOP_FIELDS {
            if let Some(v) = d.get(k) {
                if !(v.is_string() || v.is_null() || (k == "optional" && v.is_boolean()) || k == "target_filter"
                    || k == "cost" || k == "scaling" || k == "additional_cost")
                {
                    return Err(format!("EffectSpec.from_dict: field {k} = {v}"));
                }
            }
        }
        let mut to_dict = Map::new();
        to_dict.insert("effect".into(), Value::String(effect.clone()));
        for k in TOP_FIELDS {
            let v = field(k);
            let default = match k {
                "trigger" => Value::String("on_play".into()),
                "optional" => Value::Bool(false),
                _ => Value::Null,
            };
            if v != default {
                to_dict.insert(k.into(), v);
            }
        }
        for (k, v) in &params {
            to_dict.insert(k.clone(), v.clone());
        }
        let s_of = |k: &str| field(k).as_str().map(|s| s.to_string());
        let mut merged = params.clone();
        if !merged.contains_key("effect") {
            merged.insert("effect".into(), Value::String(effect.clone()));
        }
        if let Some(t) = s_of("target") {
            merged.insert("target".into(), Value::String(t));
        }
        let tf = field("target_filter");
        if crate::cards::truthy(Some(&tf)) {
            merged.insert("target_filter".into(), tf.clone());
        }
        if let Some(t) = s_of("scope") {
            merged.insert("scope".into(), Value::String(t));
        }
        if let Some(t) = s_of("duration") {
            merged.insert("duration".into(), Value::String(t));
        }
        let mut asdict = Map::new();
        asdict.insert("effect".into(), Value::String(effect.clone()));
        for k in TOP_FIELDS {
            asdict.insert(k.into(), field(k));
        }
        asdict.insert("params".into(), Value::Object(params.clone()));
        Ok(EffectSpec {
            effect,
            trigger: s_of("trigger").unwrap_or_else(|| "on_play".into()),
            timing: s_of("timing"),
            condition: None,
            target: s_of("target"),
            target_filter: Some(tf).filter(|v| !v.is_null()),
            scope: s_of("scope"),
            duration: s_of("duration"),
            optional: field("optional").as_bool().unwrap_or(false),
            cost: Some(field("cost")).filter(|v| !v.is_null()),
            scaling: Some(field("scaling")).filter(|v| !v.is_null()),
            additional_cost: Some(field("additional_cost")).filter(|v| !v.is_null()),
            params,
            to_dict,
            merged,
            origin: None,
            spec_ref: py_dumps_sorted(&Value::Object(asdict)),
        })
    }
}

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
    /// py: encoding._CARD_INDEX: a name's place in sorted(CARD_REGISTRY).
    pub vocab: HashMap<String, usize>,
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
    /// py: encoding.card_id(name): 1-based; UNKNOWN_CARD if not in the vocabulary.
    pub fn card_id(&self, name: Option<&str>) -> i64 {
        match name.filter(|n| !n.is_empty()).and_then(|n| self.vocab.get(n)) {
            Some(&i) => i as i64 + 1,
            None => self.vocab.len() as i64 + 1,
        }
    }

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
        let mut names: Vec<&String> = by_name.keys().collect();
        names.sort();
        let vocab = names.iter().enumerate().map(|(i, n)| ((*n).clone(), i)).collect();
        Ok(Registry { cards, by_name, vocab })
    }

    pub fn get(&self, name: &str) -> Option<&CardSpec> {
        self.by_name.get(name).map(|&i| &self.cards[i])
    }
    pub fn index(&self, name: &str) -> Option<usize> {
        self.by_name.get(name).copied()
    }
}
