#!/usr/bin/env python3
"""
InnoVivre Center Pivot – MQTT Device Simulator
- Subscribes:  farm/<FARM-ID>/control
               farm/<FARM-ID>/device
               farm/<FARM-ID>/motor/+/control
- Publishes:   farm/<FARM-ID>/status               (retained Online/Offline via LWT)
               farm/<FARM-ID>/device/status        (non-retained "Running")
               farm/<FARM-ID>/ack|err              (pivot/device acks)
               farm/<FARM-ID>/motor/<ID>/ack|err   (per-motor acks)
"""

import argparse
import json
import random
import re
import ssl
import sys
import time
from typing import Optional

import paho.mqtt.client as mqtt


def jprint(prefix: str, obj):
    try:
        print(prefix, json.dumps(obj, ensure_ascii=False))
    except Exception:
        print(prefix, str(obj))


def parse_args():
    ap = argparse.ArgumentParser(description="Center Pivot MQTT Device Simulator")
    ap.add_argument("--host", default="o7fd7307.ala.us-east-1.emqxsl.com", help="EMQX host")
    ap.add_argument("--port", type=int, default=8883, help="EMQX TLS port (8883)")
    ap.add_argument("--farm-id", required=True, help="Farm/Tower ID, e.g., FARM-XXXX...")
    ap.add_argument("--user", required=True, help="Broker username (e.g. device_ui)")
    ap.add_argument("--password", required=True, help="Broker password")
    ap.add_argument("--latency", type=float, default=1.0, help="Processing latency seconds")
    ap.add_argument("--random-lag", type=float, default=0.0, help="Extra random delay up to N sec")
    ap.add_argument("--drop-rate", type=float, default=0.0, help="0..1 probability to drop ACK")
    ap.add_argument("--motor-fail", action="store_true", help="Return ERR for START_MOTOR")
    ap.add_argument("--cafile", default=None, help="Optional CA bundle file; uses system trust if omitted")
    ap.add_argument("--client-id", default=None, help="Optional custom MQTT clientId")
    return ap.parse_args()


