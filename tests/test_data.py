import tempfile
from pathlib import Path

from PIL import Image

from industrial_vision.data.loaders import DataLoader


def test_data_loader_loads_sample_images(tmp_path):
    sample_dir = tmp_path / 'images'
    sample_dir.mkdir()
    image_path = sample_dir / 'sample.png'
    Image.new('RGB', (32, 32), color=(255, 0, 0)).save(image_path)

    loader = DataLoader(str(sample_dir), image_size=(32, 32), batch_size=1)
    items = loader.load()

    assert len(items) == 1
    image, label = items[0]
    assert image.shape == (32, 32, 3)
    assert label == 0
