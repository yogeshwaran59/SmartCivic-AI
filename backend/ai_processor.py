import math
# pyrefly: ignore [missing-import]
import cv2
import numpy as np
import os
from PIL import Image, ExifTags

import re

_EASYOCR_READER = None

def get_ocr_reader():
    """Lazy global singleton for EasyOCR Reader to avoid re-initializing models on every request."""
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import easyocr
            print("[OCR] Initializing EasyOCR Reader singleton...")
            _EASYOCR_READER = easyocr.Reader(['en'], gpu=False, verbose=False)
            print("[OCR] EasyOCR Reader initialized successfully.")
        except Exception as e:
            print(f"[OCR INIT WARNING] {e}")
            _EASYOCR_READER = False
    return _EASYOCR_READER if _EASYOCR_READER is not False else None

def parse_coordinates_from_text(text):
    """
    Parses latitude and longitude decimal numbers from geotag text strings like:
    - 'Lat 12.880975° Long 77.545679°'
    - 'Lat 12.880975 Long 77.545679'
    - '12.880975, 77.545679'
    - 'Latitude: 12.880975 Longitude: 77.545679'
    Returns (lat, lng) as floats, or (None, None).
    """
    if not text:
        return None, None
    try:
        # Clean OCR noise: normalize spaces around decimal points "12 . 880975" -> "12.880975"
        cleaned = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', str(text))
        
        # Pattern 1: "Lat 12.880975° Long 77.545679°" or "Lat 12.880975 Long 77.545679"
        match = re.search(r'(?:Lat(?:itude)?)\s*[:=]?\s*([+-]?\d{1,3}\.\d+)[°]?\s*[^\d\w\.-]*(?:Lon(?:g(?:itude)?)?)\s*[:=]?\s*([+-]?\d{1,3}\.\d+)', cleaned, re.IGNORECASE)
        if match:
            lat = float(match.group(1))
            lng = float(match.group(2))
            if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
                return lat, lng

        # Pattern 2: Separate Lat ... and Long ... occurrences anywhere in text
        lat_match = re.search(r'(?:Lat(?:itude)?)\s*[:=]?\s*([+-]?\d{1,2}\.\d+)', cleaned, re.IGNORECASE)
        lng_match = re.search(r'(?:Lon(?:g(?:itude)?)?)\s*[:=]?\s*([+-]?\d{1,3}\.\d+)', cleaned, re.IGNORECASE)
        if lat_match and lng_match:
            lat = float(lat_match.group(1))
            lng = float(lng_match.group(2))
            if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
                return lat, lng

        # Pattern 3: Two decimal numbers separated by comma or whitespace "12.880975, 77.545679"
        match3 = re.findall(r'([+-]?\d{1,2}\.\d{4,})\s*[,\s]+\s*([+-]?\d{1,3}\.\d{4,})', cleaned)
        for c_lat, c_lng in match3:
            lat = float(c_lat)
            lng = float(c_lng)
            if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
                return lat, lng

    except Exception as e:
        print(f"[AI GEOTAG TEXT PARSER WARNING] {e}")
    return None, None

def _convert_to_degrees(value):
    """Convert EXIF GPS coordinate tuple to decimal degrees. Handles IFDRational, tuples, floats."""
    try:
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, IndexError, ValueError):
        try:
            return float(value)
        except Exception:
            return 0.0

