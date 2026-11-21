# libSQL API for Rust

[![Crates.io][crates-badge]][crates-url]
[![MIT licensed][mit-badge]][mit-url]

[crates-badge]: https://img.shields.io/crates/v/libsql.svg
[crates-url]: https://crates.io/crates/libsql
[mit-badge]: https://img.shields.io/badge/license-MIT-blue.svg
[mit-url]: https://github.com/libsql/libsql/blob/main/LICENSE.md

This repository contains the libSQL API for Rust.

## Developing

See [DEVELOPING.md](DEVELOPING.md) for more information.

## License

This project is licensed under the [MIT license].

### Contribution

Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in libSQL by you, shall be licensed as MIT, without any additional
terms or conditions.

[MIT license]: https://github.com/libsql/libsql/blob/main/LICENSE.md

## Gossil maintenance contract

This fork pins the published libsql 0.10.0 Rust wrapper for
[Gossil issue 36](https://github.com/rahuldave/gossil/issues/36).
The complete published baseline and notices remain available at commit
`243281163e4a39303322385d5f9537736277026e`.
See [the correction guide](ROW-CORRECTION.md) for source and provider inputs.

`just lint` compares the current core library and test harness with that
baseline under the same compiler, features and existing Gossil provider.
Type checking must pass. Every current diagnostic must retain the exact
message, code and unchanged baseline token origin. New diagnostics, source
drift, compiler errors and operational failures fail the check.

The comparison retains raw ordinary and strict Clippy output, exit statuses
and admitted findings in `target/lint-comparison/`. It does not claim that
inherited strict diagnostics pass. CI runs the contract under Rust 1.95.0 and
1.100.0 and uploads the evidence. There are no lint allow attributes or
coverage exclusions. Gossil's own strict checks remain unchanged.

Writing follows nossaifd guidance, including Rosalind Reid's communication
principles, Shreya Shankar's plain-writing guidance and Oskar Austegard's
revision method.

## Recommendations

Prefer the full reviewed Git revision over a moving branch.
Run the baseline comparison and full changed-line coverage before changing
the dependency pin.
