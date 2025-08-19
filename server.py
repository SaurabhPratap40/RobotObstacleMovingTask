# server.py
import asyncio
import json
import websockets
from flask import Flask, request, jsonify
import threading

app = Flask(__name__)

# --- CORS: allow simple cross-origin calls from control page ---
@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp

# ---------------------------
# Globals
# ---------------------------
connected = set()
async_loop = None
collision_count = 0

# For autopilot / monitor
latest_capture = None   # dict: { "timestamp": ..., "image": "<base64|data:...>", "position": {...} }
latest_event = None     # last event dict

FLOOR_HALF = 50  # index.html uses PlaneGeometry(100, 100) centered at origin

def corner_to_coords(corner: str, margin=5):
    c = corner.upper()
    x = FLOOR_HALF - margin if "E" in c else -(FLOOR_HALF - margin)
    z = FLOOR_HALF - margin if ("S" in c or "B" in c) else -(FLOOR_HALF - margin)
    if c in ("NE", "EN", "TR"): x, z = (FLOOR_HALF - margin, -(FLOOR_HALF - margin))
    if c in ("NW", "WN", "TL"): x, z = (-(FLOOR_HALF - margin), -(FLOOR_HALF - margin))
    if c in ("SE", "ES", "BR"): x, z = (FLOOR_HALF - margin, (FLOOR_HALF - margin))
    if c in ("SW", "WS", "BL"): x, z = (-(FLOOR_HALF - margin), (FLOOR_HALF - margin))
    return {"x": x, "y": 0, "z": z}

# ---------------------------
# WebSocket Handler
# ---------------------------
async def ws_handler(websocket, path=None):
    global collision_count, latest_capture, latest_event
    print("Client connected via WebSocket")
    connected.add(websocket)
    try:
        async for message in websocket:
            # try to parse JSON
            try:
                data = json.loads(message)
            except Exception:
                data = None

            # record capture responses
            if isinstance(data, dict) and data.get("type") == "capture_image_response":
                # store entire payload
                latest_capture = {
                    "timestamp": data.get("timestamp"),
                    "image": data.get("image"),
                    "position": data.get("position"),
                }
                latest_event = {"type": "capture_ack", "timestamp": data.get("timestamp")}
            # record collisions
            if isinstance(data, dict) and data.get("type") == "collision" and data.get("collision"):
                collision_count += 1
                latest_event = data
            # record goal reached and confirmations
            if isinstance(data, dict) and data.get("type") in {"goal_reached", "confirmation"}:
                latest_event = data

            # print (for debugging)
            print("Received from simulator:", message)
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    finally:
        connected.discard(websocket)

def broadcast(msg: dict):
    """Broadcast a JSON message to all connected websocket clients (non-blocking)."""
    if not connected:
        return False
    for ws in list(connected):
        try:
            asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), async_loop)
        except Exception as e:
            print("broadcast error:", e)
    return True

# ---------------------------
# Flask Endpoints (HTTP API)
# ---------------------------
@app.route('/move', methods=['POST'])
def move():
    data = request.get_json()
    if not data or 'x' not in data or 'z' not in data:
        return jsonify({'error': 'Missing parameters. Please provide "x" and "z".'}), 400
    x, z = float(data['x']), float(data['z'])
    msg = {"command": "move", "target": {"x": x, "y": 0, "z": z}}
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'move command sent', 'command': msg})

@app.route('/move_rel', methods=['POST'])
def move_rel():
    data = request.get_json()
    if not data or 'turn' not in data or 'distance' not in data:
        return jsonify({'error': 'Missing parameters. Please provide "turn" and "distance".'}), 400
    msg = {"command": "move_relative", "turn": float(data['turn']), "distance": float(data['distance'])}
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'move relative command sent', 'command': msg})

@app.route('/stop', methods=['POST'])
def stop():
    msg = {"command": "stop"}
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'stop command sent', 'command': msg})

