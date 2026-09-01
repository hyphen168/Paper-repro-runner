import argparse
import json

import torch
from torch.utils.data import DataLoader as TorchDataLoader

from industrial_vision.data.loaders import CustomDataset
from industrial_vision.models.detector import Detector
from industrial_vision.utils.metrics import calculate_accuracy, calculate_f1_score, calculate_precision, calculate_recall


def evaluate_model(checkpoint_path='data/checkpoints/model.pth', data_dir='data/raw', device='cpu'):
    dataset = CustomDataset(data_dir)
    loader = TorchDataLoader(dataset, batch_size=8, shuffle=False)
    model = Detector(input_channels=3, num_classes=10)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.to(device)
    model.eval()

    predictions = []
    labels = []
    with torch.no_grad():
        for inputs, targets in loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            outputs = model(inputs.permute(0, 3, 1, 2) if inputs.ndim == 4 and inputs.shape[-1] == 3 else inputs)
            pred = outputs.argmax(dim=1)
            predictions.extend(pred.cpu().tolist())
            labels.extend(targets.cpu().tolist())

    metrics = {
        'accuracy': calculate_accuracy(labels, predictions),
        'precision': calculate_precision(labels, predictions),
        'recall': calculate_recall(labels, predictions),
        'f1_score': calculate_f1_score(labels, predictions),
    }
    return metrics


def main():
    parser = argparse.ArgumentParser(description='Evaluate the industrial vision model.')
    parser.add_argument('--checkpoint', default='data/checkpoints/model.pth')
    parser.add_argument('--data-dir', default='data/raw')
    args = parser.parse_args()
    metrics = evaluate_model(checkpoint_path=args.checkpoint, data_dir=args.data_dir)
    print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
