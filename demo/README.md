# SecureVoice AI — Sample Demo Video

This directory contains the official sample security surveillance video included with **SecureVoice AI** for testing, demonstration, and project evaluation.

## Video Specifications

- **File**: `demo-security-video.mp4`
- **Format**: MP4 (H.264 / AVC video, YUV 4:2:0)
- **Duration**: 10.0 seconds
- **Resolution**: 768 × 576 (Standard surveillance aspect ratio)
- **Framerate**: 10 FPS
- **File Size**: ~703 KB (fast loading, minimal bandwidth)
- **Pedestrian Activity**: Contains multiple pedestrians entering and traversing the monitored security perimeter.

## AI Detection Benchmark

When analyzed by SecureVoice AI with default settings (Confidence: `0.35`, Cooldown: `10s`, Monitored Region: Full `0–1` normalized):
- **Person Bounding Boxes Detected**: `237`
- **Region Entry Events**: `1` (triggers voice alert and logs to MongoDB)
- **Average Analysis Time**: 1.5 – 3 seconds

## How to Test in the Web App

### 1-Click Sample Loading (Recommended)
1. Open the SecureVoice AI web application (local or deployed on Vercel).
2. In the **Video Analysis** section, click **"Load Sample Video"** (or **"Use Sample Video"**).
3. The video will instantly load into the built-in HTML5 player.
4. Click **"Start analysis"**.
5. The YOLO vision detector processes the frames, displays bounding boxes on the detected pedestrian, and generates a Murf AI voice alert.

### Manual Upload
You can also download `demo-security-video.mp4` and drag-and-drop it into the upload box.
