# Qualification of the authored core-only Row correction against the published baseline.
set positional-arguments
set shell := ["jlog", "sh", "-cu"]
export JLOG_RUN := env("JLOG_RUN", uuid())
export CARGO_LLVM_COV_TARGET_DIR := env("CARGO_LLVM_COV_TARGET_DIR", justfile_directory() / "target/llvm-cov-target")

baseline := "243281163e4a39303322385d5f9537736277026e"
ffi_path := env("GOSSIL_LIBSQL_FFI_PATH", "")
ffi_config := 'patch.crates-io.libsql-ffi.path="' + ffi_path + '"'

# Authenticate the exact existing Gossil provider before using its Cargo override.
ffi-check:
    test -n {{quote(ffi_path)}}
    jlog run python3 scripts/verify-source.py --ffi-root {{quote(ffi_path)}}


# Authenticate the complete baseline and restrict the production correction scope.
source-check:
    jlog run python3 scripts/verify-source.py
    jlog run python3 -m unittest discover -s tests -p test_source_verifier.py
    jlog run python3 -m unittest discover -s tests -p test_baseline_lint.py
    jlog run python3 -m unittest discover -s tests -p test_fresh_coverage.py

# Acquire the dependencies through Cargo; offline checks follow acquisition.
setup: ffi-check
    jlog run cargo fetch --locked --config {{quote(ffi_config)}}

# Format the corrected Rust files and focused public controls.
fmt:
    jlog run rustfmt --edition 2021 src/local/rows.rs src/local/impls.rs src/local/statement.rs src/statement.rs tests/row_text_regression.rs

# Check the same corrected files without rewriting untouched upstream files.
fmt-check:
    jlog run rustfmt --edition 2021 --check src/local/rows.rs src/local/impls.rs src/local/statement.rs src/statement.rs tests/row_text_regression.rs

# Compile the supported core-only correction and its regression targets.
typecheck: ffi-check
    jlog run cargo check --config {{quote(ffi_config)}} --locked --no-default-features --features core --lib --test row_text_regression

# Run the Rust linter on the same supported correction targets.
lint: ffi-check typecheck
    jlog run python3 scripts/compare-baseline-lint.py

# Run upstream core unit tests and exact public Row controls with coverage.
test: ffi-check
    mkdir -p target
    jlog run python3 scripts/fresh-coverage.py --config {{quote(ffi_config)}} --locked --no-default-features --features core

# Require every changed executable production line to appear and execute.
coverage-check: test
    jlog run uv run --no-project --quiet --python '>=3.11' --with diff-cover==11.0.1 diff-cover target/row-fix.lcov --compare-branch {{baseline}} --fail-under 100
    jlog run python3 scripts/verify-source.py --coverage target/row-fix.lcov

# Check only the authored patch for whitespace; baseline bytes stay immutable.
diff-check:
    jlog run git diff --check {{baseline}}

# Run the bounded correction contract; broader upstream features are not qualified.
check: ffi-check source-check fmt-check lint typecheck coverage-check diff-check

# Preserve raw strict library diagnostics for an explicit baseline comparison.
lint-capture MANIFEST: ffi-check
    jlog run cargo clippy --manifest-path {{quote(MANIFEST)}} --config {{quote(ffi_config)}} --locked --no-default-features --features core --lib --message-format=json -- -D warnings

# Inspect all selected candidate target diagnostics without suppressing any lint.
lint-diagnostics: ffi-check
    jlog run cargo clippy --config {{quote(ffi_config)}} --locked --no-default-features --features core --lib --test row_text_regression --message-format=json