class PivotSim:
    def __init__(self, args):
        self.args = args
        self.client: Optional[mqtt.Client] = None
        self.farm = args.farm_id
        self.re_motor = re.compile(rf"^farm/{re.escape(self.farm)}/motor/([^/]+)/control$")
        # Topics
        self.t_status        = f"farm/{self.farm}/status"
        self.t_dev_status    = f"farm/{self.farm}/device/status"
        self.t_control       = f"farm/{self.farm}/control"
        self.t_device        = f"farm/{self.farm}/device"
        self.t_motor_ctrl    = f"farm/{self.farm}/motor/+/control"
        self.t_ack           = f"farm/{self.farm}/ack"
        self.t_err           = f"farm/{self.farm}/err"

    # ---------- MQTT lifecycle
    def connect(self):
        cid = self.args.client_id or f"device_sim_{random.randint(1000,999999)}"
        self.client = mqtt.Client(client_id=cid, clean_session=True)
        self.client.username_pw_set(self.args.user, self.args.password)

        # Last Will & Testament: device goes Offline if disconnects unexpectedly
        self.client.will_set(
            topic=self.t_status,
            payload=json.dumps({"message": "Offline"}),
            qos=1,
            retain=True,
        )

        # TLS
        if self.args.cafile:
            self.client.tls_set(ca_certs=self.args.cafile, certfile=None, keyfile=None,
                                tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_REQUIRED)
        else:
            ctx = ssl.create_default_context()
            self.client.tls_set_context(ctx)

        # Handlers
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        print(f"🔌 Connecting to {self.args.host}:{self.args.port} as {cid} …")
        self.client.connect(self.args.host, self.args.port, keepalive=30)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected.")
            # Presence + initial device status
            self.publish(self.t_status, {"message": "Online"}, qos=1, retain=True)
            self.publish(self.t_dev_status, {"message": "Running"}, qos=0, retain=False)

            # Subscriptions
            subs = [
                (self.t_control, 0),
                (self.t_device, 0),
                (self.t_motor_ctrl, 0),
            ]
            for t, q in subs:
                client.subscribe(t, q)
            print("📬 Subscribed:", ", ".join(t for t, _ in subs))
        else:
            print(f"❌ Connect failed rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        print(f"🔚 Disconnected (rc={rc}).")

    def publish(self, topic, obj, qos=0, retain=False):
        payload = json.dumps(obj, separators=(",", ":"))
        self.client.publish(topic, payload, qos=qos, retain=retain)
        jprint(f"🚀 {topic} ←", obj)

    # ---------- Message handling
    def _on_message(self, client, userdata, msg):
        text = msg.payload.decode("utf-8", errors="replace")
        print(f"📥 {msg.topic} → {text}")
        try:
            data = json.loads(text or "{}")
        except Exception:
            print("⚠️ Non-JSON payload, ignoring.")
            return

        # Determine type based on topic / payload
        if msg.topic == self.t_control and (data.get("type") == "PIVOT_CMD"):
            self.handle_pivot_cmd(data)
        elif msg.topic == self.t_device and (data.get("type") == "DEVICE_CMD"):
            self.handle_device_cmd(data)
        else:
            m = self.re_motor.match(msg.topic)
            if m and (data.get("type") == "MOTOR_CMD"):
                motor_id = m.group(1)
                self.handle_motor_cmd(motor_id, data)

    # Simulated processing/cadence
    def _sleep_latency(self):
        base = max(0.0, float(self.args.latency))
        jitter = random.uniform(0, max(0.0, float(self.args.random_lag)))
        time.sleep(base + jitter)

    def _maybe_drop(self):
        return random.random() < max(0.0, min(1.0, float(self.args.drop_rate)))

    # ---------- Command handlers
    def handle_pivot_cmd(self, d):
        corr = d.get("corr") or ""
        if self._maybe_drop():
            print(f"🙈 Dropping ACK for PIVOT corr={corr}")
            return
        self._sleep_latency()
        note = f"pivot {d.get('run','').lower()} accepted"
        self.publish(self.t_ack, {"corr": corr, "ok": True, "note": note})

    def handle_device_cmd(self, d):
        corr = d.get("corr") or ""
        action = (d.get("action") or "").upper()
        serial = (d.get("serial") or "").strip()

        if self._maybe_drop():
            print(f"🙈 Dropping ACK for DEVICE corr={corr}")
            return

        self._sleep_latency()

        if not action or not serial:
            self.publish(self.t_err, {"corr": corr, "ok": False, "reason": "missing action/serial"})
            return

        # Simple happy-path accept
        note = f"{action} ok"
        self.publish(self.t_ack, {"corr": corr, "ok": True, "note": note})

    def handle_motor_cmd(self, motor_id: str, d):
        corr = d.get("corr") or ""
        cmd = (d.get("command") or "").upper()

        t_ack = f"farm/{self.farm}/motor/{motor_id}/ack"
        t_err = f"farm/{self.farm}/motor/{motor_id}/err"

        if self._maybe_drop():
            print(f"🙈 Dropping ACK for MOTOR corr={corr}")
            return

        self._sleep_latency()

        # Optional error mode
        if self.args.motor_fail and cmd == "START_MOTOR":
            self.publish(t_err, {"corr": corr, "ok": False, "reason": "sim motor fault"})
            return

        self.publish(t_ack, {"corr": corr, "ok": True, "note": "sim motor ok"})

    # ---------- run
    def run_forever(self):
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                # Graceful disconnect
                if self.client is not None:
                    self.client.loop_stop()
                    self.client.disconnect()
            except Exception:
                pass


def main():
    args = parse_args()
    sim = PivotSim(args)
    sim.connect()
    sim.run_forever()


if __name__ == "__main__":
    main()
