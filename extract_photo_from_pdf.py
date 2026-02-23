#!/usr/bin/env python3
"""Extract photos/images from PDF file"""

import os
import sys
from pathlib import Path
from PIL import Image

def extract_photos_from_pdf(pdf_path: str, output_dir: str = None) -> list:
    """Extract all images from PDF using PIL"""
    
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ Plik nie istnieje: {pdf_path}")
        return []
    
    if output_dir is None:
        output_dir = pdf_file.parent / "extracted_photos"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📄 Otwieranie PDF: {pdf_file.name}")
    print(f"📁 Zapis do: {output_dir}")
    
    extracted_images = []
    
    try:
        # Use PIL to open and convert PDF pages to images
        img = Image.open(pdf_file)
        
        page_count = 1
        
        # Get number of pages if available
        try:
            while True:
                img.seek(img.n_frames - 1)
                page_count = img.n_frames
                break
        except:
            try:
                img.seek(0)
                # Try to get number of pages
                for _ in range(1000):
                    try:
                        img.seek(img.tell() + 1)
                    except EOFError:
                        page_count = img.tell() + 1
                        break
            except:
                page_count = 1
        
        img.seek(0)
        page_num = 1
        
        print(f"   Liczba stron: {page_count}")
        
        image_count = 0
        
        while page_num <= page_count:
            try:
                print(f"\n📖 Strona {page_num}/{page_count}")
                
                # Convert PDF page to RGB
                img_rgb = img.convert('RGB')
                
                image_count += 1
                filename = f"photo_{image_count:02d}_page{page_num}.png"
                filepath = output_dir / filename
                
                img_rgb.save(filepath, "PNG")
                
                size_kb = filepath.stat().st_size / 1024
                width, height = img_rgb.size
                print(f"   ✅ {filename} ({size_kb:.1f} KB) - {width}x{height}px")
                extracted_images.append(str(filepath))
                
                # Try to move to next page
                try:
                    img.seek(page_num)
                    page_num += 1
                except (EOFError, AttributeError):
                    break
            except Exception as e:
                print(f"   ⚠️  Błąd na stronie {page_num}: {e}")
                try:
                    img.seek(page_num)
                    page_num += 1
                except:
                    break
    
    except Exception as e:
        print(f"❌ Błąd podczas przetwarzania PDF: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    print(f"\n📊 Podsumowanie:")
    print(f"   Całkowicie wyekstrahowano: {len(extracted_images)} obrazów")
    if extracted_images:
        print(f"   Lokalizacja: {output_dir}")
        for img_path in extracted_images:
            print(f"     → {Path(img_path).name}")
    
    return extracted_images
    
    return extracted_images


if __name__ == "__main__":
    # Find the PDF file
    pdf_path = Path(os.path.expanduser("~")) / "Desktop"
    
    # Look for the CV PDF
    pdf_files = list(pdf_path.glob("CV_Mariusz*.pdf"))
    
    if not pdf_files:
        print("❌ Nie znaleziono pliku CV_Mariusz*.pdf na Desktop")
        sys.exit(1)
    
    pdf_file = str(pdf_files[0])
    print(f"🔍 Znaleziony plik: {Path(pdf_file).name}\n")
    
    # Extract images
    extract_photos_from_pdf(pdf_file)
