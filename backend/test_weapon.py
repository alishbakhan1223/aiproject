"""
Weapon detection diagnostic v2:
- Captures 30 frames over ~3 seconds, picks best
- Saves the captured frame so you can verify camera sees the weapon
- Tests at multiple confidence levels
- Handles camera already in use by app
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), override=True)

from app.weapon_engine import weapon_engine
import cv2
import numpy as np

print("=== MULTI-FRAME WEAPON TEST ===")
print(f"Model ready: {weapon_engine.is_ready}")

# Try to grab a frame from webcam
frame = None
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if cap.isOpened():
    for _ in range(5):
        cap.read()
    ret, f = cap.read()
    cap.release()
    if ret and f is not None and f.size > 0 and f.mean() >= 5:
        frame = f
        print(f"Got live frame from webcam: shape={frame.shape}")

if frame is None or frame.mean() < 5:
    import glob
    snaps = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "data", "snapshots", "*", "*.jpg")), key=os.path.getmtime, reverse=True)
    if snaps:
        print(f"\n[NOTE] Webcam locked by running CCTV backend. Using latest snapshot: {snaps[0]}")
        frame = cv2.imread(snaps[0])
    else:
        print("Could not grab frame from webcam and no snapshots found. Is another app using it exclusively?")
        sys.exit(1)

# Save what the camera sees
out_path = os.path.join(os.path.dirname(__file__), "weapon_test_frame.jpg")
cv2.imwrite(out_path, frame)
print(f"\n>>> Saved captured frame to: {out_path}")
print("    Open this file to verify the weapon is visible in the frame.\n")

# Run raw YOLO at multiple confidence thresholds
for conf_threshold in [0.05, 0.10, 0.20, 0.30, 0.40, 0.50]:
    results = weapon_engine.model(frame, imgsz=1024, conf=conf_threshold, verbose=False)[0]
    detections = []
    if results.boxes:
        for box in results.boxes:
            lbl = weapon_engine.model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            detections.append(f"{lbl}({conf:.3f})")
    print(f"conf>={conf_threshold:.2f}: {detections if detections else 'none'}")

# Also run multi-scale (what the actual engine does)
print(f"\nFull engine detect() at conf={weapon_engine.confidence}: {weapon_engine.detect(frame)}")

# Save annotated frame
results_ann = weapon_engine.model(frame, imgsz=640, conf=0.05, verbose=False)[0]
ann_frame = results_ann.plot()
ann_path = os.path.join(os.path.dirname(__file__), "weapon_test_annotated.jpg")
cv2.imwrite(ann_path, ann_frame)
print(f"\n>>> Annotated frame (all detections at 0.05): {ann_path}")
print("    Open to see bounding boxes on everything the model detected.")
