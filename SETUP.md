# Similarity.lk — Setup Instructions

## Python dependencies
```bash
pip install -r requirements.txt
```

## System dependencies

### Linux/macOS
```bash
# Poppler (for pdf2image)
sudo apt-get install poppler-utils          # Ubuntu/Debian
brew install poppler                        # macOS

# Tesseract + Sinhala language pack (for legacy PDF OCR)
sudo apt-get install tesseract-ocr tesseract-ocr-sin   # Ubuntu/Debian
brew install tesseract                      # macOS (then add sinhala tessdata)

# WeasyPrint GTK runtime (Linux usually already has this)
sudo apt-get install libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
```

### Windows
```bash
# 1. Install Poppler: https://github.com/oschwartz10612/poppler-windows/releases
#    Add bin/ folder to PATH

# 2. Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
#    Choose "sin" (Sinhala) during installation, or copy sin.traineddata to tessdata/

# 3. Install Playwright Chromium (used instead of WeasyPrint on Windows):
playwright install chromium
```

## Run
```bash
# Place pkl model files into models/
python app.py   # → http://localhost:5000
```

## Login
| Username   | Password     |
|------------|--------------|
| admin      | admin123     |
| researcher | research2026 |
