use std::{
    collections::HashMap,
    hash::Hash,
    sync::{LazyLock, OnceLock, RwLock, atomic::AtomicBool},
};

use crate::deserialize::value;
use deserialize::results;
use pyo3::{
    ffi::PyDictProxy_New,
    prelude::*,
    sync::OnceLockExt,
    types::{PyDict, PyMappingProxy},
};
use tokio::runtime::Runtime;

mod batch;
mod cluster;
mod deserialize;
mod enums;
mod errors;
mod execution_profile;
mod routing;
mod serialize;
mod session;
mod session_builder;
mod statement;
mod types;
mod utils;

use crate::utils::add_submodule;

pub static RUNTIME: LazyLock<Runtime> = LazyLock::new(|| Runtime::new().unwrap());

struct CacheInner<K, V>
where
    K: std::cmp::Eq + Hash + Sync + Send,
    V: Clone + Sync + Send,
{
    hmap: HashMap<K, V>,
}

pub struct Cache<K, V>
where
    K: std::cmp::Eq + Hash + Clone + Sync + Send,
    V: Clone + Sync + Send,
{
    inner: RwLock<CacheInner<K, V>>,
    python_view: OnceLock<Py<PyDict>>,
}

impl<K, V> Cache<K, V>
where
    K: std::cmp::Eq + Hash + Clone + Sync + Send,
    V: Clone + Sync + Send,
{
    pub fn new() -> Self {
        Self {
            inner: RwLock::new(CacheInner {
                hmap: HashMap::new(),
            }),
            python_view: OnceLock::new(),
        }
    }

    pub fn get_or_init<F>(&self, key: &K, f: F) -> Option<V>
    where
        F: FnOnce() -> Option<V> + Sync + Send,
    {
        // Try to read the entry
        Python::attach(|py| {
            Python::detach(py, || {
                {
                    let read_guard = self.inner.read().unwrap();
                    if let Some(value) = read_guard.hmap.get(key) {
                        return Some(value.clone());
                    }
                    // No value found in cache.
                    // Python_view couldn't have been initialized while holding the read guard
                    if self.python_view.get().is_some() {
                        // No need to acquire write lock, cache is fully initialized with data.
                        return None;
                    }
                } // read guard

                // If one of the following was true we would have returned:
                // Key was found in cache and cloned value was returned.
                // Key will never be inserted into the cache as it doesn't exist in Rust and None was returned.
                //
                // We can't be sure Rust doesn't know about the key.
                // Acquire the write lock, check if already initialized or use provided init closure and compute it.
                let mut write_guard = self.inner.write().unwrap();
                if write_guard.hmap.contains_key(key) {
                    return write_guard.hmap.get(key).cloned();
                }
                if let Some(value) = f() {
                    write_guard.hmap.insert(key.clone(), value.clone());
                    return Some(value);
                }
                None
            })
        })
    }

    pub fn get_or_init_python_mapping<'py, F>(
        &self,
        py: Python<'py>,
        f: F,
    ) -> Bound<'py, PyMappingProxy>
    where
        F: FnOnce() -> Box<dyn Iterator<Item = (K, V)>>,
        K: Clone + Eq + Hash + IntoPyObject<'py>,
        V: Clone + IntoPyObject<'py>,
    {
        let py_dict_ref = self.python_view.get_or_init_py_attached(py, || {
            let dict = PyDict::new(py);
            let mut write_guard = self.inner.write().unwrap();
            for (k, v) in &mut f() {
                let cached_value = {
                    if write_guard.hmap.contains_key(&k) {
                        write_guard.hmap.get(&k).cloned().unwrap()
                    } else {
                        write_guard.hmap.insert(k.clone(), v.clone());
                        v
                    }
                };
                dict.set_item(k, cached_value).unwrap();
            }
            dict.unbind()
        });
        PyMappingProxy::new(py, py_dict_ref.bind(py).as_mapping())
    }
}

/// A Python module implemented in Rust.
#[pymodule]
#[pyo3(name = "_rust")]
fn scylla(py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    add_submodule(
        py,
        module,
        "session_builder",
        session_builder::session_builder,
    )?;
    add_submodule(py, module, "session", session::session)?;
    add_submodule(py, module, "results", results::results)?;
    add_submodule(py, module, "statement", statement::statement)?;
    add_submodule(py, module, "enums", enums::enums)?;
    add_submodule(py, module, "errors", errors::errors)?;
    add_submodule(
        py,
        module,
        "execution_profile",
        execution_profile::execution_profile,
    )?;
    add_submodule(py, module, "types", types::types)?;
    add_submodule(py, module, "value", value::value)?;
    add_submodule(py, module, "batch", batch::batch)?;
    add_submodule(py, module, "cluster", cluster::cluster)?;
    add_submodule(py, module, "routing", routing::routing)?;
    Ok(())
}
