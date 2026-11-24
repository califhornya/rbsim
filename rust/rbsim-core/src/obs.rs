//! What the PPO net sees of the state: py: core/decisions.py
//! Observation.from_state (the information set of a seat) and
//! ai/encoding.py encode_observation (its fixed-size float32 vector).
//! Values are computed in f64 and stored as f32, as numpy does with Python
//! floats.

use std::collections::BTreeMap;

use crate::model::GameState;
use crate::registry::Registry;
use crate::types::*;

pub const UNIT_KEYWORDS: [&str; 8] = ["ASSAULT", "SHIELD", "TANK", "BACKLINE", "DEFLECT", "GANKING", "TEMPORARY", "HIDDEN"];
pub const DOMAINS: [&str; 6] = ["FURY", "CALM", "MIND", "BODY", "CHAOS", "ORDER"];
pub const N_BF: usize = 3;
pub const MAX_HAND: usize = 12;
pub const N_TOKEN_FEATURES: usize = 8 + UNIT_KEYWORDS.len();
pub const TOKEN_WIDTH: usize = 2 + N_TOKEN_FEATURES;
pub const MAX_TOKENS: usize = 160;
const PER_BF_DENSE: usize = 3 + 2 + 2 + 2 + 2 + 2;
pub const DENSE_DIM: usize = 14 + 2 * 6 + 1 + N_BF + 2 + 2 * 6 + 2 + 2 + 2 + 2 + N_BF * PER_BF_DENSE + 4 + 2 * N_BF;
pub const HAND_ROWS: usize = MAX_HAND;
pub const OBS_DIM: usize = DENSE_DIM + MAX_TOKENS * TOKEN_WIDTH;

/// py: encoding.ZONES, in order: a zone's index.
fn zone(name: &str) -> f64 {
    static ZONES: std::sync::OnceLock<std::collections::HashMap<String, usize>> = std::sync::OnceLock::new();
    *ZONES.get_or_init(|| zones().into_iter().enumerate().map(|(i, z)| (z, i)).collect())
        .get(name)
        .expect("a zone") as f64
}

fn zones() -> Vec<String> {
    const LOCS: [&str; 4] = ["base", "bf0", "bf1", "bf2"];
    let mut z: Vec<String> = ["my_hand", "my_trash", "opp_trash", "my_deck", "my_banished", "opp_banished",
        "my_deck_top", "my_chain", "opp_chain", "my_legend", "opp_legend", "my_champion", "opp_champion"]
        .iter().map(|s| s.to_string()).collect();
    for w in ["my", "opp"] {
        for l in LOCS {
            z.push(format!("{w}_units_{l}"));
        }
    }
    for w in ["my", "opp"] {
        for l in LOCS {
            z.push(format!("{w}_attached_{l}"));
        }
    }
    z.push("my_base_gear".into());
    z.push("opp_base_gear".into());
    for w in ["my", "opp"] {
        for i in 0..N_BF {
            z.push(format!("{w}_deployed_bf{i}"));
        }
    }
    for i in 0..N_BF {
        z.push(format!("battlefield_{i}"));
    }
    for i in 0..N_BF {
        z.push(format!("my_facedown_bf{i}"));
    }
    z.push("chain_order".into());
    z.push("opp_hand_known".into());
    z
}

/// py: decisions.UnitView
#[derive(Clone, Debug)]
pub struct UnitView {
    pub name: String,
    pub might: i64,
    pub ready: bool,
    pub stunned: bool,
    pub is_token: bool,
    pub gear: Vec<String>,
    pub damage: i64,
    pub buffed: bool,
    pub empowered: bool,
    pub keywords: Vec<&'static str>,
    /// py: UnitView.lasting_might (UnitInPlay.lasting_might): what the search's
    /// table_value reads.
    pub lasting_might: i64,
}

/// py: decisions.BattlefieldView
#[derive(Clone, Debug)]
pub struct BattlefieldView {
    pub a: Vec<UnitView>,
    pub b: Vec<UnitView>,
    pub controller: Option<Side>,
    pub named: Option<String>,
    pub gear_a: Vec<String>,
    pub gear_b: Vec<String>,
    pub scored_a: bool,
    pub scored_b: bool,
    pub facedowns: Vec<Side>,
    pub my_facedown: Vec<Option<String>>,
}

