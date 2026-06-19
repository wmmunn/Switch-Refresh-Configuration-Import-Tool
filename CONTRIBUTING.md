# Contributing

Contributions should remain small, reviewable, and safe for public use.

1. Create a focused branch.
2. Add or update sanitized tests.
3. Run `python -m unittest discover -s tests -v`.
4. Explain behavior changes and operator impact in the pull request.

Never include customer configs, credentials, private paths, device logs,
screenshots, ticket details, or production IP addressing. Use the RFC
documentation networks and `DEMO` identifiers from `examples/`.

Execution-related behavior must remain explicitly gated by operator review.
This project extracts text only and should not connect to or configure devices.

Generated code should follow the explainability rule documented in
[`docs/development-principles.md`](docs/development-principles.md). Code should
be clear enough that a competent human reviewer or AI assistant can explain its
behavior from the source without reverse engineering hidden assumptions.
