
import PyPDF2
import os

files = [
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\微水传感器规格书.pdf",
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\微水传感器网页.pdf",
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\油中氢规格书.pdf",
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\油中氢网页.pdf"
]

output_file = "pdf_content.txt"

with open(output_file, 'w', encoding='utf-8') as out:
    for file_path in files:
        out.write(f"--- Extracting from: {os.path.basename(file_path)} ---\n")
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                # Read all pages
                for i, page in enumerate(reader.pages):
                    out.write(f"[Page {i+1}]\n")
                    text = page.extract_text()
                    out.write(text if text else "[No text extracted]")
                    out.write("\n")
        except Exception as e:
            out.write(f"Error reading file: {e}\n")
        out.write("\n" + "="*50 + "\n\n")

print("Extraction complete.")
