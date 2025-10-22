# app.py (Dioptimalkan untuk Vercel Serverless)

import zipfile
import io
import time # Untuk simulasi loading, bisa dihapus
import uuid
import os # Diperlukan untuk os.path.splitext

from flask import Flask, render_template, request, jsonify, send_file, session
from PIL import Image, ImagePalette # <-- Tambahkan ImagePalette (opsional, tapi baik untuk kejelasan)

# Vercel tidak mendukung threading untuk polling/background jobs.
# Proses akan dijalankan secara sinkron di endpoint /start_conversion.

# --------------------------
# KONFIGURASI & STORAGE APLIKASI
# --------------------------
app = Flask(__name__)
# Ganti dengan kunci rahasia unik Anda
# JANGAN GUNAKAN NILAI DEFAULT INI UNTUK PRODUKSI, GANTI DENGAN STRING ACAK YANG KUAT!
app.config['SECRET_KEY'] = 'yasabcdefghijklmnooaowowjsnxmxopqpowdixjxnzkapqpqowoeoeodjxxnnxospwodkxnccnxoeowosn' 
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# Storage In-Memory: Data file sementara yang diupload
# Di Vercel, ini akan di-reset setelah endpoint selesai.
TEMP_STORAGE = {} 

MIMETYPE_MAP = {
    'png': 'image/png',
    'bmp': 'image/bmp',
    'tga': 'image/x-tga'
}

# --------------------------
# FUNGSI UTILITAS KONVERSI
# --------------------------
def convert_image(img_stream, target_format):
    """Mengonversi stream gambar (BytesIO) ke format target, termasuk BMP 8-bit Indexed."""
    try:
        img = Image.open(img_stream)
        output_stream = io.BytesIO()
        save_format = target_format.upper()
        
        # --- LOGIKA KONVERSI DENGAN PENGECEKAN MODE GAMBAR ---
        
        if save_format == 'PNG':
            # Logika standar PNG (mempertahankan transparansi)
            if 'A' in img.mode: 
                img = img.convert('RGBA')
            elif img.mode == 'P' and 'transparency' in img.info:
                img = img.convert('RGBA')
            elif img.mode != 'RGB':
                 img = img.convert('RGB')
            img.save(output_stream, 'PNG')
            
        elif save_format == 'BMP':
            # LOGIKA BMP 8-BIT INDEXED (Mode 'P') untuk Modding CS 1.6
            
            # 1. Pastikan gambar dalam mode RGB/RGBA terlebih dahulu agar konversi ke palet optimal
            if img.mode not in ('RGB', 'RGBA', 'L'):
                 img = img.convert('RGB')
                 
            # 2. Paksa konversi ke mode 'P' (Paletted/Indexed Color) 8-bit
            # Menggunakan palet ADAPTIVE untuk kuantisasi warna terbaik (256 warna)
            img_paletted = img.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
            
            # 3. Simpan sebagai BMP
            img_paletted.save(output_stream, 'BMP')
            
        elif save_format == 'TGA':
            # Logika standar TGA (mempertahankan transparansi)
            if 'A' in img.mode:
                 img = img.convert('RGBA')
            elif img.mode != 'RGB':
                 img = img.convert('RGB')
            img.save(output_stream, 'TGA', rle=True) # rle=True untuk kompresi TGA

        else:
            raise ValueError(f"Format target tidak didukung: {target_format}")
            
        output_stream.seek(0)
        return output_stream

    except Exception as e:
        print(f"!!! Error Konversi: Format {target_format} gagal. Pesan: {e}")
        return None

