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
    /// The rules profile every game built on this registry plays (both
    /// players, the search copies, the replays): see `Regole`.
    pub regole: Regole,
    /// sha256 (16 hex) of the registry as loaded, the profile's data
    /// correction applied: the effective cards of the profile.
    pub impronta: String,
}

/// The rules profile (decision of 25/11, docs/audit/AUDIT.md "Deviations
/// after the freeze"). `Storiche`: the Python engine at 6427b90, deviations
/// included (the default; the parity checks fix it). `D72D76`: the same with
/// D72-D76 corrected, in the code and, for D74-D75, in the card data
/// (`correggi_dati`, applied as the registry loads). `D72D77`: D72-D76 plus
/// D77 (a Standard Move not held runs the showdowns its triggers staged).
/// `D72D80`: D72-D77 plus D78 (an effect's move honors "can't move this
/// turn"), D79 (a face-down play is a task) and D80 (no points after the win).
/// `D72D81`: D72-D80 plus D81 (Call to Glory without the buff costs its energy).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Regole {
    Storiche,
    D72D76,
    D72D77,
    D72D80,
    D72D81,
}

thread_local! {
    static CORREZIONI: std::cell::Cell<[u64; 10]> = const { std::cell::Cell::new([0; 10]) };
}

/// D72..D81 changed something in this thread (the real game or a search
/// copy): what explains a divergence from the historical rules.
pub fn conta(d: usize) {
    CORREZIONI.with(|c| {
        let mut v = c.get();
        v[d - 72] += 1;
        c.set(v);
    });
}

/// The counts of D72..D81 in this thread.
pub fn correzioni() -> [u64; 10] {
    CORREZIONI.with(|c| c.get())
}

pub fn azzera_correzioni() {
    CORREZIONI.with(|c| c.set([0; 10]));
}

/// The version of the card-data correction of the corrected profile.
pub const CORREZIONE_DATI: &str = "D72-D76/1";

impl Regole {
    pub const STORICHE: &'static str = "6427b90";
    pub const D72_D76: &'static str = "6427b90+D72-D76";
    pub const D72_D77: &'static str = "6427b90+D72-D77";
    pub const D72_D80: &'static str = "6427b90+D72-D80";
    pub const D72_D81: &'static str = "6427b90+D72-D81";

    pub fn parse(s: &str) -> Result<Regole, String> {
        match s {
            Self::STORICHE => Ok(Regole::Storiche),
            Self::D72_D76 => Ok(Regole::D72D76),
            Self::D72_D77 => Ok(Regole::D72D77),
            Self::D72_D80 => Ok(Regole::D72D80),
            Self::D72_D81 => Ok(Regole::D72D81),
            _ => Err(format!(
                "regole sconosciute: {s:?} (note: {:?}, {:?}, {:?}, {:?}, {:?})",
                Self::STORICHE,
                Self::D72_D76,
                Self::D72_D77,
                Self::D72_D80,
                Self::D72_D81
            )),
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Regole::Storiche => Self::STORICHE,
            Regole::D72D76 => Self::D72_D76,
            Regole::D72D77 => Self::D72_D77,
            Regole::D72D80 => Self::D72_D80,
            Regole::D72D81 => Self::D72_D81,
        }
    }
    /// D72-D76 corrected (also in the profile that adds D77).
    pub fn corrette(self) -> bool {
        matches!(self, Regole::D72D76 | Regole::D72D77 | Regole::D72D80 | Regole::D72D81)
    }
    /// D77 corrected: in the D72-D77 profile and the ones that add D78-D81.
    pub fn d77(self) -> bool {
        matches!(self, Regole::D72D77 | Regole::D72D80 | Regole::D72D81)
    }
    /// D78 (an effect's move honors "can't move this turn"): in D72-D80 and D72-D81.
    pub fn d78(self) -> bool {
        matches!(self, Regole::D72D80 | Regole::D72D81)
    }
    /// D79 (a face-down play runs as a task): in D72-D80 and D72-D81.
    pub fn d79(self) -> bool {
        matches!(self, Regole::D72D80 | Regole::D72D81)
    }
    /// D80 (no points once the game is won): in D72-D80 and D72-D81.
    pub fn d80(self) -> bool {
        matches!(self, Regole::D72D80 | Regole::D72D81)
    }
    /// D81 (Call to Glory without the buff costs its energy): only in D72-D81.
    pub fn d81(self) -> bool {
        self == Regole::D72D81
    }
}

