from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class Detector(nn.Module):
    def __init__(self, input_channels=3, num_classes=10, hidden_dim=64):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Conv2d(input_channels, hidden_dim, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(hidden_dim, hidden_dim * 2, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(hidden_dim * 2 * 56 * 56, 128),
            nn.ReLU(),
            nn.Linear(128, num_classes),
        )

    def forward(self, x):
        x = self.backbone(x)
        x = self.classifier(x)
        return x

    def compute_loss(self, outputs, targets):
        return F.cross_entropy(outputs, targets)

    def predict(self, x):
        return self(x)

    def load_weights(self, weight_path):
        self.load_state_dict(torch.load(weight_path, map_location='cpu'))

    def save_weights(self, weight_path):
        torch.save(self.state_dict(), weight_path)
