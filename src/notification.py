from ultralytics import YOLO

class Messages:
	def __init__(self, 
		violation_name, 
		image_path, 
		date,
		confidence)
		self.violation_name = violation_name
		self.image_path = image_path
		self.date = date
		self.confidence = confidence
		
	def push_to_notification_list(results):
	    for box in results[0].boxes:
            
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            label = self.model.names[cls_id]
            
            if conf > 0.8:
                last_time = last_detect_time.get(label, 0)
                current_time = time.time()
                if current_time - last_time > COOLDOWN:
                    detection = {
                        "label": label,
                        "confidence": conf
                    }
                    
                    latest_detections.append(detection)
                    last_detect_time[label] = current_time
        return 
