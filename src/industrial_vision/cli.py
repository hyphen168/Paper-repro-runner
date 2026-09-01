import argparse

from industrial_vision.utils.metrics import calculate_accuracy, calculate_f1_score, calculate_precision, calculate_recall


def _demo_metrics():
    y_true = [1, 0, 1, 1, 0]
    y_pred = [1, 0, 1, 0, 0]
    return {
        'accuracy': calculate_accuracy(y_true, y_pred),
        'precision': calculate_precision(y_true, y_pred),
        'recall': calculate_recall(y_true, y_pred),
        'f1_score': calculate_f1_score(y_true, y_pred),
    }


def build_parser():
    parser = argparse.ArgumentParser(description='Industrial vision utility CLI')
    subparsers = parser.add_subparsers(dest='command')

    demo_parser = subparsers.add_parser('demo', help='Run a quick metrics demo.')
    demo_parser.set_defaults(func=lambda args: print(_demo_metrics()))

    train_parser = subparsers.add_parser('train', help='Train a lightweight industrial vision model.')
    train_parser.add_argument('--config', default='src/industrial_vision/config/defaults.yaml')
    train_parser.add_argument('--data-dir', default='data/raw')
    train_parser.add_argument('--epochs', type=int, default=5)
    train_parser.add_argument('--batch-size', type=int, default=8)
    train_parser.add_argument('--lr', type=float, default=1e-3)
    train_parser.set_defaults(func=lambda args: __import__('industrial_vision.pipelines.train', fromlist=['train_model']).train_model(
        config_path=args.config,
        data_dir=args.data_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
    ))

    eval_parser = subparsers.add_parser('evaluate', help='Evaluate a model checkpoint.')
    eval_parser.add_argument('--checkpoint', default='data/checkpoints/model.pth')
    eval_parser.add_argument('--data-dir', default='data/raw')
    eval_parser.set_defaults(func=lambda args: __import__('industrial_vision.pipelines.evaluate', fromlist=['evaluate_model']).evaluate_model(
        checkpoint_path=args.checkpoint,
        data_dir=args.data_dir,
    ))

    infer_parser = subparsers.add_parser('infer', help='Run inference on a single image.')
    infer_parser.add_argument('--checkpoint', default='data/checkpoints/model.pth')
    infer_parser.add_argument('--image', required=True)
    infer_parser.set_defaults(func=lambda args: __import__('industrial_vision.pipelines.infer', fromlist=['infer_image']).infer_image(
        checkpoint_path=args.checkpoint,
        image_path=args.image,
    ))

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, 'func'):
        parser.print_help()
        return
    result = args.func(args)
    if result is not None:
        print(result)


if __name__ == '__main__':
    main()
