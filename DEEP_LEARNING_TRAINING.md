# Deep Learning Training Guide

## Why "Not Found" on API Server?

The FastAPI server only has specific endpoints, NOT a root `/` endpoint:

✅ **Working URLs:**
- http://localhost:8000/docs - Interactive API documentation
- http://localhost:8000/health - Health check
- http://localhost:8000/ingest_trace - Submit traces
- http://localhost:8000/stats - View statistics

❌ **This won't work:**
- http://localhost:8000/ - Returns 404 (no root endpoint)

**Solution:** Always go to `/docs` to see available endpoints!

---

## Deep Learning Training with Epochs

I've created a complete deep learning pipeline that trains with epochs on real data.

### Architecture

**Old approach (current):**
- Unsupervised (IsolationForest + HDBSCAN)
- No epochs, no backpropagation
- Works without labels

**New approach (deep learning):**
- Supervised neural network
- Trains with epochs and backpropagation
- Uses transformer embeddings
- Learns from labeled data

---

## Installation

### Step 1: Install Deep Learning Dependencies

```bash
.\venv\Scripts\activate
pip install -r requirements_dl.txt
```

This installs:
- `torch` - PyTorch deep learning framework
- `transformers` - HuggingFace transformers
- `sentence-transformers` - Semantic embeddings
- `datasets` - Access to HuggingFace datasets
- `wandb` - Training metrics tracking (optional)

### Step 2: Verify Installation

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import sentence_transformers; print('Sentence Transformers: OK')"
```

---

## Data Sources

### Option 1: HuggingFace Datasets (Easiest) ✅

```bash
python data/data_collector.py
```

This collects real agent interaction data from:
- **AgentInstruct/AgentInstruct** - Agent task execution traces
- **m-a-p/Code-Feedback** - Code generation agent traces
- Other publicly available datasets

**No authentication required!**

### Option 2: LangSmith (Requires API Key)

1. Get API key from: https://smith.langchain.com/settings
2. Set environment variable:
   ```bash
   $env:LANGSMITH_API_KEY="your-api-key"
   ```
3. Modify `data_collector.py` to uncomment LangSmith collection

### Option 3: Your Own Production Data

Export from your database:
```python
from data.data_collector import DataCollector

collector = DataCollector()
traces = collector.collect_from_api_export("traces.db")
```

### Option 4: JSON Files

Put your trace JSON files in a directory:
```python
traces = collector.collect_from_json_files("data/my_traces")
```

---

## Training the Deep Learning Model

### Quick Start (with synthetic data)

```bash
python scripts/train_deep_learning.py
```

This will:
1. ✅ Generate 600 synthetic traces (400 healthy, 200 anomalous)
2. ✅ Create transformer embeddings using sentence-transformers
3. ✅ Split into train/validation sets (80/20)
4. ✅ Train neural network for 50 epochs
5. ✅ Show metrics: loss, accuracy, precision, recall, F1
6. ✅ Save best model to `artifacts/best_model.pt`

### Training with Real Data

Edit `train_deep_learning.py` line 275:
```python
USE_REAL_DATA = True  # Change from False to True
```

Then run:
```bash
python scripts/train_deep_learning.py
```

### Configuration Options

Open `scripts/train_deep_learning.py` and modify:

```python
# Line 273-278
USE_REAL_DATA = False      # Use real data instead of synthetic
EPOCHS = 50                # Number of training epochs
BATCH_SIZE = 32            # Batch size for training
LEARNING_RATE = 0.001      # Learning rate
USE_WANDB = False          # Enable Weights & Biases tracking
```

---

## Training Output Example

```
==============================================================
STEP 1: Preparing Data
==============================================================
📦 Generating synthetic data to supplement...
Generated 600 traces (200 pathological, 400 healthy)
✅ Total dataset: 600 traces
   - Anomalous: 200 (33.3%)
   - Healthy: 400 (66.7%)

==============================================================
STEP 2: Creating Embeddings
==============================================================
Loading transformer model: all-MiniLM-L6-v2
Embedding dimension: 384
Encoding 600 traces...
100%|████████████████████| 600/600 [00:12<00:00, 48.23it/s]

==============================================================
STEP 3: Splitting Data
==============================================================
Training set: 480 samples
Validation set: 120 samples

