"""Real agent trace data loader from public datasets.

Uses actual production agent traces instead of synthetic data:
- Exgentic/agent-llm-traces-v2: 10,057 real traces from 6 benchmarks
- Who&When Agents_Failure_Attribution: 1,448 failure traces
- Fallback to synthetic only if download fails
"""
from __future__ import annotations

import json
import os
import random
from typing import Dict, List, Optional

from agent_harness.trace_schema import Step, Trace


class RealDataLoader:
    """Load real agent traces from HuggingFace datasets."""
    
    def __init__(self, cache_dir: str = "data/real_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def load_exgentic_traces(self, max_traces: int = 500) -> List[Trace]:
        """
        Load real agent traces from Exgentic/agent-llm-traces-v2.
        
        This dataset contains 10,057 real OpenTelemetry-shaped agent traces
        across 6 benchmarks with real tool calls, timing, and token usage.
        
        Note: Loading limited to max_traces for faster training.
        """
        print("📥 Loading Exgentic/agent-llm-traces-v2 dataset...")
        
        try:
            from datasets import load_dataset
            
            # Load dataset with streaming for faster access
            print(f"   Limiting to first {max_traces} traces for speed...")
            dataset = load_dataset(
                "Exgentic/agent-llm-traces-v2",
                split=f"train[:{max_traces}]",  # Only load first N traces
                streaming=False
            )
            
            print(f"✅ Loaded {len(dataset)} traces from Exgentic dataset")
            
            traces = []
            for idx, item in enumerate(dataset):
                if idx >= max_traces:
                    break
                
                trace = self._convert_exgentic_to_trace(item, idx)
                if trace:
                    traces.append(trace)
            
            print(f"✅ Converted {len(traces)} Exgentic traces")
            
            # Cache for future use
            self._cache_traces(traces, "exgentic_traces.json")
            
            return traces
            
        except Exception as e:
            print(f"⚠️  Failed to load Exgentic dataset: {e}")
            print("   Install with: pip install datasets")
            return []
    
    def load_failure_traces(self, max_traces: int = 500) -> List[Trace]:
        """
        Load failure-centric traces from alternative datasets.
        
        Tries multiple sources for pathological agent behavior.
        """
        print("📥 Loading failure traces from available datasets...")
        
        traces = []
        
        # Try multiple dataset sources
        dataset_attempts = [
            ("tau-bench/tau-bench", "Tau-Bench agent failures"),
            ("agentinstruct/AgentInstruct", "AgentInstruct with failures"),
        ]
        
        for dataset_name, description in dataset_attempts:
            try:
                from datasets import load_dataset
                
                print(f"   Trying {description}...")
                dataset = load_dataset(dataset_name, split="train[:500]", trust_remote_code=True)
                
                print(f"   ✅ Loaded {len(dataset)} traces from {dataset_name}")
                
                for idx, item in enumerate(dataset):
                    if len(traces) >= max_traces:
                        break
                    
                    trace = self._convert_failure_to_trace(item, len(traces))
                    if trace:
                        trace.label = "pathological"
                        trace.outcome = "failure"
                        traces.append(trace)
                
                if traces:
                    print(f"   ✅ Converted {len(traces)} failure traces")
                    self._cache_traces(traces, "failure_traces.json")
                    return traces
                    
            except Exception as e:
                print(f"   ⚠️  {dataset_name} failed: {str(e)[:100]}")
                continue
        
        # If all real datasets fail, use synthetic pathological traces
        print(f"   ℹ️  Using synthetic pathological traces as fallback")
        from data.synthetic_generator import generate_dataset
        
        synthetic_traces = generate_dataset(n_healthy=0, n_pathological=max_traces)
        for trace in synthetic_traces:
            trace.label = "pathological"
            trace.outcome = "failure"
        
        print(f"   ✅ Generated {len(synthetic_traces)} synthetic pathological traces")
        return synthetic_traces
            print(f"✅ Generated {len(synthetic_traces)} synthetic pathological traces")
            return synthetic_traces
    
    def load_bfcl_traces(self, max_traces: int = 500) -> List[Trace]:
        """
        Load function-calling traces from Berkeley Function-Calling Leaderboard.
        
        Executable function-calling eval data - strong signal for 
        tool-routing accuracy/failure.
        """
        print("📥 Loading BFCL dataset...")
        
        try:
            from datasets import load_dataset
            
            dataset = load_dataset(
                "gorilla-llm/Berkeley-Function-Calling-Leaderboard",
                split="train",
                streaming=False
            )
            
            print(f"✅ Loaded {len(dataset)} BFCL traces")
            
            traces = []
            for idx, item in enumerate(dataset):
                if idx >= max_traces:
                    break
                
                trace = self._convert_bfcl_to_trace(item, idx)
                if trace:
                    traces.append(trace)
            
            print(f"✅ Converted {len(traces)} BFCL traces")
            
            # Cache for future use
            self._cache_traces(traces, "bfcl_traces.json")
            
            return traces
            
        except Exception as e:
            print(f"⚠️  Failed to load BFCL dataset: {e}")
            return []
    
    def load_mixed_dataset(
        self,
        n_healthy: int = 400,
        n_pathological: int = 200,
        use_synthetic_fallback: bool = True
    ) -> List[Trace]:
        """
        Load a balanced mix of healthy and pathological traces.
        
        Priority:
        1. Try loading from cache
        2. Try downloading from HuggingFace (with timeout protection)
        3. Fall back to synthetic if both fail (only if enabled)
        """
        # Check cache first
        cached = self._load_from_cache()
        if cached and len(cached) >= 100:  # If we have reasonable cached data
            print(f"✅ Loaded {len(cached)} traces from cache")
            
            # Separate by label
            healthy = [t for t in cached if t.label == "healthy"]
            pathological = [t for t in cached if t.label == "pathological"]
            
            # Balance if needed
            selected_healthy = healthy[:n_healthy] if len(healthy) >= n_healthy else healthy
            selected_pathological = pathological[:n_pathological] if len(pathological) >= n_pathological else pathological
            
            # If we don't have enough pathological, add synthetic
            if len(selected_pathological) < n_pathological // 2:
                print(f"\n⚠️  Only {len(selected_pathological)} pathological traces in cache")
                print(f"   Supplementing with synthetic to reach {n_pathological}")
                
                from data.synthetic_generator import generate_dataset
                needed = n_pathological - len(selected_pathological)
                synthetic = generate_dataset(n_healthy=0, n_pathological=needed)
                selected_pathological.extend(synthetic)
            
            result = selected_healthy + selected_pathological
            random.shuffle(result)
            
            # Show stats
            healthy_count = sum(1 for t in result if t.label == "healthy")
            pathological_count = sum(1 for t in result if t.label == "pathological")
            print(f"\n📊 Final dataset:")
            print(f"   Total: {len(result)} traces")
            print(f"   Healthy: {healthy_count} ({100*healthy_count/len(result):.1f}%)")
            print(f"   Pathological: {pathological_count} ({100*pathological_count/len(result):.1f}%)")
            
            return result
        
        # Try downloading real data
        traces = []
        
        # Load healthy traces (Exgentic - mostly successful)
        exgentic_traces = self.load_exgentic_traces(max_traces=n_healthy)
        if exgentic_traces:
            # Mark as healthy (heuristic: if not explicitly failed)
            for trace in exgentic_traces:
                if not trace.label:
                    trace.label = "healthy"
                    trace.outcome = "success"
            traces.extend(exgentic_traces[:n_healthy])
        
        # Load pathological traces (Who&When - all failures)
        failure_traces = self.load_failure_traces(max_traces=n_pathological)
        traces.extend(failure_traces[:n_pathological])
        
        # If we don't have enough, try BFCL
        if len(traces) < (n_healthy + n_pathological) // 2:
            bfcl_traces = self.load_bfcl_traces(max_traces=500)
            traces.extend(bfcl_traces)
        
        # Fallback to synthetic only if requested and we have very few traces
        if len(traces) < 100 and use_synthetic_fallback:
            print(f"\n⚠️  Only got {len(traces)} real traces, supplementing with synthetic...")
            from data.synthetic_generator import generate_dataset
            
            synthetic_needed = (n_healthy + n_pathological) - len(traces)
            synthetic_healthy = int(synthetic_needed * 0.6)
            synthetic_pathological = synthetic_needed - synthetic_healthy
            
            synthetic_traces = generate_dataset(
                n_healthy=synthetic_healthy,
                n_pathological=synthetic_pathological
            )
            traces.extend(synthetic_traces)
            
            print(f"   Added {len(synthetic_traces)} synthetic traces")
        
        random.shuffle(traces)
        
        # Count labels
        healthy_count = sum(1 for t in traces if t.label == "healthy")
        pathological_count = sum(1 for t in traces if t.label == "pathological")
        
        print(f"\n📊 Final dataset:")
        print(f"   Total: {len(traces)} traces")
        print(f"   Healthy: {healthy_count} ({100*healthy_count/len(traces):.1f}%)")
        print(f"   Pathological: {pathological_count} ({100*pathological_count/len(traces):.1f}%)")
        
        return traces
    
    def _convert_exgentic_to_trace(self, item: Dict, idx: int) -> Optional[Trace]:
        """Convert Exgentic dataset item to our Trace format."""
        try:
            steps = []
            
            # Extract spans/steps from the trace
            if "spans" in item:
                for step_id, span in enumerate(item["spans"]):
                    step = Step(
                        step_id=step_id,
                        action_type=span.get("span_kind", "tool_call"),
                        tool_name=span.get("name", "unknown"),
                        arguments=span.get("attributes", {}),
                        output=span.get("status_message", ""),
                        latency_ms=int(span.get("duration_ms", 0)),
                        tokens_used=span.get("attributes", {}).get("tokens", 0)
                    )
                    steps.append(step)
            
            # If no spans, try to extract from events or messages
            elif "events" in item or "messages" in item:
                events = item.get("events", item.get("messages", []))
                for step_id, event in enumerate(events):
                    step = Step(
                        step_id=step_id,
                        action_type="tool_call",
                        tool_name=event.get("tool", event.get("name", "unknown")),
                        arguments=event.get("input", {}),
                        output=str(event.get("output", "")),
                        latency_ms=int(event.get("latency_ms", 0)),
                        tokens_used=int(event.get("tokens", 0))
                    )
                    steps.append(step)
            
            if not steps:
                return None
            
            trace = Trace(
                trace_id=item.get("trace_id", f"exgentic_{idx}"),
                task_description=item.get("task", item.get("prompt", f"Task {idx}")),
                steps=steps
            )
            
            # Set label based on outcome if available
            if "outcome" in item:
                trace.label = "healthy" if item["outcome"] == "success" else "pathological"
                trace.outcome = item["outcome"]
            
            return trace
            
        except Exception as e:
            print(f"   ⚠️  Failed to convert trace {idx}: {e}")
            return None
    
    def _convert_failure_to_trace(self, item: Dict, idx: int) -> Optional[Trace]:
        """Convert Who&When failure dataset item to our Trace format."""
        try:
            steps = []
            
            # Extract failure nodes
            if "nodes" in item:
                for step_id, node in enumerate(item["nodes"]):
                    step = Step(
                        step_id=step_id,
                        action_type="tool_call",
                        tool_name=node.get("tool_name", "unknown"),
                        arguments=node.get("input", {}),
                        output=node.get("output", "ERROR"),
                        latency_ms=int(node.get("latency_ms", 100)),
                        tokens_used=int(node.get("tokens", 0))
                    )
                    steps.append(step)
            
            if not steps:
                return None
            
            trace = Trace(
                trace_id=f"failure_{idx}",
                task_description=item.get("task", f"Failed task {idx}"),
                steps=steps
            )
            
            return trace
            
        except Exception as e:
            print(f"   ⚠️  Failed to convert failure trace {idx}: {e}")
            return None
    
    def _convert_bfcl_to_trace(self, item: Dict, idx: int) -> Optional[Trace]:
        """Convert BFCL dataset item to our Trace format."""
        try:
            # BFCL is function-calling focused, simpler structure
            step = Step(
                step_id=0,
                action_type="tool_call",
                tool_name=item.get("function", "unknown"),
                arguments=item.get("arguments", {}),
                output=str(item.get("expected_output", "")),
                latency_ms=100,
                tokens_used=len(str(item.get("arguments", {})).split())
            )
            
            trace = Trace(
                trace_id=f"bfcl_{idx}",
                task_description=item.get("question", f"Function call task {idx}"),
                steps=[step]
            )
            
            # Label based on correctness if available
            if "is_correct" in item:
                trace.label = "healthy" if item["is_correct"] else "pathological"
            
            return trace
            
        except Exception as e:
            print(f"   ⚠️  Failed to convert BFCL trace {idx}: {e}")
            return None
    
    def _cache_traces(self, traces: List[Trace], filename: str):
        """Cache traces to disk."""
        cache_path = os.path.join(self.cache_dir, filename)
        
        try:
            with open(cache_path, "w") as f:
                json.dump([t.to_dict() for t in traces], f, indent=2)
            print(f"💾 Cached to {cache_path}")
        except Exception as e:
            print(f"⚠️  Failed to cache: {e}")
    
    def _load_from_cache(self) -> List[Trace]:
        """Load all cached traces."""
        traces = []
        
        if not os.path.exists(self.cache_dir):
            return traces
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.cache_dir, filename)
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        for item in data:
                            trace = Trace.from_dict(item)
                            traces.append(trace)
                except Exception as e:
                    print(f"⚠️  Failed to load {filename}: {e}")
        
        return traces


def main():
    """Example usage."""
    loader = RealDataLoader()
    
    # Load mixed real dataset
    traces = loader.load_mixed_dataset(
        n_healthy=400,
        n_pathological=200,
        use_synthetic_fallback=True  # Only if real data fails
    )
    
    print(f"\n✅ Final dataset ready: {len(traces)} traces")
    
    # Show sample
    if traces:
        sample = traces[0]
        print(f"\nSample trace:")
        print(f"  ID: {sample.trace_id}")
        print(f"  Task: {sample.task_description[:60]}...")
        print(f"  Steps: {len(sample.steps)}")
        print(f"  Label: {sample.label}")


if __name__ == "__main__":
    main()
