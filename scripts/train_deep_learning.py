"""Deep Learning training pipeline with epochs for anomaly detection.

Uses:
- Transformer-based embeddings (sentence-transformers)
- Neural network classifier with epochs
- Real data from multiple sources
- Training/validation split
- Metrics tracking with wandb

Run with: python scripts/train_deep_learning.py
"""
from __future__ import annotations

import os
import pickle
import sys
from typing import List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_harness.trace_schema import Trace  # noqa: E402
from data.data_collector import DataCollector  # noqa: E402
from data.synthetic_generator import generate_dataset  # noqa: E402

# Try to import deep learning dependencies
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("⚠️  sentence-transformers not installed. Run: pip install -r requirements_dl.txt")

try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False
    print("⚠️  wandb not installed (optional). Run: pip install wandb")


class DeepAnomalyDetector(nn.Module):
    """Neural network for anomaly detection."""
    
    def __init__(self, input_dim: int = 384, hidden_dims: List[int] = [256, 128, 64]):
        super().__init__()
        
        layers = []
        prev_dim = input_dim
        
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.BatchNorm1d(hidden_dim)
            ])
            prev_dim = hidden_dim
        
        # Output layer: binary classification (anomalous or not)
        layers.append(nn.Linear(prev_dim, 2))
        
        self.network = nn.Sequential(*layers)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)


