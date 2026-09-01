#!/bin/bash

# Activate the virtual environment
source venv/bin/activate

# Set default values for parameters
EPOCHS=50
BATCH_SIZE=32
LEARNING_RATE=0.001
CONFIG_PATH="src/industrial_vision/config/defaults.yaml"

# Parse command line arguments for custom parameters
while getopts e:b:l:c: flag
do
    case "${flag}" in
        e) EPOCHS=${OPTARG};;
        b) BATCH_SIZE=${OPTARG};;
        l) LEARNING_RATE=${OPTARG};;
        c) CONFIG_PATH=${OPTARG};;
    esac
done

# Run the training script
python src/industrial_vision/pipelines/train.py --epochs $EPOCHS --batch_size $BATCH_SIZE --learning_rate $LEARNING_RATE --config $CONFIG_PATH

# Deactivate the virtual environment
deactivate