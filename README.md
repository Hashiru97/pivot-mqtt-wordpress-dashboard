# Center Pivot Irrigation — MQTT WordPress Frontend Handoff

This package lets your team validate the MQTT topic/payload flow from WordPress
to the device layer and back — **no hardware required**.

## Contents (expected beside this README)
- Center_Pivot_Irrigation_MQTT_Requirements_with_Multi_Motor_Control.pdf
- WordPress MQTT Fields.xlsx
- pivot_device_sim.py
- requirements.txt


## Quick Start (Recommended: virtual environment)

Using a Python **virtual environment (venv)** avoids system-package conflicts and
works even on Debian/Ubuntu/Kali where Python is “externally managed”.

### 1) Create and activate venv
**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate


Windows (PowerShell)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1


You should see (.venv) in your shell prompt when it’s active.
To exit later: deactivate

Install dependencies inside the venv
python -m pip install -r sim/requirements.txt or the required ones in the sim_requirement document

Run the simulator
python sim/pivot_device_sim.py \
  --farm-id FARM-688791691808D-22222256 \
  --user device_ui \
  --password 'Device2025Ui!' \
  --latency 1.0 \
  --cafile "$(python -c 'import certifi;print(certifi.where())')"
  
 Verify install:
 python -c "import paho.mqtt, certifi; print('paho:', paho.mqtt.__version__, '| cert:', certifi.where())"
