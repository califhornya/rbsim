//! rbsim-core: the Riftbound engine ported from the Python reference
//! (riftbound/core at 6427b90). See rust/PORTING_NOTE.md.
#![allow(clippy::too_many_arguments, clippy::type_complexity)]
#![recursion_limit = "512"]

pub mod types;
pub mod rng;
pub mod pydict;
pub mod registry;
pub mod model;
pub mod cards;
pub mod agent;
pub mod game;
pub mod lp_phases;
pub mod lp_triggers;
pub mod lp_passives;
pub mod lp_conditions;
pub mod lp_costs;
pub mod lp_costs2;
pub mod lp_hidden;
pub mod lp_pay;
pub mod lp_play;
pub mod lp_dest;
pub mod lp_move;
pub mod lp_action;
pub mod lp_abilities;
pub mod lp_abilities2;
pub mod lp_deaths;
pub mod lp_misc;
pub mod lp_rules;
pub mod lp_chain;
pub mod lp_showdown;
pub mod lp_main;
pub mod effects_core;
pub mod effects;
pub mod legality;
pub mod dump;
pub mod setup;
pub mod trace;
pub mod import;
pub mod agents;
pub mod obs;
pub mod features;
pub mod search;