/// The card data of every representation the engine reads (the spec's
/// fields, `params`, `merged`, `to_dict`, the instance's and the raw card's
/// effect dicts) for one effect: `f` is applied to each dict.
fn each_effect_dict(card: &mut Value, i: usize, f: &dyn Fn(&mut Map<String, Value>)) -> Result<(), String> {
    let name = card["name"].as_str().unwrap_or("?").to_string();
    let miss = || format!("correzione dati: {name}, effetto {i} mancante");
    let spec = card["effects"].get_mut(i).and_then(|e| e.as_object_mut()).ok_or_else(miss)?;
    f(spec);
    for key in ["merged", "to_dict"] {
        f(spec.get_mut(key).and_then(|v| v.as_object_mut()).ok_or_else(miss)?);
    }
    for path in [["inst", "effects"], ["raw", "effects"]] {
        let d = card[path[0]][path[1]].get_mut(i).and_then(|e| e.as_object_mut()).ok_or_else(miss)?;
        f(d);
    }
    Ok(())
}

/// The data correction of the corrected profile (CORREZIONE_DATI), on the
/// registry as exported from Python (rust/data/registry.json stays the
/// reproducible export of the reference):
/// - D74, Pillaged Armory: "BUFF a friendly unit" names no place: both
///   effects (on_play, on_conquer) `where: anywhere`;
/// - D75, Sett Kingpin: "each buffed friendly unit at my battlefield" counts
///   itself: no `exclude_self` in its target filter.
pub fn correggi_dati(root: &mut Value) -> Result<(), String> {
    let cards = root["cards"].as_array_mut().ok_or("registry: no cards")?;
    let mut find = |n: &str| -> Result<usize, String> {
        cards.iter().position(|c| c["name"] == n).ok_or(format!("correzione dati: {n} non c'è"))
    };
    let armory = find("Pillaged Armory")?;
    let kingpin = find("Sett Kingpin")?;
    for i in 0..2 {
        each_effect_dict(&mut cards[armory], i, &|d| {
            if d.contains_key("effect") || d.contains_key("target") {
                d.insert("where".into(), Value::from("anywhere"));
            }
        })?;
        let spec = cards[armory]["effects"][i].as_object_mut().unwrap();
        spec.get_mut("params").and_then(|v| v.as_object_mut()).ok_or("correzione dati: params")?
            .insert("where".into(), Value::from("anywhere"));
    }
    each_effect_dict(&mut cards[kingpin], 0, &|d| {
        if let Some(tf) = d.get_mut("target_filter").and_then(|v| v.as_object_mut()) {
            tf.remove("exclude_self");
        }
    })?;
    Ok(())
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
        Self::from_json_regole(text, Regole::Storiche)
    }

    /// The registry for a rules profile: the corrected one applies its data
    /// correction (correggi_dati) as it loads.
    pub fn from_json_regole(text: &str, regole: Regole) -> Result<Registry, String> {
        use sha2::{Digest, Sha256};
        let mut root: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
        if regole.corrette() {
            correggi_dati(&mut root)?;
        }
        let impronta = hex::encode(Sha256::digest(root.to_string().as_bytes()))[..16].to_string();
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
        Ok(Registry { cards, by_name, vocab, regole, impronta })
    }

    pub fn get(&self, name: &str) -> Option<&CardSpec> {
        self.by_name.get(name).map(|&i| &self.cards[i])
    }
    pub fn index(&self, name: &str) -> Option<usize> {
        self.by_name.get(name).copied()
    }
}
