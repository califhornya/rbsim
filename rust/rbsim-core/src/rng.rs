//! MT19937 compatibile con `random.Random` di CPython (seme intero,
//! `getrandbits`, `_randbelow`, `randrange`, `shuffle`, `choice`, `random`).
//! Lo stesso seme dà la stessa sequenza nei due linguaggi; lo stato
//! (624 parole + indice) si confronta con `digest_words`.

const N: usize = 624;
const M: usize = 397;
const MATRIX_A: u32 = 0x9908_b0df;
const UPPER: u32 = 0x8000_0000;
const LOWER: u32 = 0x7fff_ffff;

#[derive(Clone, Debug)]
pub struct PyRandom {
    mt: [u32; N],
    mti: usize,
    /// When set (tracing the real game), every _randbelow(n) -> r.
    pub log: Option<Vec<(u64, u64)>>,
}

impl PyRandom {
    /// `random.Random(seed)` with a non-negative or negative int seed (abs value,
    /// as CPython does), split in 32-bit words, least significant first.
    pub fn new(seed: i128) -> Self {
        let mut n = seed.unsigned_abs();
        let mut key = Vec::new();
        if n == 0 {
            key.push(0u32);
        }
        while n > 0 {
            key.push((n & 0xffff_ffff) as u32);
            n >>= 32;
        }
        let mut r = PyRandom { mt: [0; N], mti: N + 1, log: None };
        r.init_by_array(&key);
        r
    }

    fn init_genrand(&mut self, s: u32) {
        self.mt[0] = s;
        for i in 1..N {
            let prev = self.mt[i - 1];
            self.mt[i] = 1_812_433_253u32.wrapping_mul(prev ^ (prev >> 30)).wrapping_add(i as u32);
        }
        self.mti = N;
    }

    fn init_by_array(&mut self, key: &[u32]) {
        self.init_genrand(19_650_218);
        let (mut i, mut j) = (1usize, 0usize);
        let len = key.len();
        let mut k = if N > len { N } else { len };
        while k > 0 {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (prev ^ (prev >> 30)).wrapping_mul(1_664_525))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            if j >= len {
                j = 0;
            }
            k -= 1;
        }
        k = N - 1;
        while k > 0 {
            let prev = self.mt[i - 1];
            self.mt[i] = (self.mt[i] ^ (prev ^ (prev >> 30)).wrapping_mul(1_566_083_941)).wrapping_sub(i as u32);
            i += 1;
            if i >= N {
                self.mt[0] = self.mt[N - 1];
                i = 1;
            }
            k -= 1;
        }
        self.mt[0] = 0x8000_0000;
    }

    pub fn genrand_u32(&mut self) -> u32 {
        if self.mti >= N {
            for kk in 0..N {
                let y = (self.mt[kk] & UPPER) | (self.mt[(kk + 1) % N] & LOWER);
                let mut v = self.mt[(kk + M) % N] ^ (y >> 1);
                if y & 1 != 0 {
                    v ^= MATRIX_A;
                }
                self.mt[kk] = v;
            }
            self.mti = 0;
        }
        let mut y = self.mt[self.mti];
        self.mti += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c_5680;
        y ^= (y << 15) & 0xefc6_0000;
        y ^= y >> 18;
        y
    }

    /// `getrandbits(k)`, 0 < k <= 64.
    pub fn getrandbits(&mut self, k: u32) -> u64 {
        assert!(k > 0 && k <= 64);
        if k <= 32 {
            return (self.genrand_u32() >> (32 - k)) as u64;
        }
        // Words from the least significant; the last one shifted.
        let mut out: u64 = 0;
        let mut left = k;
        let mut shift = 0;
        while left > 0 {
            let mut r = self.genrand_u32() as u64;
            if left < 32 {
                r >>= 32 - left;
            }
            out |= r << shift;
            shift += 32;
            left = left.saturating_sub(32);
        }
        out
    }

    /// `_randbelow(n)` (with getrandbits), n > 0.
    pub fn randbelow(&mut self, n: u64) -> u64 {
        if n == 0 {
            return 0;
        }
        let k = 64 - n.leading_zeros();
        let mut r = self.getrandbits(k);
        while r >= n {
            r = self.getrandbits(k);
        }
        if let Some(l) = self.log.as_mut() {
            l.push((n, r));
        }
        r
    }

    /// `randrange(stop)`.
    pub fn randrange(&mut self, stop: u64) -> u64 {
        self.randbelow(stop)
    }

    pub fn shuffle<T>(&mut self, x: &mut [T]) {
        if x.len() < 2 {
            return;
        }
        for i in (1..x.len()).rev() {
            let j = self.randbelow((i + 1) as u64) as usize;
            x.swap(i, j);
        }
    }

    pub fn choice_index(&mut self, len: usize) -> usize {
        self.randbelow(len as u64) as usize
    }

    pub fn random(&mut self) -> f64 {
        let a = (self.genrand_u32() >> 5) as f64;
        let b = (self.genrand_u32() >> 6) as f64;
        (a * 67_108_864.0 + b) / 9_007_199_254_740_992.0
    }

    /// canon.rng_digest: sha256 of json.dumps(getstate()[1])[:16].
    pub fn digest(&self) -> String {
        use sha2::{Digest, Sha256};
        let words = self.state_words();
        let text = format!("[{}]", words.iter().map(|w| w.to_string()).collect::<Vec<_>>().join(", "));
        let h = Sha256::digest(text.as_bytes());
        hex::encode(h)[..16].to_string()
    }

    /// The state as CPython's getstate()[1]: 624 words then the index.
    pub fn state_words(&self) -> Vec<u64> {
        let mut v: Vec<u64> = self.mt.iter().map(|&w| w as u64).collect();
        v.push(self.mti as u64);
        v
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_cpython() {
        let mut r = PyRandom::new(1_000_001);
        assert_eq!(
            [r.getrandbits(32), r.getrandbits(32), r.getrandbits(32)],
            [787295530, 1482427753, 2500419752]
        );
        let mut r = PyRandom::new(12345678901234567890);
        assert_eq!([r.getrandbits(32), r.getrandbits(32)], [2199100970, 3695432519]);
        let mut r = PyRandom::new(0);
        assert_eq!([r.getrandbits(32), r.getrandbits(32)], [3626764237, 1654615998]);
        let mut r = PyRandom::new(7);
        let mut x: Vec<u32> = (0..10).collect();
        r.shuffle(&mut x);
        assert_eq!(x, vec![8, 3, 1, 4, 7, 0, 9, 6, 2, 5]);
        assert_eq!(r.randrange(1 << 30), 461060838);
        assert_eq!(r.choice_index(3), 0);
        assert_eq!(r.random(), 0.08594723368917168);
    }
}