==============================================================
STEP 4: Training Deep Learning Model
==============================================================
Model architecture:
DeepAnomalyDetector(
  (network): Sequential(
    (0): Linear(in_features=384, out_features=256, bias=True)
    (1): ReLU()
    (2): Dropout(p=0.3, inplace=False)
    (3): BatchNorm1d(256, eps=1e-05, momentum=0.1)
    (4): Linear(in_features=256, out_features=128, bias=True)
    (5): ReLU()
    (6): Dropout(p=0.3, inplace=False)
    (7): BatchNorm1d(128, eps=1e-05, momentum=0.1)
    (8): Linear(in_features=128, out_features=64, bias=True)
    (9): ReLU()
    (10): Dropout(p=0.3, inplace=False)
    (11): BatchNorm1d(64, eps=1e-05, momentum=0.1)
    (12): Linear(in_features=64, out_features=2, bias=True)
  )
)

Total parameters: 141,954

🚀 Training on cuda

Epoch [1/50]
  Train Loss: 0.5234, Acc: 78.12%
  Val Loss: 0.4123, Acc: 82.50%
  Precision: 0.789, Recall: 0.823, F1: 0.806
  ✅ Saved best model

Epoch [2/50]
  Train Loss: 0.4012, Acc: 85.21%
  Val Loss: 0.3456, Acc: 87.50%
  Precision: 0.856, Recall: 0.891, F1: 0.873
  ✅ Saved best model

...

Epoch [50/50]
  Train Loss: 0.0823, Acc: 97.29%
  Val Loss: 0.1234, Acc: 95.83%
  Precision: 0.953, Recall: 0.968, F1: 0.960

✅ Training complete!
💾 Model saved to artifacts/final_model.pt
💾 Best model saved to artifacts/best_model.pt
```

---

## Understanding the Metrics

- **Loss**: How wrong the model is (lower is better)
- **Accuracy**: % of correct predictions
- **Precision**: Of traces flagged as anomalous, how many actually were?
- **Recall**: Of all anomalous traces, how many did we catch?
- **F1 Score**: Harmonic mean of precision and recall

---

## Using the Trained Model

After training, you'll have:
- `artifacts/transformer_embedder.pkl` - Transformer embedding model
- `artifacts/best_model.pt` - Best model from training
- `artifacts/final_model.pt` - Final model after all epochs

To use in the API, you'll need to modify `api/main.py` to load the PyTorch model instead of the sklearn model.

---

## Advanced: Tracking with Weights & Biases

1. Install wandb:
   ```bash
   pip install wandb
   ```

2. Login:
   ```bash
   wandb login
   ```

3. Enable in training script:
   ```python
   USE_WANDB = True
   ```

4. View training metrics at: https://wandb.ai

---

## Troubleshooting

### CUDA/GPU Issues
If you get CUDA errors, the model will automatically fall back to CPU:
```
🚀 Training on cpu
```

To force CPU:
```python
device = "cpu"  # Change in train_model() function
```

### Out of Memory
Reduce batch size:
```python
BATCH_SIZE = 16  # or even 8
```

### Slow Training
- Use a smaller model:
  ```python
  hidden_dims=[128, 64]  # Instead of [256, 128, 64]
  ```
- Use a faster embedder:
  ```python
  model_name="paraphrase-MiniLM-L3-v2"
  ```

---

## Data Collection Examples

### Collect from HuggingFace
```bash
python -c "from data.data_collector import DataCollector; c = DataCollector(); c.collect_from_huggingface('AgentInstruct/AgentInstruct')"
```

### Collect from Multiple Sources
```python
from data.data_collector import DataCollector

collector = DataCollector()

# Get all available data
hf_data = collector.collect_from_huggingface()
json_data = collector.collect_from_json_files("my_traces")
all_data = hf_data + json_data

print(f"Total: {len(all_data)} traces")
```

---

## Next Steps

1. ✅ Install dependencies: `pip install -r requirements_dl.txt`
2. ✅ Collect real data: `python data/data_collector.py`
3. ✅ Train model: `python scripts/train_deep_learning.py`
4. ⏭️ Integrate trained model into API
5. ⏭️ Deploy and monitor in production

Happy training! 🚀
