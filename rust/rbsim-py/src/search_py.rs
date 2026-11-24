//! The arena's search agents on the Rust engine (py: HandwrittenAgent,
//! PPOPriorAgent): Rust searches; for the PPO prior, Python's `probs` does the
//! net's forward and softmax on what Rust builds (riftbound/rs/arena_rs.py).

use numpy::{PyArray1, PyArrayMethods, PyReadonlyArray1};
use pyo3::prelude::*;

use rbsim_core::features::{self as F, Descriptor};
use rbsim_core::search::Prior;
use rbsim_core::types::*;

pub struct PyPrior {
    /// py: probs(x, q, ctx, otype, ocards, ofeats) -> float32 array (softmax over the menu)
    pub probs: Py<PyAny>,
}

impl Prior for PyPrior {
    fn probs(&mut self, x: Vec<f32>, q: i64, ctx: [f32; F::F_CTX], descs: &[Descriptor]) -> R<Vec<f32>> {
        let n = descs.len();
        let otype: Vec<i64> = descs.iter().map(|d| d.type_).collect();
        let ocards: Vec<i64> = descs.iter().flat_map(|d| d.cards).collect();
        let ofeats: Vec<f32> = descs.iter().flat_map(|d| d.feats.iter().copied()).collect();
        Python::attach(|py| -> PyResult<Vec<f32>> {
            let x = PyArray1::from_vec(py, x);
            let c = PyArray1::from_vec(py, ctx.to_vec());
            let otype = PyArray1::from_vec(py, otype);
            let ocards = PyArray1::from_vec(py, ocards).reshape([n, 3])?;
            let ofeats = PyArray1::from_vec(py, ofeats).reshape([n, F::F_OPT])?;
            let out = self.probs.bind(py).call1((x, q, c, otype, ocards, ofeats))?;
            let arr: PyReadonlyArray1<f32> = out.extract()?;
            Ok(arr.as_slice()?.to_vec())
        })
        .map_err(|e| EngineError::Py(format!("prior: {e}")))
    }
}
