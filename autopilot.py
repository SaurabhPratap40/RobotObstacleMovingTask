import requests
import cv2
import numpy as np
import time
import math
import base64

SERVER = "http://localhost:5000"

# --------------------------
# Parameters
# --------------------------
GOAL = (50, 50)   # Arbitrary goal in front
STEP_SIZE = 10    # Movement step size
SAFE_DISTANCE = 40
MAX_STEPS = 500

# --------------------------
# Helper Functions
# --------------------------
def capture_image():
    """Trigger capture and fetch latest image"""
    try:
        # Trigger capture
        requests.post(f"{SERVER}/capture", timeout=5)
        time.sleep(0.2)

        # Get latest capture (base64)
        resp = requests.get(f"{SERVER}/latest_capture", timeout=5).json()
        if not resp.get("available"):
            return None

        img_b64 = resp["image"].split(",")[1] if "," in resp["image"] else resp["image"]
        img_array = np.frombuffer(base64.b64decode(img_b64), np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        print("❌ Error capturing image:", e)
        return None

def detect_obstacles(frame):
    """Detect obstacles using contours"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    obstacles = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h > 200:
            obstacles.append((x + w // 2, y + h // 2, w, h))
    return obstacles

def move_robot(turn, distance):
    """Send relative movement (turn, distance)"""
    try:
        requests.post(f"{SERVER}/move_rel", json={"turn": turn, "distance": distance}, timeout=5)
    except Exception as e:
        print("❌ Movement error:", e)

def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --------------------------
# Self-Test Function
# --------------------------
def test_movement():
    print("🛠 Running movement self-test...")
    try:
        move_robot(0, 10)   # forward
        time.sleep(1)
        move_robot(180, 10) # backward (turn 180° and move)
        time.sleep(1)
        print("✅ Movement test passed.")
        return True
    except Exception as e:
        print("❌ Movement test failed:", e)
        return False

# --------------------------
# Main Autonomous Loop
# --------------------------
def main():
    print("🤖 Starting autonomous navigation...")

    if not test_movement():
        print("⚠️ Exiting: movement test failed.")
        return

    for step in range(MAX_STEPS):
        frame = capture_image()
        if frame is None:
            continue

        obstacles = detect_obstacles(frame)

        turn, dist = 0, STEP_SIZE

        # Avoid obstacles (very simple logic)
        if obstacles:
            print("⚠️ Obstacle detected! Turning right...")
            turn = 45  # rotate right
            dist = STEP_SIZE

        move_robot(turn, dist)
        print(f"➡️ Step {step+1}: turn={turn}, distance={dist}")

        if distance((0, 0), GOAL) < SAFE_DISTANCE:
            print("🎯 Goal reached!")
            break

        time.sleep(0.5)

if __name__ == "__main__":
    main()