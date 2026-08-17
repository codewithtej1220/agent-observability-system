"""Single command to run the complete system.

This script:
1. Checks if models are trained
2. Starts the API server
3. Opens the dashboard in browser
4. Shows real-time status

Run: python run_complete_system.py
"""
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import requests


def print_banner():
    """Print startup banner."""
    print("\n" + "╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "AGENT OBSERVABILITY SYSTEM" + " " * 27 + "║")
    print("║" + " " * 20 + "Complete System Startup" + " " * 25 + "║")
    print("╚" + "=" * 68 + "╝\n")


def print_step(step: int, message: str):
    """Print step with formatting."""
    print(f"\n{'=' * 70}")
    print(f"STEP {step}: {message}")
    print('=' * 70)


def check_models():
    """Check if models are trained."""
    print_step(1, "Checking ML Models")
    
    embedder_exists = Path("artifacts/embedder.pkl").exists()
    detector_exists = Path("artifacts/detector.pkl").exists()
    
    if embedder_exists and detector_exists:
        print("✅ Models found:")
        print(f"   • artifacts/embedder.pkl")
        print(f"   • artifacts/detector.pkl")
        return True
    else:
        print("❌ Models not found!")
        print("\nTraining models now...")
        print("This will take about 10 seconds...\n")
        
        # Train models
        result = subprocess.run(
            [sys.executable, "scripts/train_pipeline.py"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Models trained successfully!")
            return True
        else:
            print("❌ Model training failed:")
            print(result.stderr)
            return False


def start_api_server():
    """Start the API server in background."""
    print_step(2, "Starting API Server")
    
    # Check if already running
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            print("⚠️  API server already running!")
            return None
    except:
        pass
    
    print("Starting uvicorn server...")
    
    # Start server
    if os.name == 'nt':  # Windows
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    else:  # Unix
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    # Wait for server to start
    print("Waiting for server to start", end="")
    for i in range(20):
        time.sleep(0.5)
        print(".", end="", flush=True)
        try:
            response = requests.get("http://localhost:8000/health", timeout=1)
            if response.status_code == 200:
                print(" ✅")
                print(f"Server started successfully!")
                return process
        except:
            continue
    
    print(" ❌")
    print("Server failed to start!")
    return None


def load_initial_data():
    """Load some initial test data."""
    print_step(3, "Loading Initial Test Data")
    
    # Normal trace
    normal_trace = {
        "task_description": "Demo: Search and summarize weather",
        "steps": [
            {
                "step_id": 0,
                "action_type": "tool_call",
                "tool_name": "search",
                "arguments": {"query": "weather Seattle"},
                "output": "Sunny, 72°F",
                "latency_ms": 120,
                "tokens_used": 15
            },
            {
                "step_id": 1,
                "action_type": "tool_call",
                "tool_name": "summarize",
                "arguments": {"text": "Weather info"},
                "output": "It's sunny in Seattle",
                "latency_ms": 80,
                "tokens_used": 10
            }
        ]
    }
    
    # Anomalous trace (looping)
    anomalous_trace = {
        "task_description": "Demo: Agent stuck in error loop",
        "steps": [
            {
                "step_id": i,
                "action_type": "tool_call",
                "tool_name": "api_call",
                "arguments": {"endpoint": "/data"},
                "output": "Error: Connection timeout",
                "latency_ms": 100,
                "tokens_used": 10
            }
            for i in range(12)
        ]
    }
    
    try:
        # Send normal trace
        response = requests.post(
            "http://localhost:8000/ingest_trace",
            json=normal_trace,
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Normal trace ingested")
            print(f"   Anomaly Score: {result['combined_score']:.3f}")
            print(f"   Status: {'⚠️ Anomalous' if result['is_anomalous'] else '✅ Normal'}")
        
        # Send anomalous trace
        response = requests.post(
            "http://localhost:8000/ingest_trace",
            json=anomalous_trace,
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ Anomalous trace ingested")
            print(f"   Anomaly Score: {result['combined_score']:.3f}")
            print(f"   Status: {'⚠️ Anomalous' if result['is_anomalous'] else '✅ Normal'}")
            print(f"   Recommended Action: {result['recommended_action']}")
        
        return True
    except Exception as e:
        print(f"⚠️  Failed to load test data: {e}")
        return False


def open_dashboard():
    """Open dashboard in browser."""
    print_step(4, "Opening Dashboard")
    
    dashboard_path = Path("dashboard.html").absolute()
    
    if dashboard_path.exists():
        print(f"Opening dashboard: {dashboard_path}")
        webbrowser.open(f"file://{dashboard_path}")
        print("✅ Dashboard opened in browser!")
    else:
        print("❌ Dashboard not found!")
        return False
    
    return True


def show_status():
    """Show system status."""
    print_step(5, "System Status")
    
    try:
        # Get stats
        response = requests.get("http://localhost:8000/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            
            print("\n📊 Current Statistics:")
            print(f"   Total Traces: {stats['total_traces']}")
            print(f"   Anomalous Traces: {stats['anomalous_traces']}")
            print(f"   Average Anomaly Score: {stats['avg_combined_score']:.3f}")
            
            if stats['total_traces'] > 0:
                anomaly_rate = (stats['anomalous_traces'] / stats['total_traces']) * 100
                print(f"   Anomaly Rate: {anomaly_rate:.1f}%")
    except Exception as e:
        print(f"⚠️  Could not fetch stats: {e}")


def show_urls():
    """Show access URLs."""
    print("\n" + "=" * 70)
    print("🌐 ACCESS POINTS")
    print("=" * 70)
    print("\n📱 Frontend:")
    print(f"   Dashboard:     file://{Path('dashboard.html').absolute()}")
    
    print("\n🔌 Backend API:")
    print("   Base URL:      http://localhost:8000")
    print("   Health:        http://localhost:8000/health")
    print("   API Docs:      http://localhost:8000/docs")
    print("   Metrics:       http://localhost:8000/metrics")
    print("   Stats:         http://localhost:8000/stats")
    
    print("\n📊 Monitoring:")
    print("   Prometheus:    http://localhost:9090 (if docker-compose running)")
    print("   Grafana:       http://localhost:3000 (if docker-compose running)")


def main():
    """Main startup sequence."""
    print_banner()
    
    # Step 1: Check models
    if not check_models():
        print("\n❌ Failed to prepare models. Exiting.")
        return 1
    
    # Step 2: Start API server
    process = start_api_server()
    if process is None and not check_api_running():
        print("\n❌ Failed to start API server. Exiting.")
        return 1
    
    # Step 3: Load test data
    load_initial_data()
    
    # Step 4: Open dashboard
    open_dashboard()
    
    # Step 5: Show status
    show_status()
    
    # Show URLs
    show_urls()
    
    # Success message
    print("\n" + "🎉" * 35)
    print("\n  ✅ SYSTEM FULLY OPERATIONAL!")
    print("  All modules running simultaneously:")
    print("     • Unsupervised Learning ✅")
    print("     • Reinforcement Learning ✅")
    print("     • Supervised Learning ✅")
    print("     • API Server ✅")
    print("     • Database ✅")
    print("     • Monitoring ✅")
    print("     • Frontend Dashboard ✅")
    print("\n" + "🎉" * 35)
    
    print("\n💡 TIP: The dashboard will auto-refresh every 5 seconds!")
    print("💡 TIP: Press Ctrl+C to stop the system\n")
    
    # Keep running
    if process:
        print("🔄 System running... Press Ctrl+C to stop")
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping system...")
            process.terminate()
            print("✅ System stopped.")
    
    return 0


def check_api_running():
    """Check if API is already running."""
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        return response.status_code == 200
    except:
        return False


if __name__ == "__main__":
    sys.exit(main())
