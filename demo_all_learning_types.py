"""Complete demonstration of all three learning types working together.

This script demonstrates:
1. UNSUPERVISED: IsolationForest + HDBSCAN detect anomalies without labels
2. REINFORCEMENT: LinUCB bandit learns optimal actions from rewards
3. SUPERVISED: Feedback loop trains the system based on labeled outcomes
"""
import json
import time

import requests

BASE_URL = "http://localhost:8000"


def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_unsupervised_learning():
    """1. UNSUPERVISED LEARNING - Anomaly detection without labels."""
    print_section("1. UNSUPERVISED LEARNING (IsolationForest + HDBSCAN)")
    
    print("\n📊 The system detects anomalies WITHOUT labels using:")
    print("   - IsolationForest: Isolation-based anomaly score")
    print("   - HDBSCAN: Cluster outlier detection")
    
    # Example 1: Normal trace
    print("\n🟢 Test 1: Normal Agent Behavior")
    normal_trace = {
        "task_description": "Search and summarize weather",
        "steps": [
            {
                "step_id": 0,
                "action_type": "tool_call",
                "tool_name": "search",
                "arguments": {"query": "weather today"},
                "output": "Sunny, 75F",
                "latency_ms": 120,
                "tokens_used": 15
            },
            {
                "step_id": 1,
                "action_type": "tool_call",
                "tool_name": "summarize",
                "arguments": {"text": "Weather is sunny"},
                "output": "Summary: Good weather",
                "latency_ms": 80,
                "tokens_used": 10
            }
        ]
    }
    
    response = requests.post(f"{BASE_URL}/ingest_trace", json=normal_trace)
    result = response.json()
    
    print(f"\n   Isolation Score: {result['isolation_score']:.3f}")
    print(f"   Cluster Outlier: {result['is_cluster_outlier']}")
    print(f"   Combined Score: {result['combined_score']:.3f}")
    print(f"   Is Anomalous: {result['is_anomalous']}")
    print(f"   → System decision: {result['recommended_action']}")
    
    # Example 2: Anomalous trace (looping)
    print("\n🔴 Test 2: Anomalous Agent Behavior (Infinite Loop)")
    looping_trace = {
        "task_description": "Agent stuck repeating same search",
        "steps": [
            {
                "step_id": i,
                "action_type": "tool_call",
                "tool_name": "search",
                "arguments": {"query": "info"},
                "output": "No results found",
                "latency_ms": 100,
                "tokens_used": 10
            }
            for i in range(10)  # Same action repeated 10 times
        ]
    }
    
    response = requests.post(f"{BASE_URL}/ingest_trace", json=looping_trace)
    result = response.json()
    
    print(f"\n   Isolation Score: {result['isolation_score']:.3f}")
    print(f"   Cluster Outlier: {result['is_cluster_outlier']}")
    print(f"   Combined Score: {result['combined_score']:.3f}")
    print(f"   Is Anomalous: {result['is_anomalous']}")
    print(f"   → System decision: {result['recommended_action']}")
    
    print("\n✅ UNSUPERVISED models detected the anomaly without any labels!")
    
    return result['context_summary'], result['recommended_action']


def demo_reinforcement_learning(context_summary: list, action: str):
    """2. REINFORCEMENT LEARNING - LinUCB learns optimal actions."""
    print_section("2. REINFORCEMENT LEARNING (LinUCB Contextual Bandit)")
    
    print("\n🎯 The LinUCB bandit learns which action to take:")
    print("   Actions: continue, retry_step, interrupt_human, escalate_model")
    print("   Context: [mean, std, max, anomaly_score, bias]")
    
    print(f"\n📍 For the anomalous trace:")
    print(f"   Context: {[f'{x:.3f}' for x in context_summary]}")
    print(f"   Chosen Action: '{action}'")
    
    print("\n🔄 The bandit uses Upper Confidence Bound (UCB) to:")
    print("   - EXPLOIT: Choose actions with highest expected reward")
    print("   - EXPLORE: Try uncertain actions to learn more")
    
    print("\n💡 How it decides:")
    print("   UCB = mean_reward + α * sqrt(uncertainty)")
    print("   α controls exploration vs exploitation trade-off")
    
    return context_summary, action


