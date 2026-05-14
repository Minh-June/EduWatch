def detect_object(frame):
    model = YOLO("yolo_eduwatch.pt")
    results = model(frame, imgsz = 320)

    for box in results[0].boxes:
        conf = float(box.conf[0])
        cls_id = int(box.cls[0])
        label = model.names[cls_id]

        if conf > 0.8:
            last_time = last_detect_time.get(label, 0)
            current_time = time.time()

            if current_time - last_time > COOLDOWN:
                detection = {
                    "label": label,
                    "confidence": conf
                }
                
                # Dua ket qua vao danh sach
                latest_detections.append(detection)
                last_detect_time[label] = current_time

