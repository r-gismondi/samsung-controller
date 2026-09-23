# Samsung Controller — Agent Guide

## Working agreement

- Treat this repository as the source of truth for the Samsung Controller project.
- Before making changes, inspect the repository structure and identify the language, package manager, build commands, and test commands.
- Keep changes small and focused; preserve existing conventions once they are established.
- Do not commit credentials, tokens, device secrets, local configuration, or generated build artifacts.
- Prefer tests or a reproducible validation command for every behavior change.
- If requirements are ambiguous, describe the assumption before implementing it.

## Validation

Run the project’s documented formatter, linter, build, and test commands when they exist. If the repository is still being bootstrapped and no commands exist, document the proposed next step rather than inventing a production implementation.
