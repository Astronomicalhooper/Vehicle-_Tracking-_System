#!/usr/bin/env python3
"""
Vehicle Tracking System
Author : Samuel Nathan Bobai
Platform: Raspberry Pi (any model with UART + Internet)
Description:
  Reads raw NMEA sentences from a GPS module via UART,
  parses and validates coordinates, filters noise/invalid
  readings, then publishes clean location data to an MQTT
  broker in real time.
 
Hardware wiring:
  GPS Module TX  → Raspberry Pi GPIO15 (UART RX / Pin 10)
  GPS Module RX  → Raspberry Pi GPIO14 (UART TX / Pin 8)   [optional]
  GPS Module VCC → 3.3 V (Pin 1)
  GPS Module GND → GND   (Pin 6)
 
Dependencies:
  pip install paho-mqtt pyserial
 
MQTT topics:
  vehicle/location   →  { lat, lon, speed_kmh, heading, timestamp }
  vehicle/status     →  { fix, satellites, hdop }
  vehicle/alerts     →  string alerts (lost fix, speed limit, etc.)
"""
 
import serial
import json
import time
import math
import logging
from datetime import datetime, timezone
 
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("[WARN] paho-mqtt not installed — MQTT publishing disabled")
 
# ── Configuration ─────────────────────────────────────────
SERIAL_PORT   = "/dev/ttyS0"     # change to /dev/ttyAMA0 or /dev/ttyUSB0 as needed
BAUD_RATE     = 9600
MQTT_BROKER   = "broker.hivemq.com"   # free public broker for testing
MQTT_PORT     = 1883
MQTT_CLIENT_ID= "vehicle_tracker_snb"
VEHICLE_ID    = "VEH-001"
 
SPEED_LIMIT_KMH   = 120.0   # alert if exceeded
MIN_SATELLITES    = 4       # minimum fix quality
MAX_HDOP          = 5.0     # horizontal dilution of precision limit
PUBLISH_INTERVAL  = 2.0     # seconds between publishes (rate-limit)
 
# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("tracker")
 
# ─────────────────────────────────────────────────────────
def nmea_checksum(sentence: str) -> bool:
    """Validate NMEA checksum (XOR of bytes between $ and *)."""
    if "*" not in sentence:
        return False
    data, checksum = sentence[1:].split("*", 1)
    calculated = 0
    for ch in data:
        calculated ^= ord(ch)
    return calculated == int(checksum[:2], 16)
 
 
def parse_gprmc(sentence: str) -> dict | None:
    """
    Parse $GPRMC sentence.
    Returns dict with lat, lon, speed_kmh, heading, timestamp or None.
    """
    if not nmea_checksum(sentence):
        log.debug("Checksum fail: %s", sentence[:40])
        return None
 
    parts = sentence.split(",")
    if len(parts) < 10:
        return None
 
    status = parts[2]   # A = active, V = void
    if status != "A":
        log.debug("GPS void — no fix")
        return None
 
    try:
        # Time
        raw_time = parts[1]
        utc_time = f"{raw_time[0:2]}:{raw_time[2:4]}:{raw_time[4:6]}" if len(raw_time) >= 6 else "00:00:00"
 
        # Latitude
        lat_raw  = parts[3]
        lat_dir  = parts[4]
        lat_deg  = float(lat_raw[:2])
        lat_min  = float(lat_raw[2:])
        lat      = lat_deg + lat_min / 60.0
        if lat_dir == "S":
            lat = -lat
 
        # Longitude
        lon_raw  = parts[5]
        lon_dir  = parts[6]
        lon_deg  = float(lon_raw[:3])
        lon_min  = float(lon_raw[3:])
        lon      = lon_deg + lon_min / 60.0
        if lon_dir == "W":
            lon = -lon
 
        # Speed & heading
        speed_knots = float(parts[7]) if parts[7] else 0.0
        speed_kmh   = speed_knots * 1.852
        heading     = float(parts[8]) if parts[8] else 0.0
 
        return {
            "lat":       round(lat, 6),
            "lon":       round(lon, 6),
            "speed_kmh": round(speed_kmh, 1),
            "heading":   round(heading, 1),
            "utc_time":  utc_time,
        }
    except (ValueError, IndexError) as e:
        log.debug("Parse error: %s", e)
        return None
 
 
def parse_gpgga(sentence: str) -> dict | None:
    """
    Parse $GPGGA for fix quality data (satellites, HDOP).
    """
    if not nmea_checksum(sentence):
        return None
    parts = sentence.split(",")
    if len(parts) < 10:
        return None
    try:
        fix_quality = int(parts[6])   # 0=no fix, 1=GPS, 2=DGPS
        satellites  = int(parts[7])   if parts[7] else 0
        hdop        = float(parts[8]) if parts[8] else 99.9
        altitude_m  = float(parts[9]) if parts[9] else 0.0
        return {
            "fix":        fix_quality,
            "satellites": satellites,
            "hdop":       hdop,
            "altitude_m": altitude_m,
        }
    except (ValueError, IndexError):
        return None
 
 
def is_valid_fix(gga: dict) -> bool:
    """Filter out low-quality fixes."""
    if gga is None:
        return False
    return (gga["fix"] > 0
            and gga["satellites"] >= MIN_SATELLITES
            and gga["hdop"] <= MAX_HDOP)
 
 
