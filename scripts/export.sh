#!/bin/bash

# This script exports the trained model for inference or deployment.

MODEL_DIR="data/checkpoints"
EXPORT_DIR="data/exports"
MODEL_NAME="trained_model.pth"

# Create export directory if it doesn't exist
mkdir -p $EXPORT_DIR

# Copy the model to the export directory
cp "$MODEL_DIR/$MODEL_NAME" "$EXPORT_DIR"

echo "Model exported to $EXPORT_DIR/$MODEL_NAME"