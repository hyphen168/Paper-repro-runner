import argparse
import os
from pathlib import Path

import torch
import yaml
from torch.utils.data import DataLoader as TorchDataLoader

from industrial_vision.data.loaders import CustomDataset
from industrial_vision.models.detector import Detector
from industrial_vision.models.loss import LossFunction
from industrial_vision.utils.logging import setup_logging


def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)


def train_model(config_path='src/industrial_vision/config/defaults.yaml', data_dir='data/raw', epochs=5, batch_size=8, learning_rate=1e-3, device='cpu'):
    config = load_config(config_path)
    logger = setup_logging(log_file=os.path.join(config['logging']['log_dir'], 'train.log'), level=getattr(__import__('logging'), config['logging']['level']))

    dataset = CustomDataset(data_dir or config['data']['train_dir'], image_size=tuple(config['model'].get('image_size', (224, 224))))
    train_loader = TorchDataLoader(dataset, batch_size=batch_size or config['training']['batch_size'], shuffle=True)
    model = Detector(
        input_channels=config['model'].get('input_channels', 3),
        num_classes=config['model'].get('num_classes', 10),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate or config['training']['learning_rate'])
    criterion = LossFunction()

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for inputs, targets in train_loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            outputs = model(inputs.permute(0, 3, 1, 2) if inputs.ndim == 4 and inputs.shape[-1] == 3 else inputs)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()

        logger.info('Epoch %s/%s loss=%.4f', epoch, epochs, running_loss / max(len(train_loader), 1))

    save_dir = Path(config['model'].get('save_dir', 'data/checkpoints'))
    save_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = save_dir / 'model.pth'
    torch.save(model.state_dict(), checkpoint_path)
    logger.info('Model saved to %s', checkpoint_path)
    return str(checkpoint_path)


def main():
    parser = argparse.ArgumentParser(description='Train the industrial vision model.')
    parser.add_argument('--config', default='src/industrial_vision/config/defaults.yaml')
    parser.add_argument('--data-dir', default='data/raw')
    parser.add_argument('--epochs', type=int, default=5)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--learning-rate', type=float, default=1e-3)
    args = parser.parse_args()
    print(train_model(
        config_path=args.config,
        data_dir=args.data_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
    ))


if __name__ == '__main__':
    main()
