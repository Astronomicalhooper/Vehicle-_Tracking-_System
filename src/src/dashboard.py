""
Vehicle Tracker — Live Map Dashboard
Subscribes to MQTT and plots coordinates on a map using matplotlib.
Run alongside tracker.py to visualize the route.
 
Usage:
  python dashboard.py
"""
 
import json
import time
import threading
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
from datetime import datetime
 
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Install paho-mqtt: pip install paho-mqtt")
    exit(1)
 
MQTT_BROKER   = "broker.hivemq.com"
MQTT_PORT     = 1883
VEHICLE_ID    = "VEH-001"
MAX_POINTS    = 200   # trail length on map
 
lats   = deque(maxlen=MAX_POINTS)
lons   = deque(maxlen=MAX_POINTS)
speeds = deque(maxlen=MAX_POINTS)
lock   = threading.Lock()
last_info = {}
 
def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload)
        with lock:
            if "location" in msg.topic:
                lats.append(data["lat"])
                lons.append(data["lon"])
                speeds.append(data.get("speed_kmh", 0))
                last_info.update(data)
    except Exception:
        pass
 
def animate(frame):
    with lock:
        if len(lats) < 2:
            return
        xs = list(lons)
        ys = list(lats)
        spd = list(speeds)
 
    ax.clear()
    sc = ax.scatter(xs, ys, c=spd, cmap="RdYlGn_r", vmin=0, vmax=120,
                    s=10, zorder=3)
    ax.plot(xs, ys, "b-", linewidth=0.5, alpha=0.4, zorder=2)
    ax.plot(xs[-1], ys[-1], "ro", markersize=10, zorder=4, label="Current")
 
    info = last_info
    title = (f"Vehicle {VEHICLE_ID}  |  "
             f"Speed: {info.get('speed_kmh','--')} km/h  |  "
             f"Sats: {info.get('satellites','--')}  |  "
             f"HDOP: {info.get('hdop','--')}")
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
 
client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT)
client.subscribe(f"vehicle/{VEHICLE_ID}/#")
client.loop_start()
 
fig, ax = plt.subplots(figsize=(10, 6))
fig.colorbar(plt.cm.ScalarMappable(cmap="RdYlGn_r",
             norm=plt.Normalize(0, 120)), ax=ax, label="Speed (km/h)")
 
ani = animation.FuncAnimation(fig, animate, interval=2000)
plt.tight_layout()
plt.show()
client.loop_stop()