/// py: decisions.Observation (what encode_observation reads).
#[derive(Clone, Debug)]
pub struct Observation {
    pub viewer: Side,
    pub turn: i64,
    pub active: Side,
    pub victory_score: i64,
    pub my_points: i64,
    pub opp_points: i64,
    pub my_energy: i64,
    pub opp_energy: i64,
    pub my_power: Vec<(Domain, i64)>,
    pub opp_power: Vec<(Domain, i64)>,
    pub my_xp: i64,
    pub opp_xp: i64,
    pub my_hand: Vec<String>,
    pub opp_hand_count: usize,
    pub my_deck_count: usize,
    pub opp_deck_count: usize,
    pub my_trash: Vec<String>,
    pub opp_trash: Vec<String>,
    pub my_base_units: Vec<UnitView>,
    pub opp_base_units: Vec<UnitView>,
    pub my_runes: i64,
    pub opp_runes: i64,
    pub battlefields: Vec<BattlefieldView>,
    pub showdown_bf: Option<usize>,
    pub my_chain: Vec<String>,
    pub opp_chain: Vec<String>,
    pub my_deck: Vec<String>,
    pub my_deck_top: Vec<String>,
    pub my_banished: Vec<String>,
    pub opp_banished: Vec<String>,
    pub my_legend: Option<String>,
    pub opp_legend: Option<String>,
    pub my_legend_ready: bool,
    pub opp_legend_ready: bool,
    pub my_legend_once_free: bool,
    pub opp_legend_once_free: bool,
    pub my_added_legends: Vec<(String, bool)>,
    pub opp_added_legends: Vec<(String, bool)>,
    pub my_champion: Option<String>,
    pub opp_champion: Option<String>,
    pub my_base_gear: Vec<String>,
    pub opp_base_gear: Vec<String>,
    pub my_runes_ready: i64,
    pub opp_runes_ready: i64,
    pub my_rune_domains: Vec<(Domain, i64)>,
    pub opp_rune_domains: Vec<(Domain, i64)>,
    pub my_cards_played: i64,
    pub opp_cards_played: i64,
    pub my_held_move: Option<usize>,
    pub opp_held_move: Option<usize>,
    pub chain: Vec<(bool, String)>,
    pub opp_hand_known: Vec<String>,
}

fn dom_get(v: &[(Domain, i64)], name: &str) -> i64 {
    v.iter().find(|(d, _)| d.name() == name).map_or(0, |(_, n)| *n)
}

impl Observation {
    /// py: Observation._uview(u)
    pub fn uview(gs: &GameState, u: UnitId) -> UnitView {
        let x = gs.unit(u);
        UnitView {
            name: gs.name(x.card).to_string(),
            might: gs.unit_might(u),
            ready: x.ready,
            stunned: x.stunned,
            is_token: x.is_token,
            gear: x.gear.iter().map(|&g| gs.name(g).to_string()).collect(),
            damage: x.damage,
            buffed: x.might_counters > 0,
            empowered: x.empowered,
            keywords: UNIT_KEYWORDS.iter().copied().filter(|k| gs.unit_has_keyword(u, k)).collect(),
            lasting_might: gs.unit_lasting_might(u),
        }
    }

