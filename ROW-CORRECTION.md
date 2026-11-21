# Exact TEXT retrieval for Gossil

This repository corrects the local Rust wrapper in libsql 0.10.0.
The published wrapper truncates TEXT at an embedded NUL and can panic on
malformed UTF-8. The correction preserves complete valid text and returns
existing errors for invalid text and column indices.

## Source and scope

Commit `243281163e4a39303322385d5f9537736277026e` is the complete published
crate, unchanged, plus its MIT license and source provenance.
`SOURCE-PROVENANCE.json` records all 70 archive files and the license from
upstream commit `d8bc862d20bedc72945a1da27c8b7045414c0261`.
The archive digest is the crates.io checksum recorded by Gossil's original
lockfile. The baseline retains upstream formatting and notices.

The retrieval correction changes `src/local/rows.rs` and
`src/local/impls.rs`. Four mechanical `Column<'_>` annotations in the
statement surfaces make existing inferred lifetimes explicit. They change no
types or ownership. Rustfmt also normalizes indentation in the existing
`column_names` body. The wrapper copies owned values immediately from the
existing length-aware view. TEXT uses strict UTF-8 decoding.

Public `get_str` accepts only TEXT. Invalid TEXT and nontext `get_str` return `InvalidColumnType`;
out-of-range indices return `InvalidColumnIndex`. Column names return `None`
for those indices. Public Row signatures and engine dependencies stay unchanged.
The generic wrong-type `get<T>` conversions retain their upstream behavior.

The owned-value approach follows
[upstream PR 2288](https://github.com/tursodatabase/libsql/pull/2288), at
`d76abc357cb10e6b5639fc5f6ad231f91c94384b`. This correction also covers
`get_str` and column bounds. It adds no raw borrowed API.

## Qualification

`just source-check` checks every baseline file and the bounded production
changes. The upstream README prefix remains exact; a maintenance appendix
documents this fork. To compare the published archive too, run:

```sh
python3 scripts/verify-source.py --archive /path/to/libsql-0.10.0.crate
```

Set `GOSSIL_LIBSQL_FFI_PATH` to the existing Gossil `vendor/libsql-ffi`
directory. The recipes verify that provider through its own frozen source
checker and apply a standard Cargo configuration override. The qualification
lock changes only that provider from registry to path source. CI checks out
the exact accepted Gossil commit for this input.

After normal dependency acquisition with `just setup`, `just check` exercises
the core configuration used by Gossil. It checks source identity, formatting,
the upstream-baseline lint comparison, compilation and changed-line coverage.

Type checking must pass. The lint comparison rejects every new diagnostic and
requires each retained message and code to map to unchanged baseline tokens.
Unsupported nested comments and non-ASCII token forms fail closed.
It preserves raw strict failures and rejects non-lint or compiler failures.
These rules apply under both compiler versions. Gossil's strict gate stays
unchanged.

Coverage compares the correction
to the immutable baseline. A separate guard rejects a corrected file missing
from the report. Each test target has its own new profile nonce. Only those
fresh inputs and the two executed binaries enter the LLVM report; prior
profiles and caches remain untouched. There are no coverage exclusions.

The GitHub workflow runs the same core
contract on pull requests and pushes to `main` with Rust 1.95.0. It runs
the Rust 1.100.0 lint check separately.

The public Row controls cover NUL positions, Unicode, malformed UTF-8, storage
types, invalid indices, recovery and owned values after rows are dropped.
An internal unit control exercises the private generic retrieval bounds.
These checks qualify the authored core correction; they do not establish
remote, replication, encryption or cross-platform compatibility.

Gossil keeps its registry `libsql-sys` and existing `libsql-ffi` patch.
Its locked dependency must name the full reviewed commit of this repository.
[Gossil issue 36](https://github.com/rahuldave/gossil/issues/36) tracks final
integration, the independently owned Gest and checkout-validation replays,
and the 0.4.1 release. Focused tests with a temporary local patch are separate
from that final qualification.

Writing follows nossaifd guidance, including Rosalind Reid's communication
principles, Shreya Shankar's plain-writing guidance and Oskar Austegard's
revision method.

## Recommendations

Prefer this pinned wrapper correction while the fix remains unreleased
upstream. Next, qualify the exact authored commit, pin it in Gossil and replay
the integration controls before release.
