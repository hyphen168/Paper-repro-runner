# Industrial Vision Repro

A practical and extensible machine vision project template for industrial defect inspection, image classification, and visual analytics. The project is intentionally structured as a production-friendly baseline with reusable data pipelines, deterministic metrics, a small model implementation, and a simple CLI workflow.

## Features

- Modular project layout with `src/` package organization
- Image dataset loading and preprocessing utilities
- Torch-based model skeleton for industrial visual tasks
- Evaluation and metric utilities
- CLI entry points for training, evaluation, and inference
- Automated tests and Git-friendly project setup

## Project structure

```text
industrial-vision-repro/
├── src/
│   └── industrial_vision/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config/
│       │   ├── __init__.py
│       │   └── defaults.yaml
│       ├── data/
│       │   ├── __init__.py
│       │   ├── loaders.py
│       │   └── transforms.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── detector.py
│       │   └── loss.py
│       ├── pipelines/
│       │   ├── __init__.py
│       │   ├── evaluate.py
│       │   ├── infer.py
│       │   └── train.py
│       └── utils/
│           ├── io.py
│           ├── logging.py
│           └── metrics.py
├── tests/
├── data/
├── docs/
├── experiments/
├── scripts/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── setup.cfg
├── pytest.ini
└── .gitignore
```

## Installation

1. Clone the repository:

```bash
git clone https://github.com/hyphen168/Yolov5m-NEU-DET.git
cd Yolov5m-NEU-DET
```

2. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
pip install -e .
```

## Quick start

Train a model on a dataset folder:

```bash
python -m industrial_vision train --config src/industrial_vision/config/defaults.yaml --data-dir data/raw --epochs 5 --batch-size 8 --lr 0.001
```

Evaluate a checkpoint:

```bash
python -m industrial_vision evaluate --checkpoint data/checkpoints/model.pth --data-dir data/raw
```

Run inference on a single image:

```bash
python -m industrial_vision infer --checkpoint data/checkpoints/model.pth --image path/to/sample.png
```

## Configuration

The default configuration lives in `src/industrial_vision/config/defaults.yaml` and controls:

- model type and parameters
- training hyperparameters
- dataset directory settings
- logging configuration

## Git workflow

This project is intended to be used with Git in a normal engineering workflow:

```bash
git checkout -b feature/industrial-vision-upgrade
git add .
git commit -m "feat: initialize industrial vision baseline"
git push -u origin HEAD
```

## Testing

Run the project test suite with:

```bash
pytest -q
```

## Contributing

Contributions are welcome. Please keep changes focused, add tests for new functionality, and maintain a clean commit history.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Notes

This repository is intended as a reusable industrial vision scaffold that can be adapted for real manufacturing inspection pipelines, defect classification, or detection tasks.
