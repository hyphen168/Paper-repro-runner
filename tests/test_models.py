import torch

from industrial_vision.models.detector import Detector
from industrial_vision.models.loss import LossFunction


def test_detector_initializes_and_runs():
    detector = Detector(input_channels=3, num_classes=10)
    sample = torch.randn(2, 3, 224, 224)
    outputs = detector(sample)
    assert outputs.shape == (2, 10)


def test_loss_function_computes_cross_entropy():
    detector = Detector(input_channels=3, num_classes=10)
    sample = torch.randn(2, 3, 224, 224)
    outputs = detector(sample)
    targets = torch.tensor([0, 1])
    loss = LossFunction()(outputs, targets)
    assert isinstance(loss.item(), float)