def demo_supervised_learning(context_summary: list, action: str):
    """3. SUPERVISED LEARNING - Feedback trains the system."""
    print_section("3. SUPERVISED LEARNING (Online Learning from Feedback)")
    
    print("\n📝 Now we tell the system what ACTUALLY happened...")
    
    # Simulate real-world outcome
    print("\n   Scenario: The agent eventually succeeded after interruption")
    print("   Outcome: 'success'")
    print("   Steps saved: 5 (would have wasted 5 more steps)")
    print("   Cost saved: $0.50")
    
    # Compute reward (same formula as rl_policy/bandit.py)
    outcome = "success"
    steps_saved = 5
    cost_saved = 0.50
    
    action_penalty = {
        "continue": 0.0,
        "retry_step": -0.1,
        "interrupt_human": -0.3,
        "escalate_model": -0.5,
    }
    
    base_reward = 1.0 if outcome == "success" else -1.0
    reward = base_reward + 0.01 * cost_saved + 0.05 * steps_saved + action_penalty.get(action, 0.0)
    
    print(f"\n📊 Reward Calculation:")
    print(f"   Base (success): +1.0")
    print(f"   Cost saved: +{0.01 * cost_saved:.3f}")
    print(f"   Steps saved: +{0.05 * steps_saved:.3f}")
    print(f"   Action penalty: {action_penalty.get(action, 0.0):.3f}")
    print(f"   → Total Reward: {reward:.3f}")
    
    # Send feedback to update the bandit
    feedback = {
        "context_summary": context_summary,
        "action": action,
        "reward": reward
    }
    
    response = requests.post(f"{BASE_URL}/feedback", json=feedback)
    print(f"\n✅ Feedback sent! Status: {response.json()['status']}")
    
    print("\n🧠 What the bandit learned:")
    print(f"   - Action '{action}' in this context → {reward:.3f} reward")
    print(f"   - Updates internal model: A (covariance) and b (weighted rewards)")
    print(f"   - Next time similar context appears, bandit will be smarter!")
    
    # Demonstrate learning effect
    print("\n📈 Over time, with more feedback:")
    print("   - High-reward actions get selected more often")
    print("   - Low-reward actions are avoided")
    print("   - System adapts to your specific use case")
    print("   - No manual rule writing needed!")


def demo_full_loop():
    """Show how all three types work together in a loop."""
    print_section("COMPLETE LEARNING LOOP")
    
    print("\n🔄 The three learning types work together:")
    print("\n   1. UNSUPERVISED detects anomaly → anomaly_score")
    print("   2. REINFORCEMENT chooses action → recommended_action")
    print("   3. System executes action in real world → outcome")
    print("   4. SUPERVISED feedback updates policy → smarter next time")
    print("   5. Repeat!")
    
    print("\n✨ Benefits:")
    print("   ✓ No manual labeling needed (unsupervised)")
    print("   ✓ Learns optimal actions automatically (RL)")
    print("   ✓ Adapts to your environment (online learning)")
    print("   ✓ Handles distribution shift gracefully")
    print("   ✓ Gets better over time with feedback")


def show_system_stats():
    """Show current system statistics."""
    print_section("SYSTEM STATISTICS")
    
    response = requests.get(f"{BASE_URL}/stats")
    stats = response.json()
    
    print(f"\n   Total Traces Processed: {stats['total_traces']}")
    print(f"   Anomalous Traces: {stats['anomalous_traces']}")
    print(f"   Average Anomaly Score: {stats['avg_combined_score']:.3f}")
    print(f"   Anomaly Rate: {100 * stats['anomalous_traces'] / max(1, stats['total_traces']):.1f}%")


def main():
    """Run complete demonstration."""
    print("\n" + "╔" + "=" * 68 + "╗")
    print("║  AGENT OBSERVABILITY: ALL THREE LEARNING TYPES DEMO           ║")
    print("╚" + "=" * 68 + "╝")
    
    try:
        # Check server is running
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ API server not responding. Start it with:")
            print("   uvicorn api.main:app --reload")
            return
    except Exception:
        print("❌ API server not running! Start it with:")
        print("   .\\venv\\Scripts\\activate")
        print("   uvicorn api.main:app --reload")
        return
    
    print("✅ API server is running\n")
    
    # Demo each learning type
    context, action = demo_unsupervised_learning()
    time.sleep(1)
    
    demo_reinforcement_learning(context, action)
    time.sleep(1)
    
    demo_supervised_learning(context, action)
    time.sleep(1)
    
    demo_full_loop()
    time.sleep(1)
    
    show_system_stats()
    
    print("\n" + "=" * 70)
    print("🎉 DEMO COMPLETE!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Visit http://localhost:8000/docs for interactive API")
    print("2. Send more traces to see the system learn")
    print("3. Provide feedback to train the reinforcement learning policy")
    print("4. Monitor stats at http://localhost:8000/stats")
    print("\n")


if __name__ == "__main__":
    main()
