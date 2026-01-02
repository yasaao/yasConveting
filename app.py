import zipfile
import io
import uuid
import os
from flask import Flask, request, jsonify, send_file, render_template
from PIL import Image, ImageEnhance

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yas_ultimate_converter_pro_max_2026'

TEMP_STORAGE = {} 

MIMETYPE_MAP = {
    'png': 'image/png', 'bmp': 'image/bmp', 'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg', 'webp': 'image/webp', 'tga': 'image/x-tga',
    'ico': 'image/x-icon', 'tiff': 'image/tiff', 'gif': 'image/gif'
}

def convert_image_universal(img_stream, target_format, size=None, adjustments=None):
    try:
        img = Image.open(img_stream)
        output_stream = io.BytesIO()
        fmt = target_format.lower()

        # --- FITUR RESIZE ---
        if size and size[0] > 0 and size[1] > 0:
            img = img.resize((size[0], size[1]), Image.Resampling.LANCZOS)
        
        # --- FITUR EDITING ---
        if adjustments:
            if adjustments.get('brightness') != 1.0:
                img = ImageEnhance.Brightness(img).enhance(adjustments['brightness'])
            if adjustments.get('contrast') != 1.0:
                img = ImageEnhance.Contrast(img).enhance(adjustments['contrast'])
            if adjustments.get('saturation') != 1.0:
                img = ImageEnhance.Color(img).enhance(adjustments['saturation'])

        # --- LOGIKA KONVERSI ---
        if fmt == 'bmp':
            if img.mode != 'RGB': img = img.convert('RGB')
            img = img.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE)
            img.save(output_stream, 'BMP')
        elif fmt == 'tga':
            if 'A' in img.mode: img = img.convert('RGBA')
            else: img = img.convert('RGB')
            img.save(output_stream, 'TGA', rle=True)
        elif fmt == 'png':
            img.save(output_stream, 'PNG', optimize=True)
        elif fmt == 'ico':
            if 'A' in img.mode: img = img.convert('RGBA')
            img.save(output_stream, 'ICO')
        elif fmt in ['jpg', 'jpeg']:
            if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
            img.save(output_stream, 'JPEG', quality=95, subsampling=0)
        elif fmt == 'webp':
            img.save(output_stream, 'WEBP', quality=95)
        elif fmt == 'tiff':
            img.save(output_stream, 'TIFF', compression='tiff_deflate')
        else:
            if img.mode != 'RGB': img = img.convert('RGB')
            img.save(output_stream, fmt.upper())
            
        output_stream.seek(0)
        return output_stream
    except Exception as e:
        print(f"Error: {e}")
        return None

def process_file(file_id, file_info, target_format, width=None, height=None, adjustments=None):
    try:
        is_zip = file_info['filename'].lower().endswith('.zip')
        size = (int(width), int(height)) if width and height else None
        
        adj = {
            'brightness': float(adjustments.get('brightness', 1.0)),
            'contrast': float(adjustments.get('contrast', 1.0)),
            'saturation': float(adjustments.get('saturation', 1.0))
        } if adjustments else None

        if is_zip:
            zip_out = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(file_info['data']), 'r') as z_in:
                with zipfile.ZipFile(zip_out, 'w', zipfile.ZIP_DEFLATED) as z_out:
                    for name in z_in.namelist():
                        if name.endswith('/') or '__MACOSX' in name: continue
                        if any(name.lower().endswith(x) for x in ['.png','.jpg','.jpeg','.webp','.bmp','.tga','.dds','.psd','.ico']):
                            try:
                                img_data = z_in.read(name)
                                conv = convert_image_universal(io.BytesIO(img_data), target_format, size, adj)
                                if conv:
                                    new_name = os.path.splitext(name)[0] + '.' + target_format
                                    z_out.writestr(new_name, conv.getvalue())
                            except: pass
            result_data = zip_out.getvalue()
            out_name = f"Result_{target_format.upper()}.zip"
            mime = "application/zip"
        else:
            conv = convert_image_universal(io.BytesIO(file_info['data']), target_format, size, adj)
            if not conv: raise Exception("Gagal convert")
            result_data = conv.getvalue()
            name_only = os.path.splitext(file_info['filename'])[0]
            out_name = f"{name_only}.{target_format}"
            mime = MIMETYPE_MAP.get(target_format, 'application/octet-stream')

        file_info.update({
            'converted_data': result_data,
            'download_name': out_name,
            'converted_mime': mime,
            'status': 'completed'
        })
        return True
    except Exception as e:
        print(f"Proc Error: {e}")
        return False

# --- ROUTES ---

@app.route('/')
def index(): return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({'success': False})
    f = request.files['file']
    fid = str(uuid.uuid4())
    TEMP_STORAGE[fid] = {'filename': f.filename, 'data': f.read(), 'status': 'uploaded'}
    return jsonify({'success': True, 'file_id': fid, 'filename': f.filename})

# --- ROUTE BARU: GENERATE PREVIEW (TGA/DDS/PSD) ---
@app.route('/gen_preview', methods=['POST'])
def gen_preview():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    f = request.files['file']
    try:
        # Buka gambar (Pillow support TGA & DDS secara native)
        img = Image.open(f)
        if img.mode not in ('RGB', 'RGBA'): img = img.convert('RGBA')
        
        # Resize thumbnail biar ringan
        img.thumbnail((500, 500))
        
        output = io.BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return send_file(output, mimetype='image/png')
    except Exception as e:
        print(f"Preview Error: {e}")
        return jsonify({'error': 'Failed'}), 500

@app.route('/convert', methods=['POST'])
def convert():
    data = request.json
    fid = data.get('file_id')
    fmt = data.get('format', 'bmp')
    w = data.get('width')
    h = data.get('height')
    adj = data.get('adjustments')
    
    info = TEMP_STORAGE.get(fid)
    if not info: return jsonify({'success': False, 'msg': 'File hilang'})
    
    success = process_file(fid, info, fmt, w, h, adj)
    if success:
        return jsonify({'success': True, 'file_id': fid, 'name': info['download_name']})
    else:
        return jsonify({'success': False, 'msg': 'Gagal convert'})

@app.route('/download/<fid>')
def download(fid):
    info = TEMP_STORAGE.get(fid)
    if not info or 'converted_data' not in info: return "Not found", 404
    return send_file(io.BytesIO(info['converted_data']), mimetype=info['converted_mime'], as_attachment=True, download_name=info['download_name'])

@app.route('/download_zip', methods=['POST'])
def download_zip():
    data = request.json
    fids = data.get('file_ids', [])
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fid in fids:
            info = TEMP_STORAGE.get(fid)
            if info and 'converted_data' in info:
                zf.writestr(info['download_name'], info['converted_data'])
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='All_Converted_Files.zip')

if __name__ == '__main__':
    app.run(debug=True)