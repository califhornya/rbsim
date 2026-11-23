//! A small insertion-ordered map with Python dict semantics (get / set /
//! pop / setdefault, iteration in insertion order), for the engine's dicts
//! whose order matters (power pools, rune pools) or whose dump must list
//! only the keys present.

#[derive(Clone, Debug, PartialEq)]
pub struct PyDict<K: PartialEq + Clone, V: Clone> {
    items: Vec<(K, V)>,
}

impl<K: PartialEq + Clone, V: Clone> Default for PyDict<K, V> {
    fn default() -> Self {
        PyDict { items: Vec::new() }
    }
}

impl<K: PartialEq + Clone, V: Clone> PyDict<K, V> {
    pub fn new() -> Self {
        Self::default()
    }
    pub fn from_items(items: Vec<(K, V)>) -> Self {
        PyDict { items }
    }
    pub fn get(&self, k: &K) -> Option<&V> {
        self.items.iter().find(|(kk, _)| kk == k).map(|(_, v)| v)
    }
    pub fn get_mut(&mut self, k: &K) -> Option<&mut V> {
        self.items.iter_mut().find(|(kk, _)| kk == k).map(|(_, v)| v)
    }
    pub fn get_or(&self, k: &K, d: V) -> V {
        self.get(k).cloned().unwrap_or(d)
    }
    pub fn contains(&self, k: &K) -> bool {
        self.items.iter().any(|(kk, _)| kk == k)
    }
    /// d[k] = v (keeps the position of an existing key).
    pub fn set(&mut self, k: K, v: V) {
        if let Some(slot) = self.get_mut(&k) {
            *slot = v;
        } else {
            self.items.push((k, v));
        }
    }
    pub fn pop(&mut self, k: &K) -> Option<V> {
        let i = self.items.iter().position(|(kk, _)| kk == k)?;
        Some(self.items.remove(i).1)
    }
    pub fn setdefault(&mut self, k: K, d: V) -> &mut V {
        let i = match self.items.iter().position(|(kk, _)| *kk == k) {
            Some(i) => i,
            None => {
                self.items.push((k, d));
                self.items.len() - 1
            }
        };
        &mut self.items[i].1
    }
    pub fn clear(&mut self) {
        self.items.clear();
    }
    pub fn len(&self) -> usize {
        self.items.len()
    }
    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }
    pub fn iter(&self) -> impl Iterator<Item = &(K, V)> {
        self.items.iter()
    }
    pub fn iter_mut(&mut self) -> impl Iterator<Item = &mut (K, V)> {
        self.items.iter_mut()
    }
    pub fn keys(&self) -> impl Iterator<Item = &K> {
        self.items.iter().map(|(k, _)| k)
    }
    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.items.iter().map(|(_, v)| v)
    }
    pub fn items(&self) -> &Vec<(K, V)> {
        &self.items
    }
    pub fn items_mut(&mut self) -> &mut Vec<(K, V)> {
        &mut self.items
    }
}
