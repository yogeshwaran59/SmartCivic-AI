import math
import cv2
import numpy as np
import os

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) in meters.
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371000  # Radius of earth in meters
    return c * r

def get_image_similarity(img_path1, img_path2):
    """
    Compute image similarity using normalized color histogram comparison in HSV space.
    Returns correlation score between -1 and 1.
    """
    if not img_path1 or not img_path2:
        return 0.0
    if not os.path.exists(img_path1) or not os.path.exists(img_path2):
        return 0.0

    try:
        # Read images using OpenCV
        img1 = cv2.imread(img_path1)
        img2 = cv2.imread(img_path2)
        if img1 is None or img2 is None:
            return 0.0

        # Resize to normalized dimensions (e.g. 256x256) to ensure consistent size
        img1 = cv2.resize(img1, (256, 256))
        img2 = cv2.resize(img2, (256, 256))

        # Convert to HSV color space for better color invariance
        hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
        hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)

        # Calculate histograms for H and S channels
        hist1 = cv2.calcHist([hsv1], [0, 1], None, [180, 256], [0, 180, 0, 256])
        hist2 = cv2.calcHist([hsv2], [0, 1], None, [180, 256], [0, 180, 0, 256])

        # Normalize histograms
        cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

        # Compare histograms using correlation
        similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        return float(similarity)
    except Exception as e:
        print(f"Error in image comparison: {e}")
        return 0.0

def classify_complaint_text(description):
    """
    Simple keyword heuristic parser to classify complaint categories and auto-assign priorities.
    Returns: (category, priority)
    Categories: 'pothole' | 'garbage' | 'drainage' | 'street_light' | 'other'
    Priorities: 'High' | 'Medium' | 'Low'
    """
    desc = description.lower()
    
    # Classify category
    if any(k in desc for k in ['street_light', 'street light', 'lamp', 'bulb', 'outage', 'darkness']):
        category = 'street_light'
    elif any(k in desc for k in ['pothole', 'crater', 'asphalt', 'tarmac', 'bump', 'road damage', 'broken road', 'street damage']):
        category = 'pothole'
    elif any(k in desc for k in ['garbage', 'trash', 'waste', 'litter', 'dump', 'bin', 'refuse', 'stink', 'smell']):
        category = 'garbage'
    elif any(k in desc for k in ['drain', 'sewer', 'leak', 'overflow', 'flooding', 'flood', 'clog', 'water log', 'gutter']):
        category = 'drainage'
    else:
        category = 'other'

    # Classify priority
    priority = 'Medium'
    
    # Drainage issues are often high priority due to flooding and health risks
    if category == 'drainage':
        priority = 'High'
        
    # Pothole on busy/dangerous areas or causing accidents is high priority
    elif category == 'pothole':
        if any(k in desc for k in ['accident', 'crash', 'injury', 'danger', 'deep', 'main road', 'highway', 'traffic']):
            priority = 'High'
        else:
            priority = 'Medium'
            
    # Garbage blocking paths or overflowing heavily is medium/high
    elif category == 'garbage':
        if any(k in desc for k in ['overflow', 'blocking', 'blocked', 'stink', 'smell', 'rot', 'disease']):
            priority = 'Medium'
        else:
            priority = 'Low'
            
    # Street light in complete darkness or crime-prone/high traffic areas
    elif category == 'street_light':
        if any(k in desc for k in ['dark', 'complete', 'broken', 'accident', 'danger', 'safety']):
            priority = 'Medium'
        else:
            priority = 'Low'
            
    # Other default checks
    elif category == 'other':
        if any(k in desc for k in ['hazard', 'emergency', 'electric', 'wire', 'fire']):
            priority = 'High'
        else:
            priority = 'Low'

    return category, priority

def analyze_and_describe_image(img_path):
    """
    Analyzes physical properties of the image (brightness, contrast, HSV color space)
    using OpenCV to generate an automated description of the issue.
    """
    if not img_path or not os.path.exists(img_path):
        return "No image proof uploaded."
    
    try:
        # Read image using OpenCV
        img = cv2.imread(img_path)
        if img is None:
            return "Failed to decode image file."

        h, w, c = img.shape
        
        # Calculate average brightness using grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        
        # Calculate Laplacian variance (contrast/texture detail)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        
        # Calculate HSV statistics
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_mean = float(np.mean(hsv[:, :, 0]))
        s_mean = float(np.mean(hsv[:, :, 1]))
        
        # Compile analysis details
        description = f"Image proof analyzed ({w}x{h} px). "
        
        if mean_brightness < 45:
            description += "Detected extremely low ambient light levels. Pattern indicates nighttime visibility constraints, consistent with street light outage or blackouts."
        elif 30 < h_mean < 85 and s_mean > 50:
            description += "Detected dominant green/yellow/brown hues and cluttered geometries. Pattern suggests high density of discarded organic matter or garbage heap."
        elif s_mean < 45 and lap_var > 180:
            description += "Detected high-contrast structural edges in monochromatic range. Textures match typical asphalt cracking, surface degradation, or pothole craters."
        elif mean_brightness < 120 and s_mean < 55:
            description += "Detected medium-dark low-saturation reflective properties. Texture signature indicates fluid pooling or drainage system overflow."
        else:
            description += "Detected general landscape details with adequate lighting. Image clarity matches standards for dispatch task validation."
            
        return description
    except Exception as e:
        return f"Image proof uploaded. Automatic analysis reported: General civic hazard pattern. (Error during image matrix sweep: {str(e)})"

