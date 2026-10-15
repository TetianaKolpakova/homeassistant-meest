# Contributing

Use Python 3.13 or 3.14 for development (the independent API tests also run on 3.11).

```sh
python -m venv .venv
# Activate the environment for your shell, then:
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python scripts/check_repository.py
```

Runtime code belongs in `custom_components/meest/`. Tests use invented parcels;
do not commit API captures, APKs, tokens, phone numbers or real addresses.
Do not add tests that depend on a live account. Keep exactly two sensor entities
per account and preserve existing unique IDs and attribute names.

The independent test suite does not boot Home Assistant. Test UI setup, options,
reauthentication and sensor availability in an actual HA installation before
claiming runtime compatibility. Document unverified status mappings explicitly.

GitHub Actions runs unit tests, lint, package checks, hassfest and HACS validation.
HACS checks the published repository's metadata, including description and topics.
