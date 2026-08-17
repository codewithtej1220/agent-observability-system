"""Real-world data collection from multiple sources for training.

Sources:
1. LangSmith dataset - Real LLM agent traces
2. AgentBench dataset - Agent execution logs
3. Your own production traces via API export
4. HuggingFace datasets with agent interactions
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests


class DataCollector:
    """Collect real agent traces from various sources."""

    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def collect_from_langsmith(
        self, api_key: Optional[str] = None, dataset_name: str = "agent-traces"
    ) -> List[Dict[str, Any]]:
        """
        Collect traces from LangSmith.
        
        Get API key from: https://smith.langchain.com/settings
        
        Returns:
            List of trace dictionaries
        """
        if not api_key:
            api_key = os.environ.get("LANGSMITH_API_KEY")
            if not api_key:
                print("⚠️  LangSmith API key not found. Set LANGSMITH_API_KEY env var.")
                return []

        print(f"📥 Collecting from LangSmith dataset: {dataset_name}")
        
        headers = {"x-api-key": api_key}
        base_url = "https://api.smith.langchain.com/v1"
        
        try:
            # Get dataset
            response = requests.get(
                f"{base_url}/datasets",
                headers=headers,
                params={"name": dataset_name}
            )
            response.raise_for_status()
            
            datasets = response.json()
            if not datasets:
                print(f"⚠️  No dataset found with name '{dataset_name}'")
                return []
            
            dataset_id = datasets[0]["id"]
            
            # Get runs from dataset
            response = requests.get(
                f"{base_url}/runs",
                headers=headers,
                params={"dataset": dataset_id, "limit": 1000}
            )
            response.raise_for_status()
            
            traces = response.json()
            print(f"✅ Collected {len(traces)} traces from LangSmith")
            
            # Cache the data
            cache_path = os.path.join(self.cache_dir, "langsmith_traces.json")
            with open(cache_path, "w") as f:
                json.dump(traces, f, indent=2)
            
            return traces
            
        except Exception as e:
            print(f"❌ Error collecting from LangSmith: {e}")
            return []

    def collect_from_huggingface(
        self, dataset_name: str = "AgentInstruct/AgentInstruct"
    ) -> List[Dict[str, Any]]:
        """
        Collect agent interaction data from HuggingFace.
        
        Good datasets:
        - AgentInstruct/AgentInstruct
        - taide/TAIDE-LX-10B-Chat-Alpaca
        - m-a-p/Code-Feedback
        
        Returns:
            List of converted traces
        """
        print(f"📥 Collecting from HuggingFace: {dataset_name}")
        
        try:
            from datasets import load_dataset
            
            dataset = load_dataset(dataset_name, split="train[:1000]")  # First 1000
            traces = []
            
            for idx, item in enumerate(dataset):
                # Convert HF format to our trace format
                trace = self._convert_hf_to_trace(item, idx)
                if trace:
                    traces.append(trace)
            
            print(f"✅ Collected {len(traces)} traces from HuggingFace")
            
            # Cache the data
            cache_path = os.path.join(self.cache_dir, f"hf_{dataset_name.replace('/', '_')}.json")
            with open(cache_path, "w") as f:
                json.dump(traces, f, indent=2)
            
            return traces
            
        except Exception as e:
            print(f"❌ Error collecting from HuggingFace: {e}")
            print("   Install with: pip install datasets")
            return []

    def collect_from_api_export(self, db_path: str = "traces.db") -> List[Dict[str, Any]]:
        """
        Export traces from your own production database.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            List of trace dictionaries
        """
        print(f"📥 Collecting from local database: {db_path}")
        
        import sqlite3
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT trace_id, task_description, trace_json, 
                       combined_score, is_anomalous
                FROM traces
            """)
            
            traces = []
            for row in cursor.fetchall():
                trace_id, task_desc, trace_json, score, is_anomalous = row
                trace = json.loads(trace_json)
                trace["label"] = "pathological" if is_anomalous else "healthy"
                trace["anomaly_score"] = score
                traces.append(trace)
            
            conn.close()
            
            print(f"✅ Collected {len(traces)} traces from local DB")
            return traces
            
        except Exception as e:
            print(f"❌ Error collecting from database: {e}")
            return []

    def collect_from_json_files(self, directory: str) -> List[Dict[str, Any]]:
        """
        Load traces from JSON files in a directory.
        
        Args:
            directory: Path to directory containing JSON trace files
            
        Returns:
            List of trace dictionaries
        """
        print(f"📥 Collecting from JSON files in: {directory}")
        
        traces = []
        
        try:
            for filename in os.listdir(directory):
                if filename.endswith(".json"):
                    filepath = os.path.join(directory, filename)
                    with open(filepath, "r") as f:
                        data = json.load(f)
                        
                        # Handle both single trace and list of traces
                        if isinstance(data, list):
                            traces.extend(data)
                        else:
                            traces.append(data)
            
            print(f"✅ Collected {len(traces)} traces from JSON files")
            return traces
            
        except Exception as e:
            print(f"❌ Error collecting from JSON files: {e}")
            return []

    def _convert_hf_to_trace(self, item: Dict[str, Any], idx: int) -> Optional[Dict[str, Any]]:
        """Convert HuggingFace dataset item to our trace format."""
        try:
            # This is a generic converter - you may need to customize based on dataset structure
            steps = []
            
            # Try to extract conversation/messages
            if "messages" in item:
                for step_id, msg in enumerate(item["messages"]):
                    steps.append({
                        "step_id": step_id,
                        "action_type": "message",
                        "tool_name": msg.get("role", "assistant"),
                        "arguments": {},
                        "output": msg.get("content", ""),
                        "latency_ms": 0,
                        "tokens_used": len(msg.get("content", "").split())
                    })
            
            # Try to extract tool calls
            elif "tools" in item or "actions" in item:
                actions = item.get("tools", item.get("actions", []))
                for step_id, action in enumerate(actions):
                    steps.append({
                        "step_id": step_id,
                        "action_type": "tool_call",
                        "tool_name": action.get("name", "unknown"),
                        "arguments": action.get("arguments", {}),
                        "output": action.get("output", ""),
                        "latency_ms": action.get("latency_ms", 0),
                        "tokens_used": action.get("tokens", 0)
                    })
            
            if not steps:
                return None
            
            return {
                "trace_id": f"hf_{idx}",
                "task_description": item.get("instruction", item.get("input", "task")),
                "steps": steps,
                "label": "healthy"  # Default to healthy, you'll need to label later
            }
            
        except Exception:
            return None

    def load_cached_data(self) -> List[Dict[str, Any]]:
        """Load all cached data."""
        all_traces = []
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.cache_dir, filename)
                with open(filepath, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_traces.extend(data)
                    else:
                        all_traces.append(data)
        
        return all_traces


def main():
    """Example usage."""
    collector = DataCollector()
    
    # Collect from multiple sources
    all_traces = []
    
    # 1. From HuggingFace (easiest, no auth required)
    hf_traces = collector.collect_from_huggingface("AgentInstruct/AgentInstruct")
    all_traces.extend(hf_traces)
    
    # 2. From LangSmith (requires API key)
    # ls_traces = collector.collect_from_langsmith()
    # all_traces.extend(ls_traces)
    
    # 3. From local JSON files
    # json_traces = collector.collect_from_json_files("data/raw_traces")
    # all_traces.extend(json_traces)
    
    # 4. From production database
    # db_traces = collector.collect_from_api_export("traces.db")
    # all_traces.extend(db_traces)
    
    print(f"\n📊 Total traces collected: {len(all_traces)}")
    
    # Save combined dataset
    output_path = os.path.join(collector.cache_dir, "combined_dataset.json")
    with open(output_path, "w") as f:
        json.dump(all_traces, f, indent=2)
    
    print(f"💾 Saved combined dataset to: {output_path}")


if __name__ == "__main__":
    main()
