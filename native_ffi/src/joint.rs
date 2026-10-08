//! Joint fit: explain every observed harmonic peak with all candidate notes at
//! once, instead of judging each note alone.
//!
//! Judged alone, a note's semitone neighbour can look present by borrowing
//! peaks that belong to chord mates (F2's harmonics sit on C3's, G2's and C4's).
//! Fitted jointly, a template must explain its WHOLE comb: borrowed peaks are
//! already explained by the mates, and the template's empty slots argue against
//! it, so an absent neighbour fits to ~0 while a played note keeps its energy.

/// Non-negative loudness per atom such that, at every slot, the weighted sum
/// of the atoms covering it approximates the observed magnitude.
///
/// `observed[s]` = magnitude at slot s; `atoms[a]` = (slot, weight) pairs:
/// the shape of atom a (weight 1 everywhere = a flat comb; a learned note
/// template = how strong each harmonic of that note really is). Minimises the
/// KL divergence (the usual choice for magnitude spectra) with multiplicative
/// updates, which keep every loudness non-negative and converge monotonically.
pub fn fit(observed: &[f32], atoms: &[Vec<(usize, f32)>], iterations: usize) -> Vec<f32> {
    const EPS: f32 = 1e-9;
    // Start each atom at its weighted mean level, shared among overlapping atoms.
    let mut cover = vec![0.0f32; observed.len()];
    for atom in atoms {
        for &(s, w) in atom {
            cover[s] += w;
        }
    }
    let mut h: Vec<f32> = atoms
        .iter()
        .map(|atom| {
            let total: f32 = atom.iter().map(|&(_, w)| w).sum();
            if total <= 0.0 {
                return 0.0;
            }
            atom.iter().map(|&(s, w)| w * observed[s] / cover[s].max(EPS)).sum::<f32>() / total
        })
        .collect();

    let mut model = vec![0.0f32; observed.len()];
    for _ in 0..iterations {
        model.iter_mut().for_each(|m| *m = 0.0);
        for (atom, &ha) in atoms.iter().zip(&h) {
            for &(s, w) in atom {
                model[s] += w * ha;
            }
        }
        for (atom, ha) in atoms.iter().zip(h.iter_mut()) {
            let total: f32 = atom.iter().map(|&(_, w)| w).sum();
            if total <= 0.0 || *ha == 0.0 {
                continue;
            }
            let ratio: f32 = atom.iter().map(|&(s, w)| w * observed[s] / (model[s] + EPS)).sum();
            *ha *= ratio / total;
        }
    }
    h
}

#[cfg(test)]
mod tests {
    use super::*;

    const ITER: usize = 200;

    /// Atom covering `slots` with weight 1 each.
    fn flat(slots: &[usize]) -> Vec<(usize, f32)> {
        slots.iter().map(|&s| (s, 1.0)).collect()
    }

    #[test]
    fn test_weighted_atom_recovers_its_level_from_its_shape() {
        // A note whose harmonics fall off 1, 0.5, 0.25, sounding at level 2.
        let shape = [1.0, 0.5, 0.25];
        let observed: Vec<f32> = shape.iter().map(|w| 2.0 * w).collect();
        let h = fit(&observed, &[vec![(0, 1.0), (1, 0.5), (2, 0.25)]], ITER);
        assert!((h[0] - 2.0).abs() < 1e-3, "{h:?}");
    }

    #[test]
    fn test_octave_above_fits_to_zero_when_only_the_lower_note_sounds() {
        // Lower note harmonics k=1..4 at slots 0..3 with a known shape; the
        // octave above has its k=1,2 exactly on slots 1 and 3 (all shared).
        let lower = vec![(0, 1.0), (1, 0.6), (2, 0.4), (3, 0.3)];
        let upper = vec![(1, 1.0), (3, 0.5)];
        let only_lower = [1.0, 0.6, 0.4, 0.3];
        let h = fit(&only_lower, &[lower.clone(), upper.clone()], ITER);
        assert!((h[0] - 1.0).abs() < 0.05 && h[1] < 0.05, "upper octave invented: {h:?}");
        // Both sounding: the excess on the shared slots is the upper note's.
        let both = [1.0, 0.6 + 0.8, 0.4, 0.3 + 0.4];
        let h = fit(&both, &[lower, upper], ITER);
        assert!((h[0] - 1.0).abs() < 0.05 && (h[1] - 0.8).abs() < 0.05, "upper octave lost: {h:?}");
    }

    #[test]
    fn test_single_atom_recovers_its_level() {
        let h = fit(&[2.0, 2.0, 2.0], &[flat(&[0, 1, 2])], ITER);
        assert!((h[0] - 2.0).abs() < 1e-3, "{h:?}");
    }

    #[test]
    fn test_atom_whose_comb_is_half_empty_fits_to_nearly_zero() {
        // Peaks only at slots 0-3 (the played note). The rival shares slots 2-3
        // (coincident harmonics) but its own slots 4-5 are empty.
        let observed = [1.0, 1.0, 1.0, 1.0, 0.0, 0.0];
        let h = fit(&observed, &[flat(&[0, 1, 2, 3]), flat(&[2, 3, 4, 5])], ITER);
        assert!(h[0] > 0.95, "played note lost energy: {h:?}");
        assert!(h[1] < 0.05, "rival kept borrowed energy: {h:?}");
    }

    #[test]
    fn test_chord_mates_explain_the_peaks_a_rival_would_borrow() {
        // Slots 0-1: target only; 2-3: mate only; 4-5: shared by target's
        // rival (with the mate) plus 6 empty rival-only slot.
        let observed = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0];
        let atoms = [flat(&[0, 1]), flat(&[2, 3, 4, 5]), flat(&[4, 5, 6])];
        let h = fit(&observed, &atoms, ITER);
        assert!(h[0] > 0.95 && h[1] > 0.95, "{h:?}");
        assert!(h[2] < 0.05, "rival credited with the mate's energy: {h:?}");
    }

    #[test]
    fn test_identical_atoms_share_the_energy() {
        let h = fit(&[3.0, 3.0], &[flat(&[0, 1]), flat(&[0, 1])], ITER);
        assert!((h[0] + h[1] - 3.0).abs() < 1e-3, "{h:?}");
    }

    #[test]
    fn test_silence_gives_zeros_not_nan() {
        let h = fit(&[0.0, 0.0, 0.0], &[flat(&[0, 1]), flat(&[1, 2]), vec![]], ITER);
        assert!(h.iter().all(|&x| x == 0.0), "{h:?}");
    }
}
