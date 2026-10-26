from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

        first_stamp = None
        for msg in read_ros2_messages(tmp_path, topics=["/sensor/attitude"]):
            t = msg.log_time_ns
            if first_stamp is None:
                first_stamp = t
            
            m = msg.ros_msg
            series["time"].append(round((t - first_stamp) / 1e9, 4))
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
            "duration_sec": series["time"][-1] if series["time"] else 0,
            "series": series
        }
    finally:
        # Hapus file sementara setelah selesai dibaca
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
