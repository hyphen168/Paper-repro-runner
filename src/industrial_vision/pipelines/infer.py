import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from industrial_vision.models.detector import Detector


def infer_image(checkpoint_path='data/checkpoints/model.pth', image_path='data/raw/sample.png', device='cpu'):
    model = Detector(input_channels=3, num_classes=10).to(device)
    if Path(checkpoint_path).exists():
        model.load_state_dict(torch.load(checkpoint_path, map_location=device))
    model.eval()

    image = np.array(Image.open(image_path).convert('RGB'))
    image = cv2.resize(image, (224, 224))
    tensor = torch.tensor(image, dtype=torch.float32).permute(2, 0, 1) / 255.0
    tensor = tensor.unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(tensor)
        predicted_index = int(logits.argmax(dim=1).item())
        probabilities = logits.softmax(dim=1).squeeze(0).cpu().tolist()

    return {'predicted_index': predicted_index, 'probabilities': probabilities}


def main():
    parser = argparse.ArgumentParser(description='Run inference on an industrial vision image.')
    parser.add_argument('--checkpoint', default='data/checkpoints/model.pth')
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    result = infer_image(checkpoint_path=args.checkpoint, image_path=args.image)
    print(result)


if __name__ == '__main__':
    main()
