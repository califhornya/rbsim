//! rbsim-core: the Riftbound engine ported from the Python reference
//! (riftbound/core at 6427b90). See rust/PORTING_NOTE.md.
#![allow(clippy::too_many_arguments, clippy::type_complexity)]

pub mod types;
pub mod rng;
pub mod pydict;
pub mod registry;
pub mod model;
pub mod cards;
pub mod agent;
pub mod game;
