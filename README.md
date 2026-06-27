# Vehicle-_Tracking-_System# Real-Time Vehicle Tracking System
Author: Samuel Nathan Bobai
Contact: nathanbsamuel25@gmail.com
Platform: Raspberry Pi | Language: Python 3 | License: MIT
================================================================
 
## Badges
[Raspberry Pi] [Python 3] [GPS/NMEA] [MQTT] [paho-mqtt] [matplotlib] [pyserial] [MIT]
 
================================================================
## Project Overview
================================================================
A real-time GPS vehicle tracker built on Raspberry Pi.
 
Raw NMEA sentences arrive over UART from a GPS/GSM module.
The Python pipeline:
  1. Validates NMEA checksums (XOR verification)
  2. Filters low-quality fixes (< 4 satellites or HDOP > 5.0)
  3. Parses $GPRMC (position, speed) and $GPGGA (fix quality)
  4. Publishes clean JSON payloads to an MQTT broker
  5. Triggers overspeed alerts when threshold is exceeded
 
A live matplotlib dashboard subscribes to the broker and plots
the vehicle route with speed colour-coding in real time.
 
If no GPS hardware is connected, the system auto-starts in
simulation mode broadcasting fake coordinates (Abuja, Nigeria).
 
================================================================
## Key Features
================================================================
  - Full NMEA checksum validation (XOR) -- bad sentences discarded
  - GPGGA fix-quality filter: min 4 satellites, HDOP <= 5.0
  - Parses both $GPRMC (position/speed) and $GPGGA (fix quality)
  - Publishes to 3 MQTT topics: location, status, alerts
  - Overspeed alert (configurable threshold, default 120 km/h)
  - Live matplotlib dashboard with speed colour map + route trail
  - Simulation mode (no hardware required to test)
  - Structured timestamped logging to stdout
 
================================================================
## System Architecture (End-to-End)
================================================================
 
  [GPS Module]                    [GSM / 4G Module]
      |  UART                           |  UART
      v                                 v
  +----------------------------------------------+
  |              Raspberry Pi                    |
  |  +------------------+  +----------------+   |
  |  |   tracker.py     |  |  dashboard.py  |   |
  |  | - NMEA parse     |  | - MQTT sub     |   |
  |  | - fix filter     |  | - route plot   |   |
  |  | - MQTT publish   |  | - speed map    |   |
  |  +------------------+  +----------------+   |
  +----------------------------------------------+
                   |
                   | MQTT publish (QoS 1)
                   v
        [MQTT Broker - HiveMQ / Mosquitto]
                   |
        +----------+----------+
        |          |          |
        v          v          v
   [Mobile App] [Server/DB] [Alerts]
   Fleet view   Logging     Overspeed /
                            Geofence
 
================================================================
## NMEA Data Pipeline
================================================================
 
  [Raw NMEA from GPS UART]
         |
         v
  [Checksum Validation]  -- invalid? --> DISCARD
         |
         v
  [Parse $GPRMC + $GPGGA]
         |
         v
  [Fix Quality Filter]   -- weak fix? --> DISCARD
  (sats >= 4, HDOP <= 5)
         |
         v
  [Rate Limiter - 2 s]
         |
         v
  [MQTT Publish - JSON payload]
         |
         +---> vehicle/{ID}/location
         +---> vehicle/{ID}/status
         +---> vehicle/{ID}/alerts  (if overspeed)
 
================================================================
## MQTT Topics
================================================================
 
  Topic                    | Format | Payload fields
  -------------------------|--------|-------------------------------
  vehicle/{ID}/location    | JSON   | lat, lon, speed_kmh, heading,
                           |        | timestamp, satellites, hdop
  vehicle/{ID}/status      | JSON   | fix, satellites, hdop
  vehicle/{ID}/alerts      | String | SPEED_EXCEEDED + coordinates
 
================================================================
## Wiring Reference (Raspberry Pi GPIO)
================================================================
 
  GPS Module Pin | Raspberry Pi         | Notes
  ---------------|----------------------|-------------------------
  TX             | GPIO 15 / Pin 10     | UART RX (receive data)
  RX             | GPIO 14 / Pin 8      | UART TX (optional)
  VCC            | Pin 1 (3.3 V)        | Power
  GND            | Pin 6 (GND)          | Ground
 
  Note: Enable serial UART in raspi-config before wiring.
        Disable the serial console (login shell) on the same port.
 
================================================================
## Quick Start
================================================================
 
  1. Enable UART on Raspberry Pi:
       sudo raspi-config
       --> Interface Options --> Serial Port
       Disable login shell, Enable serial hardware.
 
  2. Install Python dependencies:
       pip install paho-mqtt pyserial matplotlib
 
  3. Edit SERIAL_PORT in src/tracker.py to match your GPS module:
       /dev/ttyS0   (built-in UART, Pi 3/4/5)
       /dev/ttyAMA0 (older Pi models)
       /dev/ttyUSB0 (USB GPS dongle)
 
  4. Run the tracker:
       python src/tracker.py
 
  5. In a second terminal, run the dashboard:
       python src/dashboard.py
 
  6. No GPS hardware? tracker.py starts in simulation mode
     automatically and broadcasts fake coordinates.
 
================================================================
## Python Dependencies
================================================================
 
  Package      | Version | Purpose
  -------------|---------|-----------------------------------
  paho-mqtt    | 1.6+    | MQTT client -- publish/subscribe
  pyserial     | 3.5+    | UART GPS communication
  matplotlib   | 3.5+    | Live route map dashboard
 
  Install all at once:
    pip install paho-mqtt pyserial matplotlib
 
  Or using requirements.txt:
    pip install -r requirements.txt
 
================================================================
## Repository Structure
================================================================
 
  vehicle_tracker/
  +-- src/
  |   +-- tracker.py       # GPS reader + MQTT publisher
  |   +-- dashboard.py     # Live matplotlib map
  +-- docs/
  |   +-- README.txt       # This file
  +-- requirements.txt
  +-- README.md
  +-- LICENSE
 
================================================================
## License & Author
================================================================
 
  Samuel Nathan Bobai
  Computer Science undergraduate
  National Open University of Nigeria
  Embedded Systems Intern @ Nhub Incubators
  nathanbsamuel25@gmail.com
 
  Released under the MIT License.
  Copyright (c) 2026 Samuel Nathan Bobai
