def read_image(file_path):
    from PIL import Image
    import numpy as np

    image = Image.open(file_path)
    return np.array(image)

def save_image(image_array, file_path):
    from PIL import Image

    image = Image.fromarray(image_array)
    image.save(file_path)

def read_json(file_path):
    import json

    with open(file_path, 'r') as f:
        return json.load(f)

def save_json(data, file_path):
    import json

    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def read_txt(file_path):
    with open(file_path, 'r') as f:
        return f.read()

def save_txt(data, file_path):
    with open(file_path, 'w') as f:
        f.write(data)