from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcap.reader import make_reader
from mcap_ros2.reader import read_ros2_messages
import tempfile
import shutil
import os

app = FastAPI(title="ROS 2 MCAP Telemetry API")

# Konfigurasi CORS agar Vue.js (biasanya di port 5173) bisa mengakses API ini
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "FastAPI MCAP Server is running"}

@app.post("/api/upload-mcap")
async def parse_mcap(file: UploadFile = File(...)):
    if not file.filename.endswith(".mcap"):
        raise HTTPException(status_code=400, detail="Format file harus .mcap")

    # Simpan file yang diunggah ke penyimpanan sementara
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mcap") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        series = {
            "time": [],
            "roll": [], "pitch": [], "yaw": [], "initial": [],
            "rollspeed": [], "pitchspeed": [], "yawspeed": []
        }

        depth = {k: [] for k in ("time", "depth", "pressure")}
        control = {k: [] for k in ("time", "throttle", "lateral", "forward", "yaw",
                                   "arm_mode", "control_mode", "gripper_mode", "source")}

        # Topic Orca* dicari lewat nama tipe pesannya (nama topic tidak perlu diketahui)
        with open(tmp_path, "rb") as f:
            summary = make_reader(f).get_summary()
        topics = [c.topic for c in summary.channels.values()
                  if c.topic == "/sensor/attitude"
                  or summary.schemas[c.schema_id].name.split("/")[-1] in ("OrcaDepth", "OrcaControl")]

        first_stamp = None  # satu acuan waktu untuk semua topic
        for msg in read_ros2_messages(tmp_path, topics=topics):
            t = msg.log_time_ns
            if first_stamp is None:
                first_stamp = t
            ts = round((t - first_stamp) / 1e9, 4)

            m = msg.ros_msg
            kind = msg.schema.name.split("/")[-1]
            if kind == "OrcaDepth":
                depth["time"].append(ts)
                for k in ("depth", "pressure"):
                    depth[k].append(round(float(getattr(m, k)), 3))
            elif kind == "OrcaControl":
                control["time"].append(ts)
                for k in ("throttle", "lateral", "forward", "yaw"):
                    control[k].append(int(getattr(m, k)))
                for k in ("arm_mode", "control_mode", "gripper_mode", "source"):
                    control[k].append(getattr(m, k))
            else:
                series["time"].append(ts)
                series["roll"].append(round(float(m.roll_deg), 3))
                series["pitch"].append(round(float(m.pitch_deg), 3))
                series["yaw"].append(round(float(m.yaw_deg), 3))
                series["initial"].append(round(float(m.initial_deg), 3))
                series["rollspeed"].append(round(float(m.rollspeed_deg_s), 3))
                series["pitchspeed"].append(round(float(m.pitchspeed_deg_s), 3))
                series["yawspeed"].append(round(float(m.yawspeed_deg_s), 3))

        return {
            "filename": file.filename,
            "message_count": len(series["time"]),
            "duration_sec": max([s["time"][-1] for s in (series, depth, control) if s["time"]], default=0),
            "series": series,
            "depth": depth,
            "control": control
        }
    finally:
        # Hapus file sementara setelah selesai dibaca
        if os.path.exists(tmp_path):
            os.remove(tmp_path)