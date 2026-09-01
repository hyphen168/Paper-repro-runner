#!/bin/bash

# This script is used to evaluate the trained model.

# Set the path to the model checkpoint
CHECKPOINT_PATH="data/checkpoints/model.pth"

# Set the path to the evaluation dataset
EVAL_DATASET_PATH="data/processed/eval_dataset"

# Set the output directory for evaluation results
OUTPUT_DIR="experiments/results/evaluation"

# Create output directory if it doesn't exist
mkdir -p $OUTPUT_DIR

# Run the evaluation script
python -m src.industrial_vision.pipelines.evaluate \
    --checkpoint $CHECKPOINT_PATH \
    --dataset $EVAL_DATASET_PATH \
    --output $OUTPUT_DIR/evaluation_results.json

echo "Evaluation completed. Results saved to $OUTPUT_DIR/evaluation_results.json"