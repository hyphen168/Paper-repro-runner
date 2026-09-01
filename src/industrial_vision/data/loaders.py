from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from torch.utils.data import Dataset


class CustomDataset(Dataset):
    def __init__(self, data_dir, image_size=(224, 224), valid_extensions={'.jpg', '.jpeg', '.png', '.bmp'}):
        self.data_dir = Path(data_dir)
        self.image_size = image_size
        self.valid_extensions = valid_extensions
        self.image_paths = sorted(
            path for path in self.data_dir.rglob('*') if path.is_file() and path.suffix.lower() in self.valid_extensions
        )
        self.labels = self._load_labels()

    def _load_labels(self):
        labels = {}
        label_file = self.data_dir / 'labels.csv'
        if label_file.exists():
            df = pd.read_csv(label_file)
            for _, row in df.iterrows():
                labels[str(row.get('image_name', ''))] = int(row.get('label', 0))
        return labels

    def _preprocess_image(self, image_path: Path):
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f'Unable to read image: {image_path}')
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, self.image_size)
        image = image.astype(np.float32) / 255.0
        return image

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, index):
        image_path = self.image_paths[index]
        image = self._preprocess_image(image_path)
        label = self.labels.get(image_path.name, 0)
        return image, int(label)


class DataLoader:
    def __init__(self, data_dir, image_size=(224, 224), batch_size=32):
        self.data_dir = Path(data_dir)
        self.image_size = image_size
        self.batch_size = batch_size
        self.dataset = CustomDataset(self.data_dir, image_size=image_size)

    def load(self):
        return [self.dataset[index] for index in range(len(self.dataset))]

    def __iter__(self):
        for i in range(0, len(self.dataset), self.batch_size):
            batch = [self.dataset[idx] for idx in range(i, min(i + self.batch_size, len(self.dataset)))]
            yield np.stack([sample[0] for sample in batch]), np.asarray([sample[1] for sample in batch])

    def __len__(self):
        return len(self.dataset)