def extract_exif_gps(img_path):
    """
    Extracts (latitude, longitude) decimal coordinates from an image's EXIF GPS metadata or EXIF text comments.
    Uses multiple Pillow API methods for maximum compatibility.
    Returns (lat, lng) or (None, None).
    """
    if not img_path or not os.path.exists(img_path):
        return None, None

    try:
        with Image.open(img_path) as image:
            gps_info = {}

            # Method 1: Modern Pillow getexif() API
            try:
                exif_data = image.getexif()
                if exif_data:
                    gps_ifd = exif_data.get_ifd(0x8825)
                    if gps_ifd:
                        for key, val in gps_ifd.items():
                            tag_name = ExifTags.GPSTAGS.get(key, key)
                            gps_info[tag_name] = val
                        print(f"[EXIF] getexif() GPS keys found: {list(gps_info.keys())}")
            except Exception as e1:
                print(f"[EXIF] getexif() method failed: {e1}")

            # Method 2: Legacy _getexif() API fallback
            if not gps_info:
                try:
                    getexif_fn = getattr(image, '_getexif', None)
                    if callable(getexif_fn):
                        exif = getexif_fn()
                        if isinstance(exif, dict):
                            for tag, value in exif.items():
                                tag_name = ExifTags.TAGS.get(tag, tag)
                                if tag_name == 'GPSInfo':
                                    for g_tag in value:
                                        g_name = ExifTags.GPSTAGS.get(g_tag, g_tag)
                                        gps_info[g_name] = value[g_tag]
                                    print(f"[EXIF] _getexif() GPS keys found: {list(gps_info.keys())}")
                except Exception as e2:
                    print(f"[EXIF] _getexif() method failed: {e2}")

            if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
                lat = _convert_to_degrees(gps_info['GPSLatitude'])
                if gps_info.get('GPSLatitudeRef') == 'S':
                    lat = -lat
                lng = _convert_to_degrees(gps_info['GPSLongitude'])
                if gps_info.get('GPSLongitudeRef') == 'W':
                    lng = -lng
                print(f"[EXIF] Successfully extracted GPS: lat={lat}, lng={lng}")
                return lat, lng

            # Method 3: Check string EXIF comments / descriptions for coordinate text
            try:
                getexif_fn = getattr(image, '_getexif', None)
                if callable(getexif_fn):
                    exif = getexif_fn()
                    if isinstance(exif, dict):
                        for tag, val in exif.items():
                            tag_name = ExifTags.TAGS.get(tag, tag)
                            if isinstance(val, (str, bytes)):
                                text_val = val.decode('utf-8', errors='ignore') if isinstance(val, bytes) else val
                                c_lat, c_lng = parse_coordinates_from_text(text_val)
                                if c_lat is not None and c_lng is not None:
                                    print(f"[EXIF TEXT TAG] Coordinates found in EXIF '{tag_name}': ({c_lat}, {c_lng})")
                                    return c_lat, c_lng
            except Exception as e_text:
                print(f"[EXIF TEXT TAG WARNING] {e_text}")

    except Exception as e:
        print(f"[AI EXIF EXTRACTOR WARNING] {e}")
    return None, None

def extract_text_from_image_watermark(img_path):
    """
    Extracts GPS coordinates from visual watermark text burned into GPS Map Camera photos.
    Crops the bottom 40% of the image and runs OCR.
    Returns (lat, lng) or (None, None).
    """
    if not img_path or not os.path.exists(img_path):
        return None, None

    try:
        reader = get_ocr_reader()
        if not reader:
            print("[OCR WATERMARK] EasyOCR reader not available.")
            return None, None

        img = cv2.imread(img_path)
        if img is None:
            return None, None

        h, w = img.shape[:2]

        # Scan crops (bottom 40% where watermarks are, plus full image fallback)
        crops = [
            img[int(h * 0.60):h, 0:w],
            img
        ]

        for crop in crops:
            results = reader.readtext(crop, detail=0)
            all_text = ' '.join(str(res) for res in results)
            print(f"[OCR WATERMARK] Extracted text from crop: '{all_text}'")

            lat, lng = parse_coordinates_from_text(all_text)
            if lat is not None and lng is not None:
                print(f"[OCR WATERMARK] Found GPS coordinates: ({lat}, {lng})")
                return lat, lng

    except Exception as e:
        print(f"[OCR WATERMARK WARNING] {e}")

    return None, None

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
        return similarity
    except Exception as e:
        print(f"Error in image comparison: {e}")
        return 0.0

try:
    from hf_multilingual import (
        classify_complaint_multilingual,
        translate_text,
        detect_language,
        SUPPORTED_LANGUAGES
    )
except ImportError:
    # Local directory fallback
    import sys
    sys.path.append(os.path.dirname(__file__))
    from hf_multilingual import (
        classify_complaint_multilingual,
        translate_text,
        detect_language,
        SUPPORTED_LANGUAGES
    )

def classify_complaint_text(description, title=""):
    """
    Hugging Face Multilingual Issue Classifier & Heuristic Parser.
    Supports English, Kannada (ಕನ್ನಡ), Hindi (हिंदी), and Telugu (తెలుగు).
    Returns: (category, priority)
    """
    res = classify_complaint_multilingual(description, title=title)
    return res['category'], res['priority']



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
        
        # Check EXIF geotag
        exif_lat, exif_lng = extract_exif_gps(img_path)
        if exif_lat is not None and exif_lng is not None:
            description += f"Embedded photo GPS geotag detected at coordinates ({exif_lat:.5f}, {exif_lng:.5f}). "

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

