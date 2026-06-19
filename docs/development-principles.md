# Development Principles

This project is intended for network refresh planning and review workflows.
Generated output can influence operational decisions, so code should favor
clarity, auditability, and review over cleverness.

## Explainability Rule

All generated code should be written so that a competent human reviewer or AI
assistant can explain its behavior clearly and completely from the source
itself.

Prefer:

- Straightforward control flow.
- Descriptive function and variable names.
- Small functions with explicit inputs and outputs.
- Dataclasses or typed dictionaries for structured data.
- Visible assumptions and explicit failure behavior.
- Tests built from sanitized fixtures.

Avoid:

- Clever compressed logic.
- Hidden side effects.
- Overly broad abstractions before they are needed.
- Parser behavior that requires reverse engineering to understand.
- Mixing parsing, profile evaluation, GUI updates, file I/O, and output
  rendering in the same function.

If code cannot be explained line by line in a clear review, it is too clever
for this project.

## Parser And Profile Logic

Parser and profile-engine code should be especially direct:

- Accept all required inputs explicitly.
- Return structured data instead of mutating GUI state.
- Keep parser regex patterns named and documented when they match network
  command structure.
- Prefer state-machine style parsing for complex multi-line config blocks.
- Add sanitized fixture tests for new or modified parser behavior.
- Treat ambiguous or invalid profile behavior as review-blocking.

## Safety Boundary

The tool stages review material. It should not silently approve generated
configuration, connect to devices, transmit commands, or store credentials.

When in doubt, preserve visibility for the operator.

