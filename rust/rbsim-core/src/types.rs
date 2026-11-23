//! Basic types: sides, domains, card types, object ids.

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Side {
    A,
    B,
}

impl Side {
    pub fn other(self) -> Side {
        match self {
            Side::A => Side::B,
            Side::B => Side::A,
        }
    }
    pub fn idx(self) -> usize {
        match self {
            Side::A => 0,
            Side::B => 1,
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Side::A => "A",
            Side::B => "B",
        }
    }
    pub fn from_str(s: &str) -> Option<Side> {
        match s {
            "A" => Some(Side::A),
            "B" => Some(Side::B),
            _ => None,
        }
    }
    pub const BOTH: [Side; 2] = [Side::A, Side::B];
}

/// py: enums.Domain, in definition order (list(Domain)).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Domain {
    Fury,
    Calm,
    Mind,
    Body,
    Chaos,
    Order,
}

impl Domain {
    pub const ALL: [Domain; 6] = [Domain::Fury, Domain::Calm, Domain::Mind, Domain::Body, Domain::Chaos, Domain::Order];
    pub fn name(self) -> &'static str {
        match self {
            Domain::Fury => "FURY",
            Domain::Calm => "CALM",
            Domain::Mind => "MIND",
            Domain::Body => "BODY",
            Domain::Chaos => "CHAOS",
            Domain::Order => "ORDER",
        }
    }
    pub fn from_py(s: &str) -> Option<Domain> {
        Domain::ALL.iter().copied().find(|d| d.name() == s.to_uppercase())
    }
}

/// py: enums.CardType.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum CardType {
    Unit,
    Gear,
    Spell,
    Rune,
    Legend,
    Champion,
    Battlefield,
}

impl CardType {
    pub fn from_py(s: &str) -> Option<CardType> {
        Some(match s {
            "UNIT" => CardType::Unit,
            "GEAR" => CardType::Gear,
            "SPELL" => CardType::Spell,
            "RUNE" => CardType::Rune,
            "LEGEND" => CardType::Legend,
            "CHAMPION" => CardType::Champion,
            "BATTLEFIELD" => CardType::Battlefield,
            _ => return None,
        })
    }
    pub fn name(self) -> &'static str {
        match self {
            CardType::Unit => "UNIT",
            CardType::Gear => "GEAR",
            CardType::Spell => "SPELL",
            CardType::Rune => "RUNE",
            CardType::Legend => "LEGEND",
            CardType::Champion => "CHAMPION",
            CardType::Battlefield => "BATTLEFIELD",
        }
    }
}

/// The Python class of a card in play (isinstance checks).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CardClass {
    Card,
    Unit,
    Spell,
    Gear,
    Rune,
    Legend,
    Battlefield,
}

impl CardClass {
    pub fn from_py(s: &str) -> CardClass {
        match s {
            "UnitCard" => CardClass::Unit,
            "SpellCard" => CardClass::Spell,
            "GearCard" => CardClass::Gear,
            "RuneCard" => CardClass::Rune,
            "LegendCard" => CardClass::Legend,
            "BattlefieldCard" => CardClass::Battlefield,
            _ => CardClass::Card,
        }
    }
}

macro_rules! id_type {
    ($name:ident) => {
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
        pub struct $name(pub u32);
        impl $name {
            pub fn i(self) -> usize {
                self.0 as usize
            }
        }
    };
}
id_type!(CardId);
id_type!(UnitId);
id_type!(GearId);

/// Errors that stop the engine. `NotPorted`: a branch reachable only with
/// cards or mechanics outside the ported perimeter (identifiable).
#[derive(Clone, Debug, PartialEq)]
pub enum EngineError {
    NotPorted { at: String, what: String },
    /// py: _Ignored — a declared option no longer legal: the instruction isn't followed.
    Ignored(String),
    Agent(String),
    Invalid(String),
    /// What raises an exception in Python (caught by the engine's
    /// `except Exception` around a handler or a declaration).
    Py(String),
}

impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EngineError::NotPorted { at, what } => write!(f, "NotPorted[{at}]: {what}"),
            EngineError::Ignored(s) => write!(f, "Ignored: {s}"),
            EngineError::Agent(s) => write!(f, "Agent: {s}"),
            EngineError::Invalid(s) => write!(f, "Invalid: {s}"),
            EngineError::Py(s) => write!(f, "Py: {s}"),
        }
    }
}

pub type R<T> = Result<T, EngineError>;

#[macro_export]
macro_rules! not_ported {
    ($at:expr, $($arg:tt)*) => {
        return Err($crate::types::EngineError::NotPorted { at: $at.to_string(), what: format!($($arg)*) })
    };
}

impl EngineError {
    /// Caught by Python's `except Exception` (a handler, a declaration):
    /// everything but NotPorted and agent failures.
    pub fn swallowable(&self) -> bool {
        !matches!(self, EngineError::NotPorted { .. } | EngineError::Agent(_))
    }
}