def process_single_file_or_zip(file_id, file_info, target_format):
    """Memproses konversi untuk satu file atau ZIP."""
    original_filename = file_info['filename']
    file_data = file_info['data']
    original_filename_root, original_extension = os.path.splitext(original_filename)
    is_zip = original_extension.lower() == '.zip'
    
    output_filename = ""
    try:
        if is_zip:
            zip_input_stream = io.BytesIO(file_data)
            zip_output_stream = io.BytesIO()
            
            # Memproses ZIP
            with zipfile.ZipFile(zip_input_stream, 'r') as zip_in:
                # Memberi nama file ZIP output dengan format yang diminta
                output_filename = f"{original_filename_root}_yasConvert!_{target_format}.zip"

                with zipfile.ZipFile(zip_output_stream, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                    
                    # Cek file_list dari zip_in
                    files_in_zip = zip_in.namelist()
                    if not files_in_zip:
                        raise Exception("ZIP kosong atau tidak valid.")
                        
                    for filename in files_in_zip:
                        # Abaikan direktori
                        if filename.endswith('/'):
                            continue

                        # Logika sederhana untuk cek gambar
                        if any(filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tga', '.webp', '.tiff']):
                            try:
                                image_data = zip_in.read(filename)
                                converted_stream = convert_image(io.BytesIO(image_data), target_format)
                                
                                if converted_stream:
                                    # Pastikan nama file baru hanya memiliki ekstensi target
                                    base_name = os.path.splitext(os.path.basename(filename))[0]
                                    new_filename = base_name + '.' + target_format
                                    zip_out.writestr(new_filename, converted_stream.getvalue())
                                else:
                                    # Konversi gambar di dalam ZIP gagal
                                    print(f"Konversi file dalam ZIP gagal: {filename}")
                                    
                            except Exception as e_zip_internal:
                                print(f"Error memproses file {filename} dalam ZIP: {e_zip_internal}")
                                
            zip_output_stream.seek(0)
            
            file_info['converted_data'] = zip_output_stream.getvalue()
            file_info['download_name'] = output_filename
            file_info['converted_mime'] = 'application/zip'
            
        else:
            # Logika Konversi File Tunggal
            converted_stream = convert_image(io.BytesIO(file_data), target_format)

            if not converted_stream:
                raise Exception("Gagal mengonversi gambar. Lihat console server untuk detail.")
                
            output_filename = f"{original_filename_root}_converted.{target_format}"
            
            file_info['converted_data'] = converted_stream.getvalue()
            file_info['download_name'] = output_filename
            file_info['converted_mime'] = MIMETYPE_MAP.get(target_format, 'application/octet-stream')

        # Berhasil
        file_info['status'] = 'completed'
        return {'file_id': file_id, 'status': 'completed', 'download_name': output_filename}

    except Exception as e:
        # Gagal
        print(f"!!! Error Fatal Saat Memproses {original_filename}: {e}")
        file_info['status'] = 'error'
        return {'file_id': file_id, 'status': 'error', 'message': f"Error: {e}"}

# --------------------------
# ROUTES FLASK
# --------------------------

@app.route('/', methods=['GET'])
def index():
    # Bersihkan session saat kembali ke halaman utama
    session.pop('uploaded_files', None)
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Menerima file tunggal via AJAX."""
    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'success': False, 'message': 'Tidak ada file dipilih'}), 400
    
    uploaded_file = request.files['file']
    file_id = str(uuid.uuid4())
    
    try:
        file_bytes = uploaded_file.read()
        if not file_bytes:
             return jsonify({'success': False, 'message': 'File kosong atau gagal dibaca'}), 400
    except Exception as e:
        print(f"!!! GAGAL MEMBACA FILE DARI REQUEST: {e}")
        return jsonify({'success': False, 'message': f'File terlalu besar atau error server saat upload: {e}'}), 500

    # Simpan data file di memori. 
    TEMP_STORAGE[file_id] = {
        'filename': uploaded_file.filename,
        'data': file_bytes,
        'mime': uploaded_file.mimetype,
        'status': 'uploaded'
    }
    
    if 'uploaded_files' not in session:
        session['uploaded_files'] = []
    
    session['uploaded_files'].append(file_id)
    session.modified = True
    
    return jsonify({
        'success': True, 
        'file_id': file_id, 
        'filename': uploaded_file.filename
    })

@app.route('/remove/<file_id>', methods=['POST'])
def remove_file(file_id):
    # Hapus dari storage
    if file_id in TEMP_STORAGE:
        del TEMP_STORAGE[file_id]
    
    # Hapus dari sesi
    if 'uploaded_files' in session and file_id in session['uploaded_files']:
        session['uploaded_files'].remove(file_id)
        session.modified = True
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'message': 'File tidak ditemukan'}), 404

@app.route('/start_conversion', methods=['POST'])
def start_conversion():
    """Melakukan konversi secara sinkron (sekuensial) di endpoint Vercel."""
    data = request.get_json()
    target_format = data.get('format', 'png').lower()
    file_ids = data.get('file_ids', [])

    if not file_ids:
        return jsonify({'success': False, 'message': 'Tidak ada file untuk dikonversi'}), 400
    
    results = []

    # Iterasi dan konversi setiap file secara sekuensial
    for file_id in file_ids:
        file_info = TEMP_STORAGE.get(file_id)
        if not file_info or file_info.get('status') != 'uploaded':
            results.append({'file_id': file_id, 'status': 'error', 'message': 'File hilang atau belum siap'})
            continue
            
        # Perbarui status untuk feedback di UI (walaupun singkat)
        file_info['status'] = 'converting'
        
        # Lakukan pemrosesan
        result = process_single_file_or_zip(file_id, file_info, target_format)
        results.append(result)
        
    # Setelah semua file diproses, kembalikan hasil secara langsung
    return jsonify({
        'success': True, 
        'status': 'completed', 
        'results': results,
    })

@app.route('/download/<file_id>', methods=['GET'])
def download_file(file_id):
    """Menyajikan file yang sudah dikonversi dari memori."""
    file_info = TEMP_STORAGE.get(file_id)
    
    if not file_info or 'converted_data' not in file_info:
        return "File konversi tidak ditemukan atau belum selesai.", 404
    
    # Hapus data file mentah untuk menghemat memori setelah diunduh
    file_info.pop('data', None)
    
    return send_file(
        io.BytesIO(file_info['converted_data']),
        mimetype=file_info['converted_mime'],
        as_attachment=True,
        download_name=file_info['download_name']
    )


if __name__ == '__main__':
    # Tidak digunakan di Vercel, hanya untuk local testing
    app.run(debug=True)
