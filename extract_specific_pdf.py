
import PyPDF2
import os

file_path = "/Users/zhizinan/Desktop/YX_Website/fuwuanli/元芯传感 涉氢全场景公众号文系列创作.pdf"
output_file = "/Users/zhizinan/Desktop/YX_Website/pdf_extraction_result.txt"

print(f"Extracting from: {file_path}")

try:
    with open(output_file, 'w', encoding='utf-8') as out:
        out.write(f"--- Extracted Content from {os.path.basename(file_path)} ---\n")
        
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)
                print(f"Number of pages: {num_pages}")
                
                for i, page in enumerate(reader.pages):
                    out.write(f"\n[Page {i+1}]\n")
                    text = page.extract_text()
                    out.write(text if text else "[No text extracted]")
                    out.write("\n" + "-"*30 + "\n")
        else:
            out.write(f"File not found: {file_path}\n")
            print("File not found!")

    print(f"Extraction complete. Saved to {output_file}")

except Exception as e:
    print(f"Error: {e}")
