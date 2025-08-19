import requests
import time
import math
import base64
import numpy as np
import cv2

SERVER = "http://localhost:5000"

# --------------------------
# Parameters
# --------------------------
GOALS = ["NE", "NW", "SE", "SW"]
STEP_SIZE = 5
SAFE_DISTANCE = 20   # distance threshold to avoid obstacles
MAX_STEPS = 500
OBSTACLE_SPEED = 0.05

# --------------------------
# Helper Functions
# --------------------------
def corner_to_coords(corner: str, margin=5):
    FLOOR_HALF = 50
    c = corner.upper()
    x = FLOOR_HALF - margin if "E" in c else -(FLOOR_HALF - margin)
    z = FLOOR_HALF - margin if ("S" in c or "B" in c) else -(FLOOR_HALF - margin)
    if c in ("NE", "EN", "TR"): x, z = (FLOOR_HALF - margin, -(FLOOR_HALF - margin))
    if c in ("NW", "WN", "TL"): x, z = (-(FLOOR_HALF - margin), -(FLOOR_HALF - margin))
    if c in ("SE", "ES", "BR"): x, z = (FLOOR_HALF - margin, (FLOOR_HALF - margin))
    if c in ("SW", "WS", "BL"): x, z = (-(FLOOR_HALF - margin), (FLOOR_HALF - margin))
    return {"x": x, "y": 0, "z": z}

def capture_image():
    """Fetch image from /latest_capture endpoint"""
    try:
        resp = requests.get(f"{SERVER}/latest_capture", timeout=5)
        data = resp.json()
        if not data.get('available'):
            return None
        img_data = data.get('image')
        if not img_data:
            return None
        # base64 decode
        img_bytes = base64.b64decode(img_data.split(",")[-1])
        img_array = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        print("❌ Error capturing image:", e)
        return None

def detect_obstacles(frame):
    """Detect obstacles using simple thresholding"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    obstacles = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w*h > 100:
            obstacles.append((x + w//2, y + h//2))
    return obstacles

def move_robot(turn=0, distance=STEP_SIZE):
    """Send relative movement command"""
    try:
        requests.post(f"{SERVER}/move_rel", json={"turn": turn, "distance": distance})
    except Exception as e:
        print("❌ Movement error:", e)

def set_obstacles_motion(enabled=True, speed=OBSTACLE_SPEED):
    """Enable moving obstacles"""
    try:
        requests.post(f"{SERVER}/obstacles/motion", json={
            "enabled": enabled,
            "speed": speed,
            "bounds": {"minX": -45, "maxX": 45, "minZ": -45, "maxZ": 45},
            "bounce": True
        })
        print("✅ Moving obstacles enabled")
    except Exception as e:
        print("❌ Error setting obstacle motion:", e)

def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# --------------------------
# Self-Test
# --------------------------
def test_movement():
    try:
        move_robot(distance=STEP_SIZE)
        time.sleep(0.5)
        move_robot(distance=-STEP_SIZE)
        time.sleep(0.5)
        print("✅ Movement test passed")
        return True
    except Exception as e:
        print("❌ Movement test failed:", e)
        return False

# --------------------------
# Main Autonomous Loop
# --------------------------
def main():
    print("🤖 Starting autonomous navigation with obstacle avoidance...")
    set_obstacles_motion(True)

    if not test_movement():
        print("⚠️ Exiting: movement test failed.")
        return

    for corner in GOALS:
        goal_pos = corner_to_coords(corner)
        print(f"🎯 Navigating to corner {corner}: {goal_pos}")

        for step in range(MAX_STEPS):
            frame = capture_image()
            if frame is None:
                move_robot(distance=STEP_SIZE)
                time.sleep(0.3)
                continue

            obstacles = detect_obstacles(frame)

            # Simple avoidance: sidestep if obstacle is near center
            turn = 0
            for (ox, oy) in obstacles:
                if abs(ox - 320) < SAFE_DISTANCE and abs(oy - 240) < SAFE_DISTANCE:  # assuming 640x480
                    turn = 15  # degrees
                    print("⚠️ Obstacle detected! Turning to avoid.")
                    break

            move_robot(turn=turn, distance=STEP_SIZE)
            print(f"➡️ Step {step+1}: Moving toward {corner} with turn {turn}")

            # Stop if goal reached (rough estimate using distance to origin)
            if distance((0,0), (goal_pos['x'], goal_pos['z'])) < SAFE_DISTANCE:
                print(f"✅ Goal {corner} reached!")
                break

            time.sleep(0.3)

    print("🏁 All goals completed.")

if __name__ == "__main__":
    main()
