//! The arena's search agents on the Rust engine (py: HandwrittenAgent,
//! PPOPriorAgent): Rust searches; for the PPO prior, Python's `probs` does the
//! net's forward and softmax on what Rust builds (riftbound/rs/arena_rs.py).

use numpy::{PyArray1, PyArrayMethods, PyReadonlyArray1};
use pyo3::prelude::*;

use rbsim_core::features::{self as F, Descriptor};
use rbsim_core::search::{Lockstep, Prior};
use rbsim_core::types::*;

pub struct PyPrior {
    /// py: probs(x, q, ctx, otype, ocards, ofeats) -> float32 array (softmax over the menu)
    pub probs: Py<PyAny>,
}

impl PyPrior {
    fn chiama(&mut self, x: Vec<f32>, q: i64, ctx: [f32; F::F_CTX], descs: &[Descriptor])
              -> R<(Vec<f32>, Option<f32>)> {
        let n = descs.len();
        let otype: Vec<i64> = descs.iter().map(|d| d.type_).collect();
        let ocards: Vec<i64> = descs.iter().flat_map(|d| d.cards).collect();
        let ofeats: Vec<f32> = descs.iter().flat_map(|d| d.feats.iter().copied()).collect();
        Python::attach(|py| -> PyResult<(Vec<f32>, Option<f32>)> {
            let x = PyArray1::from_vec(py, x);
            let c = PyArray1::from_vec(py, ctx.to_vec());
            let otype = PyArray1::from_vec(py, otype);
            let ocards = PyArray1::from_vec(py, ocards).reshape([n, 3])?;
            let ofeats = PyArray1::from_vec(py, ofeats).reshape([n, F::F_OPT])?;
            let out = self.probs.bind(py).call1((x, q, c, otype, ocards, ofeats))?;
            // Two formats: the softmax array alone (make_probs) or (array, value) (make_probs_valore).
            if let Ok((arr, v)) = out.extract::<(PyReadonlyArray1<f32>, f64)>() {
                return Ok((arr.as_slice()?.to_vec(), Some(v as f32)));
            }
            let arr: PyReadonlyArray1<f32> = out.extract()?;
            Ok((arr.as_slice()?.to_vec(), None))
        })
        .map_err(|e| EngineError::Py(format!("prior: {e}")))
    }
}

impl Prior for PyPrior {
    /// py: probs(x, q, ctx, otype, ocards, ofeats) -> float32 array (softmax over the menu), or the pair
    /// (array, value of the net from the deciding seat).
    fn probs(&mut self, x: Vec<f32>, q: i64, ctx: [f32; F::F_CTX], descs: &[Descriptor]) -> R<Vec<f32>> {
        Ok(self.chiama(x, q, ctx, descs)?.0)
    }
    fn eval(&mut self, x: Vec<f32>, q: i64, ctx: [f32; F::F_CTX], descs: &[Descriptor]) -> R<(Vec<f32>, Option<f32>)> {
        self.chiama(x, q, ctx, descs)
    }
}

/// The step with the Python copy (riftbound/rs/arena_mista.py): `before(info_json)`
/// -> the count to repeat, or -1 to lead; `after(info_json, n)` after a led search.
pub struct PyLockstep {
    pub before: Py<PyAny>,
    pub after: Py<PyAny>,
}

impl Lockstep for PyLockstep {
    fn before(&mut self, info: &serde_json::Value) -> R<Option<usize>> {
        let s = info.to_string();
        let n = Python::attach(|py| -> PyResult<i64> { self.before.bind(py).call1((s,))?.extract::<i64>() })
            .map_err(|e| EngineError::Agent(format!("lockstep: {e}")))?;
        Ok(if n < 0 { None } else { Some(n as usize) })
    }
    fn after(&mut self, info: &serde_json::Value, n: usize) -> R<()> {
        let s = info.to_string();
        Python::attach(|py| -> PyResult<()> { self.after.bind(py).call1((s, n))?; Ok(()) })
            .map_err(|e| EngineError::Agent(format!("lockstep: {e}")))
    }
}