@app.route('/capture', methods=['POST'])
def capture():
    msg = {"command": "capture_image"}
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'capture command sent', 'command': msg})

@app.route('/goal', methods=['POST'])
def set_goal():
    data = request.get_json() or {}
    if 'corner' in data:
        pos = corner_to_coords(str(data['corner']))
    elif 'x' in data and 'z' in data:
        pos = {"x": float(data['x']), "y": float(data.get('y', 0)), "z": float(data['z'])}
    else:
        return jsonify({'error': 'Provide {"corner":"NE|NW|SE|SW"} OR {"x":..,"z":..}'}), 400

    msg = {"command": "set_goal", "position": pos}
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'goal set', 'goal': pos})

@app.route('/obstacles/positions', methods=['POST'])
def set_obstacle_positions():
    data = request.get_json() or {}
    positions = data.get('positions')
    if not isinstance(positions, list) or not positions:
        return jsonify({'error': 'Provide "positions" as a non-empty list.'}), 400

    norm = []
    for p in positions:
        if not isinstance(p, dict) or 'x' not in p or 'z' not in p:
            return jsonify({'error': 'Each position needs "x" and "z".'}), 400
        norm.append({"x": float(p['x']), "y": float(p.get('y', 2)), "z": float(p['z'])})

    msg = {"command": "set_obstacles", "positions": norm}
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'obstacles updated', 'count': len(norm)})

@app.route('/obstacles/motion', methods=['POST'])
def set_obstacle_motion():
    data = request.get_json() or {}
    if 'enabled' not in data:
        return jsonify({'error': 'Missing "enabled" boolean.'}), 400

    msg = {
        "command": "set_obstacle_motion",
        "enabled": bool(data['enabled']),
        "speed": float(data.get('speed', 0.05)),
        "velocities": data.get('velocities'),
        "bounds": data.get('bounds', {"minX": -45, "maxX": 45, "minZ": -45, "maxZ": 45}),
        "bounce": bool(data.get('bounce', True)),
    }
    if not broadcast(msg):
        return jsonify({'error': 'No connected simulators.'}), 400
    return jsonify({'status': 'obstacle motion updated', 'config': msg})

# ---------------------------
# Collisions / Reset / Latest capture/event endpoints
# ---------------------------
@app.route('/collisions', methods=['GET'])
def get_collisions():
    return jsonify({'count': collision_count})

@app.route('/reset', methods=['POST'])
def reset():
    global collision_count
    collision_count = 0
    if not broadcast({"command": "reset"}):
        return jsonify({'status': 'reset done (no simulators connected)', 'collisions': collision_count})
    return jsonify({'status': 'reset broadcast', 'collisions': collision_count})

@app.route('/latest_capture', methods=['GET'])
def get_latest_capture():
    """Returns the latest capture. ?meta=1 returns metadata without the full image."""
    global latest_capture
    if latest_capture is None:
        return jsonify({'available': False}), 200
    if request.args.get('meta') == '1':
        meta = {k: v for k, v in latest_capture.items() if k != 'image'}
        meta['available'] = True
        return jsonify(meta), 200
    resp = dict(latest_capture)
    resp['available'] = True
    return jsonify(resp), 200

@app.route('/latest_event', methods=['GET'])
def get_latest_event():
    global latest_event
    if latest_event is None:
        return jsonify({'available': False}), 200
    resp = dict(latest_event)
    resp['available'] = True
    return jsonify(resp), 200

# ---------------------------
# Flask Thread
# ---------------------------
def start_flask():
    app.run(port=5000)

# ---------------------------
# Main Async for WebSocket (port 8080)
# ---------------------------
async def main():
    global async_loop
    async_loop = asyncio.get_running_loop()
    ws_server = await websockets.serve(ws_handler, "localhost", 8080)
    print("WebSocket server started on ws://localhost:8080")
    await ws_server.wait_closed()

# ---------------------------
# Entry
# ---------------------------
if __name__ == "__main__":
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    asyncio.run(main())