    /// py: Observation.from_state(gs, viewer). bf.control() notes control:
    /// the state changes as in Python.
    pub fn from_state(gs: &mut GameState, viewer: Side) -> Observation {
        let other = viewer.other();
        let names = |gs: &GameState, cs: &[CardId]| -> Vec<String> { cs.iter().map(|&c| gs.name(c).to_string()).collect() };
        let mut bfs = Vec::new();
        for i in 0..gs.battlefields.len() {
            let a: Vec<UnitView> = gs.battlefields[i].units_for(Side::A).iter().map(|&u| Self::uview(gs, u)).collect();
            let b: Vec<UnitView> = gs.battlefields[i].units_for(Side::B).iter().map(|&u| Self::uview(gs, u)).collect();
            let controller = gs.battlefields[i].control();
            let bf = &gs.battlefields[i];
            bfs.push(BattlefieldView {
                a,
                b,
                controller,
                named: bf.card.map(|c| gs.name(c).to_string()),
                gear_a: bf.gear[0].iter().map(|&g| gs.name(gs.dgear[g.i()].card).to_string()).collect(),
                gear_b: bf.gear[1].iter().map(|&g| gs.name(gs.dgear[g.i()].card).to_string()).collect(),
                scored_a: bf.scored_this_turn[0],
                scored_b: bf.scored_this_turn[1],
                facedowns: bf.facedowns.iter().map(|f| f.owner).collect(),
                my_facedown: bf.facedowns.iter().map(|f| if f.owner == viewer { Some(gs.name(f.card).to_string()) } else { None }).collect(),
            });
        }
        let legend = |gs: &GameState, s: Side| -> (Option<String>, bool) {
            match gs.legend_unit[s.idx()] {
                Some(u) => (Some(gs.name(gs.unit(u).card).to_string()), gs.unit(u).ready),
                None => (gs.legend[s.idx()].map(|c| gs.name(c).to_string()), false),
            }
        };
        let once_free = |gs: &GameState, s: Side| -> bool {
            let Some(card) = gs.legend[s.idx()] else { return false };
            let once: Vec<usize> = gs.effects(card).iter().enumerate()
                .filter(|(_, e)| crate::cards::truthy(e.get("once_per_turn")))
                .map(|(i, _)| i)
                .collect();
            !once.is_empty() && !once.iter().any(|&i| {
                gs.once_per_turn_used.get(&crate::model::OnceK::Card(card, crate::model::OnceKey::Idx(i as i64))) == Some(&gs.turn)
            })
        };
        let added = |gs: &GameState, s: Side| -> Vec<(String, bool)> {
            gs.added_legends[s.idx()].iter().map(|(lu, _)| (gs.name(gs.unit(*lu).card).to_string(), gs.unit(*lu).ready)).collect()
        };
        let champion = |gs: &GameState, s: Side| -> Option<String> {
            match gs.champion[s.idx()] {
                Some(c) if !gs.champion_deployed[s.idx()] => Some(gs.name(c).to_string()),
                _ => None,
            }
        };
        let runes = |gs: &GameState, s: Side| -> (i64, Vec<(Domain, i64)>) {
            let p = gs.player(s);
            let ready = p.rune_pool.values().map(|rs| rs.iter().filter(|r| r.ready).count() as i64).sum();
            let doms = p.rune_pool.iter().filter(|(_, rs)| !rs.is_empty()).map(|(d, rs)| (*d, rs.len() as i64)).collect();
            (ready, doms)
        };
        let me = gs.player(viewer);
        let opp = gs.player(other);
        let held = gs.pending_move;
        let (my_leg, opp_leg) = (legend(gs, viewer), legend(gs, other));
        let (my_ready, my_doms) = runes(gs, viewer);
        let (opp_ready, opp_doms) = runes(gs, other);
        let mut my_deck = names(gs, &me.deck.cards);
        my_deck.sort();
        Observation {
            viewer,
            turn: gs.turn,
            active: gs.active,
            victory_score: gs.victory_score,
            my_points: gs.points[viewer.idx()],
            opp_points: gs.points[other.idx()],
            my_energy: me.energy(),
            opp_energy: opp.energy(),
            my_power: me.power_pool.iter().cloned().collect(),
            opp_power: opp.power_pool.iter().cloned().collect(),
            my_xp: gs.get_xp(viewer),
            opp_xp: gs.get_xp(other),
            my_hand: names(gs, &me.hand),
            opp_hand_count: opp.hand.len(),
            my_deck_count: me.deck.cards.len(),
            opp_deck_count: opp.deck.cards.len(),
            my_trash: names(gs, &me.trash),
            opp_trash: names(gs, &opp.trash),
            my_base_units: me.base_units.iter().map(|&u| Self::uview(gs, u)).collect(),
            opp_base_units: opp.base_units.iter().map(|&u| Self::uview(gs, u)).collect(),
            my_runes: me.total_runes_in_play(),
            opp_runes: opp.total_runes_in_play(),
            battlefields: bfs,
            showdown_bf: if gs.showdown_active { gs.showdown_bf_idx } else { None },
            my_chain: gs.chain.iter().filter(|i| i.player == viewer).map(|i| gs.name(i.card).to_string()).collect(),
            opp_chain: gs.chain.iter().filter(|i| i.player != viewer).map(|i| gs.name(i.card).to_string()).collect(),
            my_deck,
            my_deck_top: names(gs, &me.deck.known_on_top()),
            my_banished: names(gs, &me.banished),
            opp_banished: names(gs, &opp.banished),
            my_legend: my_leg.0,
            opp_legend: opp_leg.0,
            my_legend_ready: my_leg.1,
            opp_legend_ready: opp_leg.1,
            my_legend_once_free: once_free(gs, viewer),
            opp_legend_once_free: once_free(gs, other),
            my_added_legends: added(gs, viewer),
            opp_added_legends: added(gs, other),
            my_champion: champion(gs, viewer),
            opp_champion: champion(gs, other),
            my_base_gear: names(gs, &me.base_gear),
            opp_base_gear: names(gs, &opp.base_gear),
            my_runes_ready: my_ready,
            opp_runes_ready: opp_ready,
            my_rune_domains: my_doms,
            opp_rune_domains: opp_doms,
            my_cards_played: gs.cards_played_this_turn[viewer.idx()],
            opp_cards_played: gs.cards_played_this_turn[other.idx()],
            my_held_move: held.filter(|h| h.1 == viewer).map(|h| h.0),
            opp_held_move: held.filter(|h| h.1 == other).map(|h| h.0),
            chain: gs.chain.iter().map(|i| (i.player == viewer, gs.name(i.card).to_string())).collect(),
            opp_hand_known: names(gs, &opp.hand_known()),
        }
    }
}

