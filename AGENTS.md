# Working in gossil-libsql

This repository preserves the complete published libsql 0.10.0 crate and a
bounded Rust wrapper correction for Gossil's `core` configuration.
Read `ROW-CORRECTION.md` before changing the correction.

- Preserve the authenticated baseline and upstream notices.
- Keep the retrieval correction in `src/local/rows.rs` and `src/local/impls.rs`.
- The four explicit lifetime annotations in the statement surfaces preserve inferred types.
- Preserve public Row signatures, error variants and engine dependencies.
- Use Just through jlog for checks. `just check` is the core correction contract.
- Companion lint uses an explicit upstream-baseline comparison after type checking.
  Admit only exact message/code matches at unchanged authenticated source origins.
  Reject new diagnostics, source drift, compiler errors and operational failures.
- Preserve raw strict failures and all admitted findings for Rust 1.95.0 and 1.100.0.
  This contract changes no Gossil gate and permits no lint allow attributes.
- Compare authored line coverage against the immutable baseline, with no exclusions.
- Distinguish inherited source diagnostics, source review and executed checks.
- Use independent Sol6.1 source, test and prose review before publication.
- Gossil issue 36 and its native Gest parent track this companion work.

## Recommendations

Prefer the smallest wrapper correction over an engine migration.
Next, qualify its authored diff and replay Gossil's public Row controls at the
exact dependency revision.
