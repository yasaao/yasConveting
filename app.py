# --- PASTIKAN IMPORT INI ADA DI ATAS ---
from flask import Flask, request, jsonify, send_file, render_template
import io

# ... (Kode fungsi convert_image_universal dan process_file BIARKAN SAMA) ...

# --- TAMBAHKAN ROUTE BARU INI DI BAWAH ROUTE UPLOAD ---

@app.route('/gen_preview', methods=['POST'])
def gen_preview():
    """
    Endpoint khusus untuk generate preview file yang tidak disupport browser
    (seperti TGA, DDS, PSD, TIFF).
    Mengembalikan gambar dalam format PNG agar bisa dilihat di tag <img>.
    """
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    f = request.files['file']
    
    try:
        # Buka gambar (Pillow support TGA & DDS)
        img = Image.open(f)
        
        # Konversi ke RGB/RGBA agar aman jadi PNG
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA')
            
        # Resize jika terlalu besar (biar preview cepat loadingnya)
        # Max width/height 500px cukup untuk preview
        img.thumbnail((500, 500))
        
        # Simpan ke memori sebagai PNG
        output = io.BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        
        return send_file(output, mimetype='image/png')
        
    except Exception as e:
        print(f"Preview Error: {e}")
        return jsonify({'error': 'Failed to preview'}), 500

# ... (Sisa kode routes lain biarkan sama) ...