fn b(x: bool) -> f64 {
    if x { 1.0 } else { 0.0 }
}

/// py: encoding._unit_features(u)
pub fn unit_features(u: &UnitView) -> Vec<f64> {
    let mut f = vec![u.might as f64 / 10.0, u.damage as f64 / 10.0, b(u.ready), b(u.stunned), b(u.is_token),
                     b(u.buffed), b(u.empowered), u.gear.len() as f64 / 3.0];
    for k in UNIT_KEYWORDS {
        f.push(b(u.keywords.contains(&k)));
    }
    f
}

/// py: encoding._dense(obs)
fn dense(o: &Observation) -> Vec<f64> {
    let vs = o.victory_score.max(1) as f64;
    let me = o.viewer;
    let mut s = vec![
        o.turn as f64 / 20.0,
        o.my_points as f64 / vs,
        o.opp_points as f64 / vs,
        o.victory_score as f64 / 8.0,
        o.my_energy as f64 / 15.0,
        o.opp_energy as f64 / 15.0,
        o.my_xp as f64 / 15.0,
        o.opp_xp as f64 / 15.0,
        o.my_hand.len() as f64 / 12.0,
        o.opp_hand_count as f64 / 12.0,
        o.my_deck_count as f64 / 40.0,
        o.opp_deck_count as f64 / 40.0,
        o.my_runes as f64 / 12.0,
        o.opp_runes as f64 / 12.0,
    ];
    s.extend(DOMAINS.iter().map(|d| dom_get(&o.my_power, d) as f64 / 12.0));
    s.extend(DOMAINS.iter().map(|d| dom_get(&o.opp_power, d) as f64 / 12.0));
    s.push(b(o.active == me));
    s.extend((0..N_BF).map(|i| b(o.showdown_bf == Some(i))));
    s.push(o.my_runes_ready as f64 / 12.0);
    s.push(o.opp_runes_ready as f64 / 12.0);
    s.extend(DOMAINS.iter().map(|d| dom_get(&o.my_rune_domains, d) as f64 / 12.0));
    s.extend(DOMAINS.iter().map(|d| dom_get(&o.opp_rune_domains, d) as f64 / 12.0));
    s.extend([b(o.my_legend_ready), b(o.opp_legend_ready)]);
    s.extend([b(o.my_legend_once_free), b(o.opp_legend_once_free)]);
    s.extend([b(o.my_champion.is_some()), b(o.opp_champion.is_some())]);
    s.extend([o.my_cards_played as f64 / 5.0, o.opp_cards_played as f64 / 5.0]);
    for i in 0..N_BF {
        let Some(bf) = o.battlefields.get(i) else {
            s.extend([0.0; PER_BF_DENSE]);
            continue;
        };
        let (mine, opp) = if me == Side::A { (&bf.a, &bf.b) } else { (&bf.b, &bf.a) };
        let ctrl = bf.controller;
        s.extend([b(ctrl == Some(me)), b(ctrl.is_some() && ctrl != Some(me)), b(ctrl.is_none())]);
        let (ms, os) = if me == Side::A { (bf.scored_a, bf.scored_b) } else { (bf.scored_b, bf.scored_a) };
        s.extend([b(ms), b(os)]);
        s.extend([bf.facedowns.iter().filter(|&&f| f == me).count() as f64,
                  bf.facedowns.iter().filter(|&&f| f != me).count() as f64]);
        s.extend([mine.len() as f64 / 6.0, opp.len() as f64 / 6.0]);
        s.extend([mine.iter().map(|u| u.might).sum::<i64>() as f64 / 20.0, opp.iter().map(|u| u.might).sum::<i64>() as f64 / 20.0]);
        let (mg, og) = if me == Side::A { (&bf.gear_a, &bf.gear_b) } else { (&bf.gear_b, &bf.gear_a) };
        s.extend([mg.len() as f64 / 4.0, og.len() as f64 / 4.0]);
    }
    s.extend([o.my_base_units.len() as f64 / 6.0, o.opp_base_units.len() as f64 / 6.0,
              o.my_base_units.iter().map(|u| u.might).sum::<i64>() as f64 / 20.0,
              o.opp_base_units.iter().map(|u| u.might).sum::<i64>() as f64 / 20.0]);
    s.extend((0..N_BF).map(|i| b(o.my_held_move == Some(i))));
    s.extend((0..N_BF).map(|i| b(o.opp_held_move == Some(i))));
    assert_eq!(s.len(), DENSE_DIM);
    s
}

