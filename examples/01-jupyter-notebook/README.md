# Example: Jupyter Notebook

This example demonstrates that a full Jupyter notebook session works correctly
inside the pybox sandbox. The sandbox does not interfere with kernel startup,
cell execution, or file I/O within the working directory.

## What it checks

- Jupyter and ipykernel start normally under the sandbox
- Notebook cells can import packages installed in the venv
- Cells can read and write files within the working directory
- Cells **cannot** write to locations outside the working directory (e.g. `/tmp`)
- The failure is a clean `PermissionError`, not a crash

## Setup

Uses a `pip`-based venv (plain `python -m venv`).

```
pip install pybox jupyter ipykernel pandas matplotlib
```

pybox is activated automatically on first Python startup via the `.pth` hook.

## File layout

```
01-jupyter-notebook/
├── README.md
├── Makefile
├── analysis.ipynb       # The notebook: data processing + sandbox boundary test
├── data/
│   └── sales.csv        # Input data read by the notebook
└── output/              # Notebook writes results here (gitignored)
```

## Make targets

| Target | Description |
|--------|-------------|
| `make setup` | Create venv, install dependencies |
| `make run` | Execute notebook headlessly, write `output/executed.ipynb` + HTML report |
| `make serve` | Launch Jupyter in the browser (interactive demo) |
| `make clean` | Remove venv and outputs |

## Expected output

`make run` executes all cells and produces `output/executed.ipynb` and
`output/report.html`. The final cells show:

- A summary table written to `output/summary.csv` — succeeds
- An attempt to write to `/tmp/escaped.txt` — raises `PermissionError`
- The traceback is captured in the notebook output, demonstrating the boundary