class TransformerEmbedder:
    """Use sentence-transformers for semantic embeddings."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Args:
            model_name: HuggingFace model name
                - 'all-MiniLM-L6-v2': Fast, 384 dims (default)
                - 'all-mpnet-base-v2': Better quality, 768 dims
                - 'paraphrase-MiniLM-L3-v2': Very fast, 384 dims
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("Install sentence-transformers: pip install -r requirements_dl.txt")
        
        print(f"Loading transformer model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        print(f"Embedding dimension: {self.embedding_dim}")
    
    def embed_traces(self, traces: List[Trace]) -> np.ndarray:
        """Convert traces to semantic embeddings."""
        texts = []
        
        for trace in traces:
            # Create a rich text representation of the trace
            text_parts = [f"Task: {trace.task_description}"]
            
            for step in trace.steps:
                tool = step.tool_name or "unknown"
                args = str(step.arguments)[:100]  # Truncate long args
                output = step.output[:100]  # Truncate long outputs
                text_parts.append(f"Tool: {tool}, Args: {args}, Output: {output}")
            
            # Add summary statistics
            text_parts.append(f"Total steps: {len(trace.steps)}")
            
            # Tool diversity
            unique_tools = len(set(s.tool_name for s in trace.steps if s.tool_name))
            text_parts.append(f"Unique tools: {unique_tools}")
            
            # Join all parts
            text = " | ".join(text_parts)
            texts.append(text)
        
        print(f"Encoding {len(texts)} traces...")
        embeddings = self.model.encode(texts, show_progress_bar=True, batch_size=32)
        return embeddings


def prepare_data(use_real_data: bool = False) -> Tuple[List[Trace], np.ndarray]:
    """
    Prepare training data.
    
    Args:
        use_real_data: If True, try to collect real data; otherwise use synthetic
        
    Returns:
        (traces, labels) where labels are 1 for anomalous, 0 for healthy
    """
    traces = []
    
    if use_real_data:
        print("📥 Collecting real-world data...")
        collector = DataCollector()
        
        # Try to load cached data first
        cached = collector.load_cached_data()
        if cached:
            print(f"Found {len(cached)} cached traces")
            # Convert to Trace objects (you'll need to implement proper conversion)
            for item in cached:
                try:
                    trace = Trace.from_dict(item)
                    traces.append(trace)
                except Exception as e:
                    print(f"Skipping invalid trace: {e}")
        else:
            # Collect fresh data
            print("No cached data found. Collecting from HuggingFace...")
            hf_traces = collector.collect_from_huggingface()
            
            # Convert and save
            for item in hf_traces:
                try:
                    trace = Trace.from_dict(item)
                    traces.append(trace)
                except Exception:
                    continue
        
        # For real data, you need to label it manually or use heuristics
        # For now, let's use simple heuristics
        labels = []
        for trace in traces:
            # Heuristic: anomalous if many repeated tools or very long
            unique_tools = len(set(s.tool_name for s in trace.steps if s.tool_name))
            total_steps = len(trace.steps)
            
            # Flag as anomalous if:
            # - More than 10 steps with low tool diversity
            # - More than 20 steps
            # - Any error outputs
            is_anomalous = (
                (total_steps > 10 and unique_tools < 3) or
                total_steps > 20 or
                any("error" in s.output.lower() for s in trace.steps)
            )
            labels.append(1 if is_anomalous else 0)
        
        labels = np.array(labels)
    
    # If no real data or not enough, supplement with synthetic
    if len(traces) < 100:
        print("📦 Generating synthetic data to supplement...")
        synthetic_traces = generate_dataset(n_healthy=400, n_pathological=200)
        synthetic_labels = np.array([1 if t.label == "pathological" else 0 for t in synthetic_traces])
        
        traces.extend(synthetic_traces)
        if len(labels) > 0:
            labels = np.concatenate([labels, synthetic_labels])
        else:
            labels = synthetic_labels
    
    print(f"✅ Total dataset: {len(traces)} traces")
    print(f"   - Anomalous: {int(labels.sum())} ({100*labels.mean():.1f}%)")
    print(f"   - Healthy: {int(len(labels) - labels.sum())} ({100*(1-labels.mean()):.1f}%)")
    
    return traces, labels


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    epochs: int = 50,
    learning_rate: float = 0.001,
    device: str = "cuda" if torch.cuda.is_available() else "cpu",
    use_wandb: bool = False
) -> None:
    """
    Train the deep learning model.
    
    Args:
        model: PyTorch model
        train_loader: Training data loader
        val_loader: Validation data loader
        epochs: Number of training epochs
        learning_rate: Learning rate
        device: Device to train on
        use_wandb: Whether to log to Weights & Biases
    """
    model = model.to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=5)
    
    print(f"\n🚀 Training on {device}")
    print(f"Epochs: {epochs}, Learning rate: {learning_rate}")
    
    best_val_loss = float('inf')
    
    for epoch in range(epochs):
        # Training phase
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        
        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(device), batch_y.to(device)
            
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            train_total += batch_y.size(0)
            train_correct += (predicted == batch_y).sum().item()
        
        train_loss /= len(train_loader)
        train_acc = 100 * train_correct / train_total
        
        # Validation phase
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        val_tp = 0
        val_fp = 0
        val_fn = 0
        
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X, batch_y = batch_X.to(device), batch_y.to(device)
                
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                
                val_loss += loss.item()
                _, predicted = torch.max(outputs.data, 1)
                val_total += batch_y.size(0)
                val_correct += (predicted == batch_y).sum().item()
                
                # Calculate precision/recall
                val_tp += ((predicted == 1) & (batch_y == 1)).sum().item()
                val_fp += ((predicted == 1) & (batch_y == 0)).sum().item()
                val_fn += ((predicted == 0) & (batch_y == 1)).sum().item()
        
        val_loss /= len(val_loader)
        val_acc = 100 * val_correct / val_total
        
        precision = val_tp / max(1, val_tp + val_fp)
        recall = val_tp / max(1, val_tp + val_fn)
        f1 = 2 * precision * recall / max(0.0001, precision + recall)
        
        scheduler.step(val_loss)
        
        # Print progress
        print(f"Epoch [{epoch+1}/{epochs}]")
        print(f"  Train Loss: {train_loss:.4f}, Acc: {train_acc:.2f}%")
        print(f"  Val Loss: {val_loss:.4f}, Acc: {val_acc:.2f}%")
        print(f"  Precision: {precision:.3f}, Recall: {recall:.3f}, F1: {f1:.3f}")
        
        # Log to wandb
        if use_wandb and WANDB_AVAILABLE:
            wandb.log({
                "epoch": epoch,
                "train_loss": train_loss,
                "train_acc": train_acc,
                "val_loss": val_loss,
                "val_acc": val_acc,
                "precision": precision,
                "recall": recall,
                "f1": f1
            })
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), "artifacts/best_model.pt")
            print("  ✅ Saved best model")


def main():
    """Main training pipeline."""
    
    # Configuration
    USE_REAL_DATA = False  # Set to True to try collecting real data
    EPOCHS = 50
    BATCH_SIZE = 32
    LEARNING_RATE = 0.001
    USE_WANDB = False  # Set to True and run 'wandb login' to enable tracking
    
    os.makedirs("artifacts", exist_ok=True)
    
    # Initialize wandb
    if USE_WANDB and WANDB_AVAILABLE:
        wandb.init(project="agent-anomaly-detection", config={
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "learning_rate": LEARNING_RATE
        })
    
    # Step 1: Prepare data
    print("=" * 60)
    print("STEP 1: Preparing Data")
    print("=" * 60)
    traces, labels = prepare_data(use_real_data=USE_REAL_DATA)
    
    # Step 2: Create embeddings
    print("\n" + "=" * 60)
    print("STEP 2: Creating Embeddings")
    print("=" * 60)
    
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        print("\n❌ Cannot proceed without sentence-transformers")
        print("Install with: pip install -r requirements_dl.txt")
        return
    
    embedder = TransformerEmbedder(model_name="all-MiniLM-L6-v2")
    embeddings = embedder.embed_traces(traces)
    
    # Save embedder
    with open("artifacts/transformer_embedder.pkl", "wb") as f:
        pickle.dump(embedder, f)
    print("💾 Saved embedder to artifacts/transformer_embedder.pkl")
    
    # Step 3: Train/test split
    print("\n" + "=" * 60)
    print("STEP 3: Splitting Data")
    print("=" * 60)
    
    X_train, X_val, y_train, y_val = train_test_split(
        embeddings, labels, test_size=0.2, random_state=42, stratify=labels
    )
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Validation set: {len(X_val)} samples")
    
    # Convert to PyTorch tensors
    train_dataset = TensorDataset(
        torch.FloatTensor(X_train),
        torch.LongTensor(y_train)
    )
    val_dataset = TensorDataset(
        torch.FloatTensor(X_val),
        torch.LongTensor(y_val)
    )
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE)
    
    # Step 4: Train model
    print("\n" + "=" * 60)
    print("STEP 4: Training Deep Learning Model")
    print("=" * 60)
    
    model = DeepAnomalyDetector(
        input_dim=embeddings.shape[1],
        hidden_dims=[256, 128, 64]
    )
    
    print(f"\nModel architecture:")
    print(model)
    print(f"\nTotal parameters: {sum(p.numel() for p in model.parameters()):,}")
    
    train_model(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        use_wandb=USE_WANDB
    )
    
    # Save final model
    torch.save(model.state_dict(), "artifacts/final_model.pt")
    print("\n✅ Training complete!")
    print("💾 Model saved to artifacts/final_model.pt")
    print("💾 Best model saved to artifacts/best_model.pt")
    
    if USE_WANDB and WANDB_AVAILABLE:
        wandb.finish()


if __name__ == "__main__":
    main()