type Row = (f64, i64, Vec<f64>);

fn plain(v: f64) -> Vec<f64> {
    let mut f = vec![0.0; N_TOKEN_FEATURES];
    f[0] = v;
    f
}

/// py: encoding._tokens(obs): the rows after the hand's.
fn tokens(o: &Observation, reg: &Registry) -> Vec<Row> {
    let me = o.viewer;
    let mut rows: Vec<Row> = Vec::new();
    let cid = |n: &str| reg.card_id(Some(n));
    for n in o.my_hand.iter().skip(HAND_ROWS) {
        rows.push((zone("my_hand"), cid(n), plain(1.0 / 3.0)));
    }
    let counted = |rows: &mut Vec<Row>, z: &str, names: &[String]| {
        let mut counts: BTreeMap<&String, i64> = BTreeMap::new();
        for n in names {
            *counts.entry(n).or_insert(0) += 1;
        }
        for (n, k) in counts {
            rows.push((zone(z), cid(n), plain(k as f64 / 3.0)));
        }
    };
    // py: units = {(my, base), (opp, base), then (my, bfI), (opp, bfI)}: dict order.
    let mut units: Vec<(String, &Vec<UnitView>)> = vec![("my_units_base".into(), &o.my_base_units),
                                                         ("opp_units_base".into(), &o.opp_base_units)];
    let mut attached: Vec<String> = vec!["my_attached_base".into(), "opp_attached_base".into()];
    for (i, bf) in o.battlefields.iter().take(N_BF).enumerate() {
        let (mine, opp) = if me == Side::A { (&bf.a, &bf.b) } else { (&bf.b, &bf.a) };
        units.push((format!("my_units_bf{i}"), mine));
        units.push((format!("opp_units_bf{i}"), opp));
        attached.push(format!("my_attached_bf{i}"));
        attached.push(format!("opp_attached_bf{i}"));
    }
    for (z, us) in &units {
        for u in us.iter() {
            rows.push((zone(z), cid(&u.name), unit_features(u)));
        }
    }
    counted(&mut rows, "my_chain", &o.my_chain);
    counted(&mut rows, "opp_chain", &o.opp_chain);
    for (z, name, ready) in [("my_legend", &o.my_legend, o.my_legend_ready), ("opp_legend", &o.opp_legend, o.opp_legend_ready)] {
        if let Some(n) = name.as_ref().filter(|n| !n.is_empty()) {
            rows.push((zone(z), cid(n), plain(b(ready))));
        }
    }
    for (z, added) in [("my_legend", &o.my_added_legends), ("opp_legend", &o.opp_added_legends)] {
        for (n, ready) in added {
            rows.push((zone(z), cid(n), plain(b(*ready))));
        }
    }
    for (z, name) in [("my_champion", &o.my_champion), ("opp_champion", &o.opp_champion)] {
        if let Some(n) = name.as_ref().filter(|n| !n.is_empty()) {
            rows.push((zone(z), cid(n), plain(1.0 / 3.0)));
        }
    }
    for (i, bf) in o.battlefields.iter().take(N_BF).enumerate() {
        if let Some(n) = bf.named.as_ref().filter(|n| !n.is_empty()) {
            rows.push((zone(&format!("battlefield_{i}")), cid(n), plain(1.0 / 3.0)));
        }
    }
    for (i, bf) in o.battlefields.iter().take(N_BF).enumerate() {
        for (slot, name) in bf.my_facedown.iter().enumerate() {
            if let Some(n) = name.as_ref().filter(|n| !n.is_empty()) {
                let mut f = plain(1.0 / 3.0);
                f[1] = slot as f64 / 3.0;
                rows.push((zone(&format!("my_facedown_bf{i}")), cid(n), f));
            }
        }
    }
    for (depth, (mine, name)) in o.chain.iter().rev().enumerate() {
        let mut f = plain(1.0 / 3.0);
        f[1] = b(*mine);
        f[2] = depth as f64 / 3.0;
        rows.push((zone("chain_order"), cid(name), f));
    }
    counted(&mut rows, "opp_hand_known", &o.opp_hand_known);
    for (rank, name) in o.my_deck_top.iter().enumerate() {
        let mut f = plain(1.0 / 3.0);
        f[1] = rank as f64 / 3.0;
        rows.push((zone("my_deck_top"), cid(name), f));
    }
    for ((_, us), z) in units.iter().zip(attached.iter()) {
        let gear: Vec<String> = us.iter().flat_map(|u| u.gear.iter().cloned()).collect();
        counted(&mut rows, z, &gear);
    }
    counted(&mut rows, "my_base_gear", &o.my_base_gear);
    counted(&mut rows, "opp_base_gear", &o.opp_base_gear);
    for (i, bf) in o.battlefields.iter().take(N_BF).enumerate() {
        let (mg, og) = if me == Side::A { (&bf.gear_a, &bf.gear_b) } else { (&bf.gear_b, &bf.gear_a) };
        counted(&mut rows, &format!("my_deployed_bf{i}"), mg);
        counted(&mut rows, &format!("opp_deployed_bf{i}"), og);
    }
    counted(&mut rows, "my_trash", &o.my_trash);
    counted(&mut rows, "opp_trash", &o.opp_trash);
    counted(&mut rows, "my_banished", &o.my_banished);
    counted(&mut rows, "opp_banished", &o.opp_banished);
    counted(&mut rows, "my_deck", &o.my_deck);
    rows
}

/// py: encoding.encode_observation(obs) -> float32[OBS_DIM]
pub fn encode_observation(o: &Observation, reg: &Registry) -> Vec<f32> {
    let mut v: Vec<f32> = dense(o).into_iter().map(|x| x as f32).collect();
    let mut table = vec![0f32; MAX_TOKENS * TOKEN_WIDTH];
    let mut put = |r: usize, z: f64, c: i64, f: &[f64]| {
        let row = &mut table[r * TOKEN_WIDTH..(r + 1) * TOKEN_WIDTH];
        row[0] = z as f32;
        row[1] = c as f32;
        for (k, x) in f.iter().enumerate() {
            row[2 + k] = *x as f32;
        }
    };
    for (r, n) in o.my_hand.iter().take(HAND_ROWS).enumerate() {
        put(r, zone("my_hand"), reg.card_id(Some(n)), &plain(1.0 / 3.0));
    }
    for (k, (z, c, f)) in tokens(o, reg).into_iter().take(MAX_TOKENS - HAND_ROWS).enumerate() {
        put(HAND_ROWS + k, z, c, &f);
    }
    v.extend(table);
    assert_eq!(v.len(), OBS_DIM);
    v
}
