
import PyPDF2
from PIL import Image
import io
import os

files = [
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\微水传感器规格书.pdf",
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\微水传感器网页.pdf",
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\油中氢规格书.pdf",
    r"C:\Users\34697\Desktop\微水&油中氢(2)\微水&油中氢\油中氢网页.pdf"
]

output_dir = "extracted_images"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

def remove_white_background(img, threshold=240):
    img = img.convert("RGBA")
    datas = img.getdata()
    new_data = []
    for item in datas:
        if item[0] > threshold and item[1] > threshold and item[2] > threshold:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)
    return img

print("Starting image extraction...")

count = 0
for file_path in files:
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    print(f"Processing: {base_name}")
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(reader.pages):
                if '/XObject' in page['/Resources']:
                    xObject = page['/Resources']['/XObject'].get_object()
                    for obj in xObject:
                        if xObject[obj]['/Subtype'] == '/Image':
                            try:
                                size = (xObject[obj]['/Width'], xObject[obj]['/Height'])
                                data = xObject[obj]._data
                                if xObject[obj]['/Filter'] == '/FlateDecode':
                                    img = Image.frombytes(xObject[obj]['/ColorSpace'] == '/DeviceRGB' and "RGB" or "CMYK", size, data)
                                else:
                                    img = Image.open(io.BytesIO(data))
                                
                                # Process image
                                img_processed = remove_white_background(img)
                                
                                save_name = f"{base_name}_p{page_num+1}_{obj[1:]}.png"
                                save_path = os.path.join(output_dir, save_name)
                                img_processed.save(save_path, "PNG")
                                print(f"Saved: {save_name} ({img.format}, {img.size})")
                                count += 1
                            except Exception as e:
                                print(f"  Error extracting image {obj}: {e}")
                                # Try fallback extraction using PyPDF2 helper if available in this version
                                try:
                                    for image_file_object in page.images:
                                         # PyPDF2 >= 3.0.0
                                        image_name = image_file_object.name
                                        img = Image.open(io.BytesIO(image_file_object.data))
                                        img_processed = remove_white_background(img)
                                        save_name = f"{base_name}_p{page_num+1}_{image_name}.png"
                                        save_path = os.path.join(output_dir, save_name)
                                        img_processed.save(save_path, "PNG")
                                        print(f"Saved (via helper): {save_name}")
                                        count += 1
                                except:
                                    pass

    except Exception as e:
        print(f"Error processing file {base_name}: {e}")

print(f"Extraction complete. Total images: {count}")
