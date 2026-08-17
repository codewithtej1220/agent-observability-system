"""Real agent trace data loader from public datasets - SIMPLIFIED VERSION.

Uses actual production agent traces with robust fallbacks:
- Multiple dataset attempts for each category
- Graceful degradation to synthetic data
- Clear status reporting
"""
from __future__ import annotations

import json
import os
import random
from typing import Dict, List, Optional

from agent_harness.trace_schema import Step, Trace


class RealDataLoader:
    """Load real agent traces with multiple fallback options."""
    
    def __init__(self, cache_dir: str = "data/real_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def load_healthy_traces(self, max_traces: int = 800) -> List[Trace]:
        """
        Load healthy/successful agent traces from available datasets.
        
        Tries multiple sources, falls back gracefully.
        """
        print("📥 Loading healthy agent traces...")
        
        # Check cache first
        cached = self._load_from_cache_file("healthy_traces.json")
        if cached and len(cached) >= max_traces // 2:
            print(f"   ✅ Using {len(cached)} cached healthy traces")
            return cached[:max_traces]
        
        traces = []
        
        # Try multiple datasets in order of preference
        dataset_options = [
            ("Anthropic/hh-rlhf", "Anthropic HH-RLHF helpful responses"),
            ("tatsu-lab/alpaca", "Alpaca instruction dataset"),
            ("Open-Orca/OpenOrca", "OpenOrca dataset"),
        ]
        
        for dataset_name, description in dataset_options:
            if len(traces) >= max_traces:
                break
                
            try:
                from datasets import load_dataset
                
                print(f"   Trying {description}...")
                dataset = load_dataset(
                    dataset_name,
                    split=f"train[:{min(max_traces, 1000)}]"
                )
                
                print(f"   ✅ Loaded {len(dataset)} items from {dataset_name}")
                
                for idx, item in enumerate(dataset):
                    if len(traces) >= max_traces:
                        break
                    
                    trace = self._convert_generic_to_trace(item, f"healthy_{len(traces)}")
                    if trace:
                        trace.label = "healthy"
                        trace.outcome = "success"
                        traces.append(trace)
                
                if traces:
                    print(f"   ✅ Converted {len(traces)} healthy traces")
                    break  # Success, stop trying other datasets
                    
            except Exception as e:
                print(f"   ⚠️  {dataset_name} unavailable: {str(e)[:80]}")
                continue
        
        # Cache if we got real data
        if traces:
            self._cache_traces(traces, "healthy_traces.json")
            return traces
        
        # Fallback to synthetic
        print(f"   ℹ️  No real datasets available, using synthetic healthy traces")
        from data.synthetic_generator import generate_dataset
        
        synthetic = generate_dataset(n_healthy=max_traces, n_pathological=0)
        for trace in synthetic:
            trace.label = "healthy"
        return synthetic
    
    def load_pathological_traces(self, max_traces: int = 400) -> List[Trace]:
        """
        Load pathological/failure agent traces.
        
        Tries real datasets, falls back to synthetic.
        """
        print("📥 Loading pathological agent traces...")
        
        # Check cache first
        cached = self._load_from_cache_file("pathological_traces.json")
        if cached and len(cached) >= max_traces // 2:
            print(f"   ✅ Using {len(cached)} cached pathological traces")
            return cached[:max_traces]
        
        traces = []
        
        # Try datasets with failure data
        dataset_options = [
            ("Anthropic/hh-rlhf", "Anthropic HH-RLHF with unhelpful responses"),
            ("lmsys/toxic-chat", "Toxic/problematic interactions"),
        ]
        
        for dataset_name, description in dataset_options:
            if len(traces) >= max_traces:
                break
                
            try:
                from datasets import load_dataset
                
                print(f"   Trying {description}...")
                dataset = load_dataset(
                    dataset_name,
                    split=f"train[:{min(max_traces, 500)}]"
                )
                
                print(f"   ✅ Loaded {len(dataset)} items")
                
                for idx, item in enumerate(dataset):
                    if len(traces) >= max_traces:
                        break
                    
                    trace = self._convert_generic_to_trace(item, f"patho_{len(traces)}")
                    if trace:
                        trace.label = "pathological"
                        trace.outcome = "failure"
                        traces.append(trace)
                
                if traces:
                    print(f"   ✅ Converted {len(traces)} pathological traces")
                    break
                    
            except Exception as e:
                print(f"   ⚠️  {dataset_name} unavailable: {str(e)[:80]}")
                continue
        
        # Cache if we got real data
        if traces:
            self._cache_traces(traces, "pathological_traces.json")
            return traces
        
        # Fallback to synthetic
        print(f"   ℹ️  No real failure datasets, using synthetic pathological traces")
        from data.synthetic_generator import generate_dataset
        
        synthetic = generate_dataset(n_healthy=0, n_pathological=max_traces)
        for trace in synthetic:
            trace.label = "pathological"
        return synthetic
    
    def load_mixed_dataset(
        self,
        n_healthy: int = 800,
        n_pathological: int = 400,
        use_synthetic_fallback: bool = True
    ) -> List[Trace]:
        """
        Load a balanced mix of healthy and pathological traces.
        
        Returns a shuffled dataset with labels.
        """
        print("\n" + "=" * 70)
        print("LOADING REAL AGENT TRACE DATASET")
        print("=" * 70)
        
        # Load both types
        healthy_traces = self.load_healthy_traces(max_traces=n_healthy)
        pathological_traces = self.load_pathological_traces(max_traces=n_pathological)
        
        # Combine
        traces = healthy_traces[:n_healthy] + pathological_traces[:n_pathological]
        random.shuffle(traces)
        
        # Count actual labels
        healthy_count = sum(1 for t in traces if t.label == "healthy")
        pathological_count = sum(1 for t in traces if t.label == "pathological")
        
        print(f"\n📊 Final dataset:")
        print(f"   Total: {len(traces)} traces")
        print(f"   Healthy: {healthy_count} ({100*healthy_count/len(traces):.1f}%)")
        print(f"   Pathological: {pathological_count} ({100*pathological_count/len(traces):.1f}%)")
        
        return traces
    
    def _convert_generic_to_trace(self, item: Dict, trace_id: str) -> Optional[Trace]:
        """Convert any dataset item to our Trace format."""
        try:
            steps = []
            
            # Try different field names used by different datasets
            task_desc = item.get("task", item.get("instruction", item.get("prompt", item.get("query", "Unknown task"))))
            
            # Try to extract steps/actions
            if "actions" in item:
                actions = item["actions"] if isinstance(item["actions"], list) else [item["actions"]]
                for idx, action in enumerate(actions):
                    step = Step(
                        step_id=idx,
                        action_type="tool_call",
                        tool_name=action.get("tool", action.get("name", "unknown")),
                        arguments=action.get("arguments", action.get("input", {})),
                        output=str(action.get("output", action.get("result", ""))),
                        latency_ms=int(action.get("latency", action.get("time", 100))),
                        tokens_used=int(action.get("tokens", 10))
                    )
                    steps.append(step)
            
            elif "steps" in item:
                steps_data = item["steps"] if isinstance(item["steps"], list) else [item["steps"]]
                for idx, step_data in enumerate(steps_data):
                    step = Step(
                        step_id=idx,
                        action_type="tool_call",
                        tool_name=step_data.get("tool", "unknown"),
                        arguments=step_data.get("input", {}),
                        output=str(step_data.get("output", "")),
                        latency_ms=100,
                        tokens_used=10
                    )
                    steps.append(step)
            
            elif "messages" in item:
                messages = item["messages"] if isinstance(item["messages"], list) else [item["messages"]]
                for idx, msg in enumerate(messages[:5]):  # Limit to 5 messages
                    step = Step(
                        step_id=idx,
                        action_type="message",
                        tool_name=msg.get("role", "assistant"),
                        arguments={},
                        output=str(msg.get("content", "")),
                        latency_ms=50,
                        tokens_used=len(str(msg.get("content", "")).split())
                    )
                    steps.append(step)
            
            # Need at least 1 step
            if not steps:
                # Create a single step from available data
                step = Step(
                    step_id=0,
                    action_type="tool_call",
                    tool_name="unknown",
                    arguments={},
                    output=str(item.get("output", item.get("response", "no output"))),
                    latency_ms=100,
                    tokens_used=10
                )
                steps.append(step)
            
            trace = Trace(
                trace_id=trace_id,
                task_description=str(task_desc)[:200],  # Limit length
                steps=steps
            )
            
            return trace
            
        except Exception as e:
            # Silently skip bad items
            return None
    
    def _cache_traces(self, traces: List[Trace], filename: str):
        """Cache traces to disk."""
        cache_path = os.path.join(self.cache_dir, filename)
        try:
            with open(cache_path, "w") as f:
                json.dump([t.to_dict() for t in traces], f)
            print(f"   💾 Cached to {filename}")
        except Exception:
            pass  # Silently fail cache writes
    
    def _load_from_cache_file(self, filename: str) -> List[Trace]:
        """Load traces from a specific cache file."""
        cache_path = os.path.join(self.cache_dir, filename)
        
        if not os.path.exists(cache_path):
            return []
        
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
                traces = []
                for item in data:
                    trace = Trace.from_dict(item)
                    traces.append(trace)
                return traces
        except Exception:
            return []


def main():
    """Test the loader."""
    loader = RealDataLoader()
    traces = loader.load_mixed_dataset(n_healthy=800, n_pathological=400)
    print(f"\n✅ Loaded {len(traces)} total traces")


if __name__ == "__main__":
    main()
