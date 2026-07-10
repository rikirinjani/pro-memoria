# Contributing to Pro Memoria

## Ways to contribute

- **Bug reports & feature requests** — open a GitHub issue
- **Code changes** — fork, branch, PR to `master`
- **Paper feedback** — issues or PRs against `paper/pro-memoria.md`
- **Benchmark additions** — new traces, new formats, new scenarios welcome

## Guidelines

- Keep the protocol zero-dependency pure Python
- All encoding roundtrips must be verified (256-byte test for encoding, real-trace corpus for adapter)
- Hamming ECC tests must verify single-bit correction AND double-bit detection
- New features need a test in `verify_integration.py` before merging
- Run full test suite before PR: `python opencode_plugin/verify_integration.py`
- By contributing, you agree your contributions are licensed under Apache-2.0 (code) or CC-BY-4.0 (spec)

## PR process

1. Open an issue describing the change
2. Fork, branch, implement
3. Add or update tests
4. Run full suite (must pass 33/33)
5. PR to `master` with a summary
