# test_move.py
import requests
API = "http://localhost:5000"

def try_move():
    payload = {"x": 5, "z": 0}
    r = requests.post(API + "/move", json=payload, timeout=3)
    print("move ->", r.status_code, r.text)

def try_goal():
    r = requests.post(API + "/goal", json={"corner": "NE"}, timeout=3)
    print("goal ->", r.status_code, r.text)

def try_capture():
    r = requests.post(API + "/capture", timeout=3)
    print("capture ->", r.status_code, r.text)

def latest_cap_meta():
    r = requests.get(API + "/latest_capture?meta=1", timeout=3)
    print("latest_capture meta ->", r.status_code, r.text)

if __name__ == "__main__":
    try_move()
    try_goal()
    try_capture()
    latest_cap_meta()
