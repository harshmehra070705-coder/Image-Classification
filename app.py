import os
import uuid
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify
)
from werkzeug.utils import secure_filename

from config import *
from database import (
    init_database, save_photo_record, get_all_photos,
    delete_photo, get_total_stats
)
from face_utils import (
    detect_and_encode_faces, search_similar_faces,
    validate_image, resize_image_if_needed,
    normalize_to_jpeg
)

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

init_database()


def allowed_file(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower().strip()
    return ext in ALLOWED_EXTENSIONS


def generate_unique_filename(force_ext: str) -> str:
    force_ext = force_ext.lower().strip('.')
    return f"{uuid.uuid4().hex}.{force_ext}"


@app.route('/')
def index():
    stats = get_total_stats()
    recent_photos = get_all_photos()[:12]
    return render_template('index.html', stats=stats, photos=recent_photos)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'photos' not in request.files:
            flash('Koi file select nahi ki!', 'error')
            return redirect(request.url)

        files = request.files.getlist('photos')
        if not files or files[0].filename == '':
            flash('Koi file select nahi ki!', 'error')
            return redirect(request.url)

        uploaded_count = 0
        total_faces = 0
        errors = []

        for file in files:
            if not file or file.filename == '':
                continue

            original_name = secure_filename(file.filename)

            if not allowed_file(original_name):
                errors.append(f'{original_name}: Ye format allowed nahi hai')
                continue

            # 1) save temp file (original extension)
            tmp_ext = original_name.rsplit('.', 1)[1].lower()
            tmp_filename = generate_unique_filename(tmp_ext)
            tmp_path = os.path.join(app.config['UPLOAD_FOLDER'], tmp_filename)
            file.save(tmp_path)

            # 2) validate image decode
            if not validate_image(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                errors.append(f'{original_name}: Valid image nahi hai / decode nahi hua')
                continue

            # 3) normalize to final JPG
            final_filename = generate_unique_filename("jpg")
            final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)

            try:
                normalize_to_jpeg(tmp_path, output_path=final_path, max_size=4000)
            except Exception as e:
                errors.append(f'{original_name}: JPG convert fail -> {str(e)}')
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                continue
            finally:
                # remove temp
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

            # 4) save DB record
            file_size = os.path.getsize(final_path)
            photo_id = save_photo_record(final_filename, original_name, final_path, file_size)

            # 5) face detection + encoding
            result = detect_and_encode_faces(final_path, photo_id)

            uploaded_count += 1
            total_faces += int(result.get("faces_found", 0))

            if not result.get("success", True):
                errors.append(f"{original_name}: Face encode error -> {result.get('message')}")

        if uploaded_count > 0:
            flash(f'{uploaded_count} photo(s) upload ho gayi! {total_faces} face(s) detect hue!', 'success')

        for e in errors:
            flash(e, 'error')

        return redirect(url_for('upload'))

    return render_template('upload.html')


@app.route('/search', methods=['GET', 'POST'])
def search():
    results = None

    if request.method == 'POST':
        if 'search_photo' not in request.files:
            flash('Search ke liye ek photo select karo!', 'error')
            return redirect(request.url)

        file = request.files['search_photo']

        if not file or file.filename == '':
            flash('Koi file select nahi ki!', 'error')
            return redirect(request.url)

        original_name = secure_filename(file.filename)

        if not allowed_file(original_name):
            flash('Ye file format allowed nahi hai!', 'error')
            return redirect(request.url)

        # temp save
        tmp_ext = original_name.rsplit('.', 1)[1].lower()
        tmp_name = f"search_{uuid.uuid4().hex}.{tmp_ext}"
        tmp_path = os.path.join(app.config['UPLOAD_FOLDER'], tmp_name)
        file.save(tmp_path)

        if not validate_image(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            flash('Search image valid nahi hai / decode nahi hua', 'error')
            return redirect(request.url)

        # normalize to jpg
        final_name = f"search_{uuid.uuid4().hex}.jpg"
        final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_name)

        try:
            normalize_to_jpeg(tmp_path, output_path=final_path, max_size=4000)
        except Exception as e:
            flash(f'Search JPG convert fail: {str(e)}', 'error')
            return redirect(request.url)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        results = search_similar_faces(final_path)
        results['search_image'] = final_name

        if results.get('success'):
            if results.get('results'):
                flash(f"{len(results['results'])} matching photo(s) mili!", 'success')
            else:
                flash('Koi matching photo nahi mili.', 'warning')
        else:
            flash(results.get('message', 'Search failed'), 'error')

    return render_template('search.html', results=results)


@app.route('/gallery')
def gallery():
    photos = get_all_photos()
    return render_template('gallery.html', photos=photos)


@app.route('/delete/<int:photo_id>', methods=['POST'])
def delete_photo_route(photo_id):
    delete_photo(photo_id)
    flash('Photo delete ho gayi!', 'success')
    return redirect(url_for('gallery'))


@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'No file'})

    file = request.files['photo']
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})

    original_name = secure_filename(file.filename)
    if not allowed_file(original_name):
        return jsonify({'success': False, 'message': 'Invalid file format'})

    # temp save
    tmp_ext = original_name.rsplit('.', 1)[1].lower()
    tmp_filename = generate_unique_filename(tmp_ext)
    tmp_path = os.path.join(app.config['UPLOAD_FOLDER'], tmp_filename)
    file.save(tmp_path)

    if not validate_image(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Invalid/corrupt image'})

    # normalize to jpg
    final_filename = generate_unique_filename("jpg")
    final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)

    try:
        normalize_to_jpeg(tmp_path, output_path=final_path, max_size=4000)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Convert failed: {str(e)}'})
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    file_size = os.path.getsize(final_path)
    photo_id = save_photo_record(final_filename, original_name, final_path, file_size)
    result = detect_and_encode_faces(final_path, photo_id)

    return jsonify({
        'success': bool(result.get('success', True)),
        'photo_id': photo_id,
        'filename': final_filename,
        'faces_found': int(result.get('faces_found', 0)),
        'message': result.get('message', '')
    })


@app.route('/api/search', methods=['POST'])
def api_search():
    if 'photo' not in request.files:
        return jsonify({'success': False, 'message': 'No file'})

    file = request.files['photo']
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})

    original_name = secure_filename(file.filename)
    if not allowed_file(original_name):
        return jsonify({'success': False, 'message': 'Invalid file format'})

    tmp_ext = original_name.rsplit('.', 1)[1].lower()
    tmp_name = f"search_{uuid.uuid4().hex}.{tmp_ext}"
    tmp_path = os.path.join(app.config['UPLOAD_FOLDER'], tmp_name)
    file.save(tmp_path)

    if not validate_image(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return jsonify({'success': False, 'message': 'Invalid/corrupt image'})

    final_name = f"search_{uuid.uuid4().hex}.jpg"
    final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_name)

    try:
        normalize_to_jpeg(tmp_path, output_path=final_path, max_size=4000)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Convert failed: {str(e)}'})
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    results = search_similar_faces(final_path)
    results['search_image'] = final_name
    return jsonify(results)


@app.route('/api/stats')
def api_stats():
    return jsonify(get_total_stats())


@app.errorhandler(413)
def too_large(e):
    flash('File bahut badi hai!', 'error')
    return redirect(url_for('upload'))


@app.errorhandler(404)
def not_found(e):
    return render_template('base.html', error="Page not found!"), 404


if __name__ == '__main__':
    print("Upload folder:", UPLOAD_FOLDER)
    print("Database:", DATABASE_PATH)
    app.run(debug=True, host='0.0.0.0', port=5000)