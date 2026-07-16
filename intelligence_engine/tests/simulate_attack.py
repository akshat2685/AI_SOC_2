import time
import requests

def run_atomic_red_team_replay():
    print("Starting Atomic Red Team simulation...")
    techniques = ["T1059.001", "T1078", "T1110"]
    for t in techniques:
        print(f"Simulating {t}...")
        time.sleep(1)
        try:
            requests.post("http://localhost:8000/api/alerts", json={
                "technique": t,
                "severity": "HIGH",
                "message": f"Simulated attack {t} detected"
            })
            print(f"Alert sent for {t}")
        except Exception as e:
            print(f"Failed to send alert for {t}: {e}")

if __name__ == "__main__":
    run_atomic_red_team_replay()
