import json
import random
import os

# Configuration
GOLDEN_DATASET_PATH = "shared/golden_dataset.json"
TRAIN_PATH = "shared/train.json"
TEST_PATH = "shared/test.json"

TRAIN_RATIO = 0.8
TEST_RATIO = 0.2
RANDOM_SEED = 42


def split_dataset():
    """
    Split the golden dataset into train/val/test sets with proper shuffling.
    This fixes the train/test data leakage issue where the model was evaluated
    on its own training data.
    """
    # Load golden dataset
    if not os.path.exists(GOLDEN_DATASET_PATH):
        raise FileNotFoundError(f"Golden dataset not found at {GOLDEN_DATASET_PATH}")
    
    with open(GOLDEN_DATASET_PATH, 'r') as f:
        data = json.load(f)
    
    total_size = len(data)
    print(f"Total examples in golden dataset: {total_size}")
    
    # Shuffle with fixed seed for reproducibility
    random.seed(RANDOM_SEED)
    random.shuffle(data)
    print(f"✓ Shuffled data with seed={RANDOM_SEED}")
    
    # Calculate split sizes (80/20 train/test)
    train_size = int(total_size * TRAIN_RATIO)
    # Test gets the remainder to ensure all examples are used
    test_size = total_size - train_size
    
    print(f"\nSplit sizes:")
    print(f"  Train: {train_size} ({TRAIN_RATIO*100:.0f}%)")
    print(f"  Test:  {test_size} ({TEST_RATIO*100:.0f}%)")
    
    # Split the data
    train_data = data[:train_size]
    test_data = data[train_size:]
    
    # Verify split
    assert len(train_data) + len(test_data) == total_size, \
        "Split sizes don't add up to total size"
    
    # Save splits
    os.makedirs(os.path.dirname(TRAIN_PATH), exist_ok=True)
    
    with open(TRAIN_PATH, 'w') as f:
        json.dump(train_data, f, indent=2)
    print(f"\n✓ Saved training set to {TRAIN_PATH}")
    
    with open(TEST_PATH, 'w') as f:
        json.dump(test_data, f, indent=2)
    print(f"✓ Saved test set to {TEST_PATH}")
    
    print(f"\n{'='*60}")
    print("Data split complete!")
    print(f"{'='*60}")
    print("\nIMPORTANT: All previous accuracy metrics are now INVALID.")
    print("The model was being evaluated on its training data.")
    print("Re-run optimization and benchmarking with the new splits.")


if __name__ == "__main__":
    split_dataset()
