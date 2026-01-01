import zipfile
import io
import uuid
import os
from flask import Flask, request, jsonify, send_file, render_template
from PIL import Image

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yas_cs16_special_key'

# Storage Sementara
TEMP_STORAGE = {} 

MIMETYPE_MAP = {
    'png': 'image/png',
    'bmp': 'image/bmp',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp'
}

def convert_image_cs16(img_stream, target_format):
    """
    Logika Konversi Spesial:
    - BMP: Wajib 8-bit (Indexed 256 colors) untuk CS 1.6.
    - Dither: OFF (Agar tidak ada efek 'agar-agar'/bintik noise).
    """
    try:
        img = Image.open(img_stream)
        output_stream = io.BytesIO()
        fmt = target_format.lower()
        
        if fmt == 'bmp':
            # LANGKAH 1: Pastikan Image dalam mode RGB dulu
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # LANGKAH 2: Konversi ke 8-bit (256 Warna) untuk Engine GoldSource
            # PENTING: dither=Image.Dither.NONE (Ini yang menghilangkan efek 'agar-agar')
            # method=Image.Quantize.MAXCOVERAGE (Mencari warna paling akurat)
            img = img.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE)
            
            # LANGKAH 3: Simpan sebagai BMP
            img.save(output_stream, 'BMP')

        elif fmt == 'png':
            img.save(output_stream, 'PNG', optimize=True)
            
        elif fmt in ['jpg', 'jpeg']:
            if img.mode in ('RGBA', 'P'): 
                img = img.convert('RGB')
            img.save(output_stream, 'JPEG', quality=95, subsampling=0)

        elif fmt == 'webp':
            img.save(output_stream, 'WEBP', quality=95)

        else:
            # Fallback
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(output_stream, fmt.upper())
            
        output_stream.seek(0)
        return output_stream

    except Exception as e:
        print(f"Error Konversi: {e}")
        return None

def process_file(file_id, file_info, target_format):
    try:
        # Cek apakah ZIP atau Single File
        is_zip = file_info['filename'].lower().endswith('.zip')
        
        if is_zip:
            # Handle ZIP Batch Processing
            zip_out = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(file_info['data']), 'r') as z_in:
                with zipfile.ZipFile(zip_out, 'w', zipfile.ZIP_DEFLATED) as z_out:
                    for name in z_in.namelist():
                        if name.endswith('/') or '__MACOSX' in name: continue
                        if any(name.lower().endswith(x) for x in ['.png','.jpg','.jpeg','.webp','.bmp']):
                            img_data = z_in.read(name)
                            conv = convert_image_cs16(io.BytesIO(img_data), target_format)
                            if conv:
                                new_name = os.path.splitext(name)[0] + '.' + target_format
                                z_out.writestr(new_name, conv.getvalue())
            
            result_data = zip_out.getvalue()
            out_name = "YasConvert_CS16_Result.zip"
            mime = "application/zip"
        
        else:
            # Handle Single File
            conv = convert_image_cs16(io.BytesIO(file_info['data']), target_format)
            if not conv: raise Exception("Gagal convert")
            
            result_data = conv.getvalue()
            name_only = os.path.splitext(file_info['filename'])[0]
            out_name = f"{name_only}.{target_format}"
            mime = MIMETYPE_MAP.get(target_format, 'application/octet-stream')

        # Update Storage
        file_info.update({
            'converted_data': result_data,
            'download_name': out_name,
            'converted_mime': mime,
            'status': 'completed'
        })
        return True

    except Exception as e:
        print(f"Error Processing: {e}")
        return False

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({'success': False})
    f = request.files['file']
    if not f.filename: return jsonify({'success': False})
    
    fid = str(uuid.uuid4())
    TEMP_STORAGE[fid] = {
        'filename': f.filename,
        'data': f.read(),
        'status': 'uploaded'
    }
    return jsonify({'success': True, 'file_id': fid, 'filename': f.filename})

@app.route('/convert', methods=['POST'])
def convert():
    data = request.json
    fid = data.get('file_id')
    fmt = data.get('format', 'bmp') 
    
    info = TEMP_STORAGE.get(fid)
    if not info: return jsonify({'success': False, 'msg': 'File hilang/expired'})
    
    success = process_file(fid, info, fmt)
    if success:
        return jsonify({'success': True, 'file_id': fid, 'name': info['download_name']})
    else:
        return jsonify({'success': False, 'msg': 'Gagal convert'})

@app.route('/download/<fid>')
def download(fid):
    info = TEMP_STORAGE.get(fid)
    if not info or 'converted_data' not in info: return "File not found", 404
    return send_file(
        io.BytesIO(info['converted_data']),
        mimetype=info['converted_mime'],
        as_attachment=True,
        download_name=info['download_name']
    )

if __name__ == '__main__':
    app.run(debug=True)