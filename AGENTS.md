# Samsung Controller — Agent Guide

## Working agreement

- Treat this repository as the source of truth for the Samsung Controller project.
- Before making changes, inspect the repository structure and identify the language, package manager, build commands, and test commands.
- Keep changes small and focused; preserve existing conventions once they are established.
- Do not commit credentials, tokens, device secrets, local configuration, or generated build artifacts.
- Prefer tests or a reproducible validation command for every behavior change.
- If requirements are ambiguous, describe the assumption before implementing it.

## Publishing

After a change request, land the work without waiting for review or a manual pull request:

- Commit on a feature branch and push it to origin.
- Open a pull request into `main`, then merge it.
- If pull-request creation fails because this agent is not a GitHub collaborator, or the integration cannot access pull requests, merge the feature branch into `main` and push `main`. Use a fast-forward or a merge commit. Do not force-push `main`. Do not stop and ask for the pull request to be opened by hand.

Git push is the path that already has access on this repository. `main` is not a protected branch.

## Validation

Run the project’s documented formatter, linter, build, and test commands when they exist. If the repository is still being bootstrapped and no commands exist, document the proposed next step rather than inventing a production implementation.
