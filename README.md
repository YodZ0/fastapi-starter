# FastAPI application boilerplate

## Quality gates

`ruff check`, `ruff format`, `mypy` and `pytest` are one command, not four:

```sh
uv run --frozen pre-commit run --all-files
```

Setup, once per clone:

```sh
uv sync --frozen
uv run --frozen pre-commit install
```

The hook list lives in [.pre-commit-config.yaml](.pre-commit-config.yaml) and is
the only definition of the gates - the command above and the git `pre-commit`
hook run that same list, so a local run and a blocked commit can never disagree.
