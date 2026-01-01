import zipfile
import io
import uuid
import os
from flask import Flask, request, jsonify, send_file, render_template
from PIL import Image

app = Flask(__name__)
app.config['SECRET_KEY'] = 'yas_ultimate_converter_2026'

# Storage Sementara
TEMP_STORAGE = {} 

# Mapping Mime Type Lengkap
MIMETYPE_MAP = {
    'png': 'image/png',
    'bmp': 'image/bmp',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'tga': 'image/x-tga',
    'ico': 'image/x-icon',
    'tiff': 'image/tiff',
    'gif': 'image/gif',
    'pdf': 'application/pdf'
}

def convert_image_universal(img_stream, target_format):
    try:
        # Load Image (Pillow otomatis support DDS, PSD, TGA, ICNS, dll sebagai INPUT)
        img = Image.open(img_stream)
        output_stream = io.BytesIO()
        fmt = target_format.lower()
        
        # --- LOGIKA KONVERSI ---
        
        if fmt == 'bmp':
            # CS 1.6: Wajib 8-bit (256 color) + No Dither
            if img.mode != 'RGB': img = img.convert('RGB')
            img = img.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE, dither=Image.Dither.NONE)
            img.save(output_stream, 'BMP')

        elif fmt == 'tga':
            # CS 1.6 VGUI/HUD: Butuh Alpha Channel (RGBA) jika transparan
            # Jika tidak ada transparansi, RGB biasa.
            if 'A' in img.mode or 'transparency' in img.info:
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')
            # RLE Compression wajib agar file tidak kegedean
            img.save(output_stream, 'TGA', rle=True)

        elif fmt == 'png':
            img.save(output_stream, 'PNG', optimize=True)
            
        elif fmt == 'ico':
            # Icon biasanya butuh ukuran spesifik, tapi kita simpan apa adanya dulu
            if 'A' in img.mode: img = img.convert('RGBA')
            # ICO support multiple sizes, here we just save the current one
            img.save(output_stream, 'ICO')

        elif fmt in ['jpg', 'jpeg']:
            if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
            img.save(output_stream, 'JPEG', quality=95, subsampling=0)

        elif fmt == 'webp':
            img.save(output_stream, 'WEBP', quality=95)

        elif fmt == 'tiff':
            img.save(output_stream, 'TIFF', compression='tiff_deflate')

        else:
            # Fallback untuk format umum lainnya
            if img.mode != 'RGB': img = img.convert('RGB')
            img.save(output_stream, fmt.upper())
            
        output_stream.seek(0)
        return output_stream

    except Exception as e:
        print(f"Error Konversi: {e}")
        return None

def process_file(file_id, file_info, target_format):
    try:
        is_zip = file_info['filename'].lower().endswith('.zip')
        
        if is_zip:
            zip_out = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(file_info['data']), 'r') as z_in:
                with zipfile.ZipFile(zip_out, 'w', zipfile.ZIP_DEFLATED) as z_out:
                    for name in z_in.namelist():
                        if name.endswith('/') or '__MACOSX' in name: continue
                        # Cek ekstensi input yang didukung (DDS, PSD, TGA, dll)
                        if any(name.lower().endswith(x) for x in ['.png','.jpg','.jpeg','.webp','.bmp','.tga','.dds','.psd','.tif','.tiff','.ico']):
                            try:
                                img_data = z_in.read(name)
                                conv = convert_image_universal(io.BytesIO(img_data), target_format)
                                if conv:
                                    # Ganti ekstensi file hasil
                                    new_name = os.path.splitext(name)[0] + '.' + target_format
                                    z_out.writestr(new_name, conv.getvalue())
                            except Exception as e:
                                print(f"Skip file error {name}: {e}")

            result_data = zip_out.getvalue()
            out_name = f"YasConvert_Result_{target_format.upper()}.zip"
            mime = "application/zip"
        
        else:
            conv = convert_image_universal(io.BytesIO(file_info['data']), target_format)
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
    TEMP_STORAGE[fid] = {'filename': f.filename, 'data': f.read(), 'status': 'uploaded'}
    return jsonify({'success': True, 'file_id': fid, 'filename': f.filename})

@app.route('/convert', methods=['POST'])
def convert():
    data = request.json
    fid = data.get('file_id')
    fmt = data.get('format', 'bmp') 
    
    info = TEMP_STORAGE.get(fid)
    if not info: return jsonify({'success': False, 'msg': 'File hilang'})
    
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