# ─────────────────────────────────────────────────────────
class MQTTPublisher:
    def __init__(self):
        self.client = None
        self.connected = False
        if MQTT_AVAILABLE:
            self.client = mqtt.Client(client_id=MQTT_CLIENT_ID)
            self.client.on_connect    = self._on_connect
            self.client.on_disconnect = self._on_disconnect
 
    def connect(self):
        if not MQTT_AVAILABLE or self.client is None:
            return
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            log.error("MQTT connect failed: %s", e)
 
    def _on_connect(self, client, userdata, flags, rc):
        self.connected = (rc == 0)
        log.info("MQTT %s (rc=%d)", "connected" if self.connected else "refused", rc)
 
    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        log.warning("MQTT disconnected (rc=%d)", rc)
 
    def publish(self, topic: str, payload: dict):
        if not self.connected:
            return
        try:
            self.client.publish(f"vehicle/{VEHICLE_ID}/{topic}",
                                json.dumps(payload), qos=1)
        except Exception as e:
            log.error("Publish error: %s", e)
 
    def publish_alert(self, message: str):
        if not self.connected:
            return
        self.client.publish(f"vehicle/{VEHICLE_ID}/alerts", message, qos=1)
 
 
# ─────────────────────────────────────────────────────────
def main():
    log.info("=== Vehicle Tracking System Starting ===")
    log.info("Vehicle ID : %s", VEHICLE_ID)
    log.info("Serial port: %s @ %d baud", SERIAL_PORT, BAUD_RATE)
 
    publisher = MQTTPublisher()
    publisher.connect()
 
    last_publish = 0.0
    gga_data     = None
 
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        log.info("Serial port opened")
    except serial.SerialException as e:
        log.error("Cannot open serial port: %s", e)
        log.info("Running in simulation mode (fake GPS data)")
        ser = None
 
    # ── Simulation mode if no GPS hardware ──
    if ser is None:
        log.info("Simulating GPS data for demonstration...")
        import random, math as _math
        lat, lon = 9.0820, 8.6753   # Abuja, Nigeria
        heading  = 45.0
        while True:
            lat += random.uniform(-0.0005, 0.0005)
            lon += random.uniform(-0.0005, 0.0005)
            speed = random.uniform(20, 80)
            loc = {"lat": round(lat,6), "lon": round(lon,6),
                   "speed_kmh": round(speed,1), "heading": heading,
                   "utc_time": datetime.now(timezone.utc).strftime("%H:%M:%S")}
            log.info("SIM | lat=%.6f lon=%.6f spd=%.1f km/h", lat, lon, speed)
            if MQTT_AVAILABLE:
                publisher.publish("location", loc)
            if speed > SPEED_LIMIT_KMH:
                log.warning("ALERT: Speed %.1f exceeds limit %.1f km/h", speed, SPEED_LIMIT_KMH)
                publisher.publish_alert(f"SPEED_EXCEEDED {speed:.1f} km/h")
            time.sleep(PUBLISH_INTERVAL)
        return
 
    # ── Main GPS loop ──
    while True:
        try:
            raw_line = ser.readline().decode("ascii", errors="ignore").strip()
        except serial.SerialException as e:
            log.error("Read error: %s", e)
            time.sleep(1)
            continue
 
        if not raw_line.startswith("$"):
            continue
 
        # Update fix quality from GGA
        if raw_line.startswith("$GPGGA") or raw_line.startswith("$GNGGA"):
            gga_data = parse_gpgga(raw_line)
            if gga_data:
                log.debug("GGA: sats=%d hdop=%.1f fix=%d",
                          gga_data["satellites"], gga_data["hdop"], gga_data["fix"])
 
        # Parse location from RMC
        elif raw_line.startswith("$GPRMC") or raw_line.startswith("$GNRMC"):
            location = parse_gprmc(raw_line)
 
            if location is None:
                continue
 
            if not is_valid_fix(gga_data):
                log.warning("Fix quality insufficient — discarding reading")
                continue
 
            now = time.time()
            if now - last_publish < PUBLISH_INTERVAL:
                continue
            last_publish = now
 
            # Enrich with quality data
            location["vehicle_id"]  = VEHICLE_ID
            location["timestamp"]   = datetime.now(timezone.utc).isoformat()
            location["satellites"]  = gga_data["satellites"] if gga_data else 0
            location["hdop"]        = gga_data["hdop"]       if gga_data else 0
 
            log.info("lat=%.6f lon=%.6f spd=%.1f km/h hdg=%.0f° sats=%d",
                     location["lat"], location["lon"], location["speed_kmh"],
                     location["heading"], location["satellites"])
 
            publisher.publish("location", location)
 
            if gga_data:
                publisher.publish("status", {
                    "fix": gga_data["fix"],
                    "satellites": gga_data["satellites"],
                    "hdop": gga_data["hdop"],
                })
 
            # Speed alert
            if location["speed_kmh"] > SPEED_LIMIT_KMH:
                alert_msg = (f"SPEED_EXCEEDED | {location['speed_kmh']:.1f} km/h "
                             f"at {location['lat']},{location['lon']}")
                log.warning("ALERT: %s", alert_msg)
                publisher.publish_alert(alert_msg)
 
    ser.close()
 
 
if __name__ == "__main__":
    main()
