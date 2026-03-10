# database.py
import sqlite3
import os
import json
import numpy as np
from config import DATABASE_PATH

def get_db_connection():
    """Database connection banata hai"""
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Dictionary-like access
    return conn

def init_database():
    """Database tables create karta hai - pehli baar chalao"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Photos table - har uploaded photo ka record
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            filepath TEXT NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_size INTEGER,
            has_faces BOOLEAN DEFAULT 0,
            face_count INTEGER DEFAULT 0
        )
    ''')
    
    # Faces table - har photo me detected faces ka encoding
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            encoding TEXT NOT NULL,
            face_location TEXT,
            FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
    ''')
    
    # Index for faster queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_photo_id ON faces(photo_id)
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

def save_photo_record(filename, original_name, filepath, file_size):
    """Photo ka record database me save karta hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO photos (filename, original_name, filepath, file_size)
        VALUES (?, ?, ?, ?)
    ''', (filename, original_name, filepath, file_size))
    
    photo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return photo_id

def update_photo_face_info(photo_id, has_faces, face_count):
    """Photo record me face info update karta hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE photos 
        SET has_faces = ?, face_count = ?
        WHERE id = ?
    ''', (has_faces, face_count, photo_id))
    
    conn.commit()
    conn.close()

def save_face_encoding(photo_id, encoding, face_location):
    """Face encoding database me save karta hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Numpy array ko JSON string me convert karo
    encoding_str = json.dumps(encoding.tolist())
    location_str = json.dumps(face_location)
    
    cursor.execute('''
        INSERT INTO faces (photo_id, encoding, face_location)
        VALUES (?, ?, ?)
    ''', (photo_id, encoding_str, location_str))
    
    conn.commit()
    conn.close()

def get_all_face_encodings():
    """Saari face encodings database se lata hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT f.id, f.photo_id, f.encoding, f.face_location,
               p.filename, p.original_name, p.filepath
        FROM faces f
        JOIN photos p ON f.photo_id = p.id
    ''')
    
    results = []
    for row in cursor.fetchall():
        encoding = np.array(json.loads(row['encoding']))
        results.append({
            'face_id': row['id'],
            'photo_id': row['photo_id'],
            'encoding': encoding,
            'face_location': json.loads(row['face_location']),
            'filename': row['filename'],
            'original_name': row['original_name'],
            'filepath': row['filepath']
        })
    
    conn.close()
    return results

def get_all_photos():
    """Saari photos ka record lata hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM photos ORDER BY upload_date DESC
    ''')
    
    photos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return photos

def get_photo_by_id(photo_id):
    """Specific photo ka record lata hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM photos WHERE id = ?', (photo_id,))
    photo = cursor.fetchone()
    
    conn.close()
    return dict(photo) if photo else None

def delete_photo(photo_id):
    """Photo ka record delete karta hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Pehle photo info lo (file delete karne ke liye)
    cursor.execute('SELECT filepath FROM photos WHERE id = ?', (photo_id,))
    photo = cursor.fetchone()
    
    if photo:
        # Database se delete karo (faces bhi cascade delete ho jayengi)
        cursor.execute('DELETE FROM faces WHERE photo_id = ?', (photo_id,))
        cursor.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
        conn.commit()
        
        # File bhi delete karo
        if os.path.exists(photo['filepath']):
            os.remove(photo['filepath'])
    
    conn.close()

def get_total_stats():
    """Total statistics return karta hai"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total FROM photos')
    total_photos = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM faces')
    total_faces = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM photos WHERE has_faces = 1')
    photos_with_faces = cursor.fetchone()['total']
    
    conn.close()
    
    return {
        'total_photos': total_photos,
        'total_faces': total_faces,
        'photos_with_faces': photos_with_faces
    }