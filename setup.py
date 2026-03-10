# setup.py
"""
Ye script pehli baar chalao - sab kuch setup kar dega
"""
import os
import sys

def setup():
    print("=" * 50)
    print("🚀 Face Search App - Setup")
    print("=" * 50)
    
    # 1. Directories create karo
    directories = [
        'static/uploads',
        'static/css',
        'static/js',
        'data',
        'templates'
    ]
    
    for dir_path in directories:
        os.makedirs(dir_path, exist_ok=True)
        print(f"✅ Directory created: {dir_path}")
    
    # 2. Database initialize karo
    from database import init_database
    init_database()
    print("✅ Database initialized!")
    
    # 3. Check dependencies
    print("\n📦 Checking dependencies...")
    
    required_packages = [
        'flask',
        'face_recognition',
        'cv2',
        'numpy',
        'PIL'
    ]
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package} - installed")
        except ImportError:
            print(f"  ❌ {package} - NOT installed!")
            print(f"     Run: pip install {package}")
    
    print("\n" + "=" * 50)
    print("✅ Setup complete!")
    print("=" * 50)
    print("\n🎯 Ab app start karne ke liye ye command run karo:")
    print("   python app.py")
    print("\n🌐 Phir browser me kholo:")
    print("   http://127.0.0.1:5000")
    print("=" * 50)

if __name__ == '__main__':
    setup()