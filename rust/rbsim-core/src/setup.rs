//! py: game_factory.build_game / make_deck_from_file and
//! cards_registry.load_deck_json — a game from two deck files and a seed,
//! with the same random draws as Python.

use serde_json::Value;
use std::rc::Rc;

use crate::game::Game;
use crate::model::*;
use crate::pydict::PyDict;
use crate::registry::Registry;
use crate::rng::PyRandom;
use crate::types::*;

pub struct DeckData {
    pub cards: Vec<String>,
    pub runes: Vec<(Domain, i64)>,
    pub champion: Option<String>,
    pub legend: Option<String>,
    pub battlefields: Vec<String>,
}

/// py: load_deck_json (names only; the registry checks are Python's).
pub fn load_deck(text: &str) -> Result<DeckData, String> {
    let d: Value = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let s = |v: &Value| v.as_str().unwrap_or("").trim().to_string();
    let champion = Some(s(&d["champion"])).filter(|x| !x.is_empty());
    let legend = Some(s(&d["legend"])).filter(|x| !x.is_empty());
    let mut battlefields = Vec::new();
    for e in d["battlefields"].as_array().cloned().unwrap_or_default() {
        let n = if e.is_object() { s(&e["name"]) } else { s(&e) };
        if !n.is_empty() {
            battlefields.push(n);
        }
    }
    let mut cards = Vec::new();
    for e in d["cards"].as_array().cloned().unwrap_or_default() {
        let n = s(&e["name"]);
        let c = e["count"].as_i64().unwrap_or(1);
        for _ in 0..c {
            cards.push(n.clone());
        }
    }
    let mut runes = Vec::new();
    for e in d["runes"].as_array().cloned().unwrap_or_default() {
        let dom = Domain::from_py(&s(&e["domain"])).ok_or("rune domain")?;
        runes.push((dom, e["count"].as_i64().unwrap_or(1)));
    }
    Ok(DeckData { cards, runes, champion, legend, battlefields })
}

/// An empty GameState around a registry (players, two battlefields added by the caller).
pub fn empty_state(reg: Rc<Registry>, rng: PyRandom) -> GameState {
    let p = |s| Player::new(s, Deck::default(), RuneDeck { runes: Vec::new(), unseen: Some(0) });
    GameState {
        reg,
        cards: Vec::new(),
        units: Vec::new(),
        dgear: Vec::new(),
        rng,
        players: [p(Side::A), p(Side::B)],
        turn: 1,
        max_turns: 40,
        active: Side::A,
        champion: [None, None],
        legend: [None, None],
        legend_unit: [None, None],
        extra_legends: [Vec::new(), Vec::new()],
        added_legends: [Vec::new(), Vec::new()],
        points: [0, 0],
        victory_score: 8,
        winner: None,
        battlefields: Vec::new(),
        champion_deployed: [false, false],
        chain: Vec::new(),
        pending_move: None,
        staged_showdowns: Vec::new(),
        showdown_active: false,
        showdown_bf_idx: None,
        showdown_attacker: None,
        focus_player: None,
        xp: [0, 0],
        cards_played_this_turn: [0, 0],
        spells_played_this_turn: [0, 0],
        played_cards_this_turn: [Vec::new(), Vec::new()],
        enemy_choices_this_turn: [0, 0],
        next_card_discounts: [Vec::new(), Vec::new()],
        delayed_effects: Vec::new(),
        delayed_main: Vec::new(),
        once_per_turn_used: PyDict::new(),
        xp_gained_turn: PyDict::new(),
        no_spell_damage_turn: -1,
        decree_turn: -1,
        next_spell_bonus: PyDict::new(),
        modes_chosen: PyDict::new(),
        next_unit_any_bf: PyDict::new(),
        next_unit_accelerate: PyDict::new(),
        next_spell_repeat: PyDict::new(),
        held_hostage: Vec::new(),
        move_group: None,
        jhin_pile: PyDict::new(),
        spell_spent: PyDict::new(),
        turn_cost_changes: Vec::new(),
        extra_turns: Vec::new(),
        free_hide: PyDict::new(),
        buff_bonus_turn: PyDict::new(),
        rally_turn: PyDict::new(),
        conquer_return: Vec::new(),
        cant_play_spells_turn: PyDict::new(),
        chain_uid: 1,
        chain_gone: Vec::new(),
        next_unit_ready_buff: PyDict::new(),
        died_in_beginning: PyDict::new(),
        in_beginning_phase: false,
        runes_at_beginning: (0, PyDict::new()),
        in_ending_phase: false,
        turns_taken: [0, 0],
        cant_play_cards_turn: PyDict::new(),
        unit_play_draws: PyDict::new(),
        units_enter_ready_turn: [-1, -1],
        next_units_enter_ready: [0, 0],
        friendly_unit_died_this_turn: [false, false],
        friendly_gear_died_this_turn: [false, false],
        discarded_this_turn: [false, false],
        cards_burned_this_turn: [0, 0],
        conquered_this_turn: [0, 0],
        hold_points_this_turn: [0, 0],
    }
}

