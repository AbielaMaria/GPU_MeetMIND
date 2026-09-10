#!/bin/bash
#SBATCH --job-name=deepfake_june17_train
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=train_%j.log
#SBATCH --error=train_err_%j.log

echo "=== Training Started ==="

eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
conda activate my_deepfake_env

cd /home/stiwari/deepfake/17_june_training || exit 1

mkdir -p logs

python3 train_model.py

EXIT_CODE=$?

echo "Training finished with exit code $EXIT_CODE"

exit $EXIT_CODE

