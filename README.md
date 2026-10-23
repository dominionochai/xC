# xC

A minimal Python package scaffold for the xC project. No application requirements or source implementation were provided, so this initial commit intentionally contains only a working CLI starter and test.

## Requirements

- Python 3.10+

## Install and run

```sh
python -m pip install -e .
xc hello world
# hello world
xc
# xC starter
```

You can also run it without installing:

```sh
PYTHONPATH=src python -m xc hello world
```

## Test

```sh
python -m unittest discover -s tests
```