fn instantiate(gs: &mut GameState, name: &str) -> Result<CardId, String> {
    let i = gs.reg.index(name).ok_or_else(|| format!("unknown card {name}"))?;
    Ok(gs.new_card(i as u32))
}

/// py: build_game(game_seed, deck_a_path, deck_b_path, ai_a=None, ai_b=None,
/// victory_score=8, starting_energy=0, first_player, max_turns, bf_a=None, bf_b=None)
pub fn build_game(reg: Rc<Registry>, game_seed: i64, deck_a: &DeckData, deck_b: &DeckData, first_player: &str,
                  max_turns: i64, bf_a: Option<&str>, bf_b: Option<&str>) -> Result<Game, String> {
    let mut rng = PyRandom::new(game_seed as i128);
    let mut rune_rng_a = PyRandom::new(rng.randrange(1 << 30) as i128);
    let mut rune_rng_b = PyRandom::new(rng.randrange(1 << 30) as i128);
    let mut gs = empty_state(reg.clone(), PyRandom::new(0));
    let mut make = |gs: &mut GameState, d: &DeckData| -> Result<(Vec<CardId>, Vec<Rune>, Option<CardId>, Option<CardId>, Vec<String>), String> {
        let mut cards = Vec::new();
        for n in &d.cards {
            cards.push(instantiate(gs, n)?);
        }
        let mut runes = Vec::new();
        for &(dom, c) in &d.runes {
            for _ in 0..c {
                runes.push(Rune { domain: dom, ready: true });
            }
        }
        let champ = match &d.champion {
            Some(n) => Some(instantiate(gs, n)?),
            None => None,
        };
        let legend = match &d.legend {
            Some(n) => Some(instantiate(gs, n)?),
            None => None,
        };
        Ok((cards, runes, champ, legend, d.battlefields.clone()))
    };
    let (mut main_a, mut runes_a, champ_a, legend_a, bfs_a) = make(&mut gs, deck_a)?;
    rune_rng_a.shuffle(&mut runes_a);
    let (mut main_b, mut runes_b, champ_b, legend_b, bfs_b) = make(&mut gs, deck_b)?;
    rune_rng_b.shuffle(&mut runes_b);
    rng.shuffle(&mut main_a);
    rng.shuffle(&mut main_b);
    let na = runes_a.len() as i64;
    let nb = runes_b.len() as i64;
    gs.players[0] = Player::new(Side::A, Deck { cards: main_a, known_top: Vec::new() }, RuneDeck { runes: runes_a, unseen: Some(na) });
    gs.players[1] = Player::new(Side::B, Deck { cards: main_b, known_top: Vec::new() }, RuneDeck { runes: runes_b, unseen: Some(nb) });
    let starter = match first_player.trim().to_lowercase().as_str() {
        "random" => if rng.choice_index(2) == 0 { Side::A } else { Side::B },
        "a" => Side::A,
        "b" => Side::B,
        _ => Side::A,
    };
    let mut bf_rng = PyRandom::new(((game_seed as i128 * 2654435761) & 0xFFFF_FFFF) as i128);
    // Come `_select_battlefield` di Python: scelta valida = quella, senza toccare bf_rng; altrimenti a caso.
    let mut select = |bfs: &Vec<String>, choice: Option<&str>| -> Option<String> {
        if bfs.is_empty() {
            return None;
        }
        if let Some(c) = choice {
            if let Some(n) = bfs.iter().find(|n| n.as_str() == c) {
                return Some(n.clone());
            }
        }
        Some(bfs[bf_rng.choice_index(bfs.len())].clone())
    };
    let pick_a = select(&bfs_a, bf_a);
    let pick_b = select(&bfs_b, bf_b);
    let mut victory_score = 8;
    for p in [&pick_a, &pick_b] {
        let card = match p {
            Some(n) => Some(instantiate(&mut gs, n)?),
            None => None,
        };
        if let Some(c) = card {
            victory_score += gs
                .spec(c)
                .effects
                .iter()
                .filter(|es| es.effect == "victory_score_plus")
                .map(|es| es.params.get("amount").map(crate::cards::py_int).unwrap_or(1))
                .sum::<i64>();
        }
        gs.battlefields.push(Battlefield::new(card));
    }
    gs.rng = rng;
    gs.turn = 1;
    gs.max_turns = max_turns;
    gs.active = starter;
    gs.victory_score = victory_score;
    gs.champion = [champ_a, champ_b];
    gs.legend = [legend_a, legend_b];
    Ok(Game::new(gs))
}
