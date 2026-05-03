# Contributing

Thanks for helping improve this project.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Or use:

```bash
make setup
```

## Build preview outputs

```bash
make build-outputs
```

## Run the app

```bash
make run
```

## Validate before opening a PR

```bash
make smoke
```

## Commit hygiene

After clone, run once:

```bash
git config core.hooksPath .githooks
```

This strips `Co-authored-by` lines so GitHub does not list extra contributors.
