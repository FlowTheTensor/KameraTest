from flask import Flask, Response, render_template_string
import cv2
import time
import numpy as np
import socket

app = Flask(__name__)

# HTML-Template für die Webseite
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Webcam Livestream</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            background-color: #1a1a2e;
            color: white;
        }
        h1 {
            margin-bottom: 20px;
        }
        img {
            border: 3px solid #4a4a6a;
            border-radius: 10px;
            max-width: 90%;
        }
    </style>
</head>
<body>
    <h1>🎥 Webcam Livestream</h1>
    <img src="{{ url_for('video_feed') }}" alt="Webcam Stream">
</body>
</html>
"""


def find_camera_index(max_index=10):
    """Sucht den ersten verfügbaren Kamera-Index sehr schnell."""
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            cap.release()
            return idx
        cap.release()
    return None

# Automatische Kameraerkennung (schnelle Suche)
camera_index = find_camera_index()
if camera_index is None:
    raise RuntimeError("Keine Kamera gefunden!")
camera = cv2.VideoCapture(camera_index)

def generate_frames():
    """Generator-Funktion für Video-Frames"""
    
    # Kamera-Einstellungen für bessere Performance
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))  # MJPEG direkt von Kamera
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 30)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    # Aktuelle Kamera-Einstellungen ausgeben
    actual_width = camera.get(cv2.CAP_PROP_FRAME_WIDTH)
    actual_height = camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
    actual_fps = camera.get(cv2.CAP_PROP_FPS)
    print(f"Kamera: {actual_width}x{actual_height} @ {actual_fps} FPS")
    
    # JPEG-Qualität (niedriger = schneller)
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]
    
    # FPS-Berechnung (geglättet)
    prev_time = time.time()
    fps = 0
    fps_smooth = 0
    
    try:
        while True:
            success, frame = camera.read()
            if not success:
                break
            
            # FPS berechnen (geglättet für stabilere Anzeige)
            current_time = time.time()
            time_diff = current_time - prev_time
            if time_diff > 0:
                fps = 1 / time_diff
                fps_smooth = 0.9 * fps_smooth + 0.1 * fps  # Glättung
            prev_time = current_time
            
            # FPS auf das Bild schreiben (grüner Text mit schwarzem Hintergrund)
            fps_text = f"FPS: {round(fps_smooth)}"
            cv2.rectangle(frame, (5, 5), (150, 45), (0, 0, 0), -1)  # Schwarzer Hintergrund
            cv2.putText(frame, fps_text, (10, 35), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # --- Schwarze Bereiche finden und grün umrahmen ---
            # In Graustufen umwandeln
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Schwellenwert für "schwarz" (anpassbar)
            _, mask = cv2.threshold(gray, 40, 255, cv2.THRESH_BINARY_INV)
            # Konturen finden
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            # Konturen grün umrahmen
            cv2.drawContours(frame, contours, -1, (0, 255, 0), 2)

            # Frame als JPEG kodieren (mit reduzierter Qualität)
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            if not ret:
                continue
            
            # Frame als Bytes zurückgeben (MJPEG-Format)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
    finally:
        camera.release()


@app.route('/')
def index():
    """Hauptseite mit dem Video-Stream"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/video_feed')
def video_feed():
    """Route für den Video-Stream"""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )



if __name__ == '__main__':
    # Gerätenamen automatisch ermitteln
    print("Starte Webcam-Server...")
    print("=" * 50)
    print(f"🌐 Öffne im Browser:")
    print(f"   [hier Gerätename einfügen].local")
    print("=" * 50)
    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)