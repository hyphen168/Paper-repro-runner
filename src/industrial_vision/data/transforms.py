import random

import numpy as np
from torchvision import transforms


class DataTransform:
    """Simple transform utility used by the project tests and scripts."""

    def __init__(self, scale=1.0):
        self.scale = scale

    def apply(self, data):
        values = list(data)
        return [float(value) ** 2 for value in values]

    def __call__(self, image):
        if isinstance(image, (list, tuple, np.ndarray)):
            return np.asarray(image, dtype=np.float32) ** 2
        return image


class ResizeAndNormalize:
    def __init__(self, size=(256, 256), mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5)):
        self.resize = transforms.Resize(size)
        self.normalize = transforms.Normalize(mean=mean, std=std)

    def __call__(self, image):
        image = self.resize(image)
        image = transforms.ToTensor()(image)
        image = self.normalize(image)
        return image


class RandomHorizontalFlip:
    def __init__(self, p=0.5):
        self.p = p

    def __call__(self, image):
        if random.random() < self.p:
            image = transforms.functional.hflip(image)
        return image


class ComposeTransforms:
    def __init__(self, transforms):
        self.transforms = transforms

    def __call__(self, image):
        for transform in self.transforms:
            image = transform(image)
        return image
