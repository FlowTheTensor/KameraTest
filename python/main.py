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

def find_camera(max_retries=10, retry_delay=3):
    """
    Sucht automatisch nach einer funktionierenden Kamera.
    Filtert Hardware-Decoder heraus und findet echte Kameras.
    Mit Retry-Logik falls Kamera noch nicht bereit ist.
    """
    import os
    import subprocess
    
    def get_real_camera_devices():
        """Findet echte Kamera-Devices (filtert Hardware-Decoder heraus)"""
        real_cameras = []
        
        try:
            # v4l2-ctl nutzen um echte Kameras zu finden
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                current_device_name = ""
                
                for line in lines:
                    if not line.startswith('\t') and line.strip():
                        current_device_name = line.strip()
                    elif '/dev/video' in line:
                        device_path = line.strip()
                        # Hardware-Decoder/Encoder ausfiltern
                        skip_keywords = ['bcm2835', 'codec', 'isp', 'decoder', 'encoder', 'scaler']
                        is_real_camera = not any(kw in current_device_name.lower() for kw in skip_keywords)
                        
                        if is_real_camera:
                            real_cameras.append(device_path)
                            print(f"  Echte Kamera gefunden: {device_path} ({current_device_name})")
                        else:
                            print(f"  Überspringe Hardware-Device: {device_path} ({current_device_name})")
        except Exception as e:
            print(f"v4l2-ctl nicht verfügbar oder Fehler: {e}")
        
        return real_cameras
    
    def try_open_camera(source, backend=None):
        """Versucht eine Kamera zu öffnen und prüft ob sie funktioniert"""
        try:
            if backend:
                camera = cv2.VideoCapture(source, backend)
            else:
                camera = cv2.VideoCapture(source)
            
            if not camera.isOpened():
                return None
            
            # MJPEG Format setzen (vor dem ersten read!)
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Mehrere Frames versuchen (erster Frame kann manchmal fehlschlagen)
            for _ in range(3):
                time.sleep(0.2)
                ret, frame = camera.read()
                if ret and frame is not None and frame.size > 0:
                    return camera
            
            camera.release()
        except Exception as e:
            print(f"    Fehler bei {source}: {e}")
        
        return None
    
    print("=" * 50)
    print("Suche nach Webcam...")
    print("=" * 50)
    
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"\n--- Versuch {attempt + 1}/{max_retries} (warte {retry_delay}s) ---")
            time.sleep(retry_delay)
        
        # Methode 1: v4l2-ctl nutzen um echte Kameras zu finden
        print("\n[1] Suche mit v4l2-ctl nach echten Kameras...")
        real_cameras = get_real_camera_devices()
        
        for device_path in real_cameras:
            print(f"  Versuche {device_path} mit V4L2...")
            camera = try_open_camera(device_path, cv2.CAP_V4L2)
            if camera:
                print(f"✓ Kamera {device_path} (V4L2) erfolgreich geöffnet!")
                return camera, device_path
        
        # Methode 2: Alle /dev/video* durchprobieren
        print("\n[2] Prüfe alle /dev/video* Devices...")
        for i in range(10):
            path = f"/dev/video{i}"
            if os.path.exists(path):
                print(f"  Versuche {path}...")
                
                # Erst V4L2 Backend
                camera = try_open_camera(path, cv2.CAP_V4L2)
                if camera:
                    print(f"✓ Kamera {path} (V4L2) erfolgreich geöffnet!")
                    return camera, path
                
                # Dann Standard-Backend
                camera = try_open_camera(path)
                if camera:
                    print(f"✓ Kamera {path} erfolgreich geöffnet!")
                    return camera, path
        
        # Methode 3: Index-basiert (für Windows und als Fallback)
        print("\n[3] Versuche Index-basierte Kamerasuche...")
        for idx in range(5):
            print(f"  Versuche Index {idx}...")
            camera = try_open_camera(idx)
            if camera:
                print(f"✓ Kamera Index {idx} erfolgreich geöffnet!")
                return camera, idx
    
    return None, None

def generate_frames():
    """Generator-Funktion für Video-Frames"""
    
    # Automatische Kameraerkennung
    camera, cam_id = find_camera()
    
    if camera is None:
        print("=" * 50)
        print("FEHLER: Keine Kamera gefunden!")
        print("")
        print("Diagnose-Befehle:")
        print("  v4l2-ctl --list-devices")
        print("  ls -la /dev/video*")
        print("  lsusb | grep -i cam")
        print("")
        print("Mögliche Lösungen:")
        print("1. sudo apt install v4l-utils  (falls v4l2-ctl fehlt)")
        print("2. sudo chmod 666 /dev/video*")
        print("3. sudo usermod -aG video $USER && logout")
        print("4. USB-Kamera neu einstecken und warten")
        print("5. sudo modprobe uvcvideo")
        print("6. sudo fuser -k /dev/video*  (falls blockiert)")
        print("7. sudo reboot  (wenn nichts hilft)")
        print("=" * 50)
        return
    
    print(f"Verwende Kamera: {cam_id}")
    
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
    import sys
    import subprocess

    # Bei Autostart nach Boot warten bis Kamera bereit ist
    if '--wait' in sys.argv:
        print("Warte 10 Sekunden auf Kamera-Initialisierung...")
        time.sleep(10)

    # USB-Reset versuchen um Kamera zu aktivieren
    if '--usb-reset' in sys.argv or '--wait' in sys.argv:
        print("Versuche USB-Reset...")
        try:
            # USB-Subsystem neu scannen
            subprocess.run(['sudo', 'udevadm', 'trigger'], timeout=5)
            subprocess.run(['sudo', 'udevadm', 'settle'], timeout=10)
            time.sleep(2)
            print("USB-Reset abgeschlossen")
        except Exception as e:
            print(f"USB-Reset fehlgeschlagen: {e}")

        # Gerätenamen automatisch ermitteln
        import socket
        device_name = socket.gethostname()
        print("Starte Webcam-Server...")
        print("=" * 50)
        print(f"🌐 Öffne im Browser:")
        print(f"   http://{device_name}.local:80")
        print("=" * 50)
        app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
