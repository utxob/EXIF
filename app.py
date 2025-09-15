from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import os
import time

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'tiff', 'bmp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_exif(image):
    """Return EXIF data as a dictionary"""
    try:
        exif_data = {}
        info = image._getexif()
        if info:
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                exif_data[decoded] = value
        return exif_data
    except Exception as e:
        return {"Error": str(e)}

def get_gps_info(exif_data):
    """Extract GPS info from EXIF"""
    if not exif_data or 'GPSInfo' not in exif_data:
        return None
    
    gps_info = {}
    for key in exif_data['GPSInfo'].keys():
        decode = GPSTAGS.get(key, key)
        gps_info[decode] = exif_data['GPSInfo'][key]
    return gps_info

def convert_to_degrees(value):
    """Convert GPS coordinates to decimal degrees"""
    try:
        if isinstance(value, tuple) and len(value) >= 3:
            d = float(value[0][0]) / float(value[0][1]) if isinstance(value[0], tuple) else float(value[0])
            m = float(value[1][0]) / float(value[1][1]) if isinstance(value[1], tuple) else float(value[1])
            s = float(value[2][0]) / float(value[2][1]) if isinstance(value[2], tuple) else float(value[2])
            return d + (m / 60.0) + (s / 3600.0)
        elif isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            if ',' in value:
                parts = value.split(',')
                if len(parts) >= 3:
                    d = float(parts[0])
                    m = float(parts[1])
                    s = float(parts[2])
                    return d + (m / 60.0) + (s / 3600.0)
            else:
                return float(value)
        elif isinstance(value, list) and len(value) >= 3:
            d = float(value[0])
            m = float(value[1])
            s = float(value[2])
            return d + (m / 60.0) + (s / 3600.0)
        else:
            return None
    except (IndexError, TypeError, ZeroDivisionError, ValueError):
        return None

def get_coordinates(gps_info):
    """Return latitude and longitude as decimal degrees"""
    try:
        lat, lon = None, None
        
        if 'GPSLatitude' in gps_info:
            lat = convert_to_degrees(gps_info['GPSLatitude'])
            if lat is not None and 'GPSLatitudeRef' in gps_info:
                if gps_info['GPSLatitudeRef'] in ['S', 's', 'W', 'w']:
                    lat = -lat
        
        if 'GPSLongitude' in gps_info:
            lon = convert_to_degrees(gps_info['GPSLongitude'])
            if lon is not None and 'GPSLongitudeRef' in gps_info:
                if gps_info['GPSLongitudeRef'] in ['W', 'w', 'S', 's']:
                    lon = -lon
        
        return lat, lon
    except Exception:
        return None, None

def generate_google_maps_url(lat, lon):
    if lat is not None and lon is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    return None

def safe_remove_file(filepath, max_retries=5, delay=0.1):
    """Safely remove a file with retries to handle file locking issues"""
    for i in range(max_retries):
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except PermissionError:
            time.sleep(delay)  # Wait a bit before retrying
        except Exception as e:
            print(f"Error removing file {filepath}: {e}")
            return False
    return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Create upload directory if it doesn't exist
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        
        file.save(filepath)
        
        try:
            # Process the image - make sure to close it properly
            with Image.open(filepath) as image:
                # Get EXIF data
                exif_data = get_exif(image)
                
                # Get GPS info
                gps_info = get_gps_info(exif_data) if exif_data else None
                
                # Get coordinates
                lat, lon = None, None
                maps_url = None
                if gps_info:
                    lat, lon = get_coordinates(gps_info)
                    maps_url = generate_google_maps_url(lat, lon)
                
                # Prepare data for template
                exif_data_filtered = {k: v for k, v in exif_data.items() if k != 'GPSInfo'} if exif_data else {}
            
            # Clean up - safely remove uploaded file
            if not safe_remove_file(filepath):
                print(f"Warning: Could not remove file {filepath}")
            
            return render_template('result.html', 
                                 filename=filename,
                                 exif_data=exif_data_filtered,
                                 gps_info=gps_info,
                                 latitude=lat,
                                 longitude=lon,
                                 maps_url=maps_url)
            
        except Exception as e:
            # Clean up in case of error
            safe_remove_file(filepath)
            flash(f'Error processing image: {str(e)}')
            return redirect(url_for('index'))
    
    flash('Invalid file type. Please upload an image file (PNG, JPG, JPEG, TIFF, BMP).')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
