# import os
# import json
# import uuid
# from PIL import Image, PngImagePlugin, UnidentifiedImageError
# import base64
# import io
# from datetime import datetime
# from tqdm import tqdm

# def generate_json_tree(root_path):
#     tree = {}
#     valid_extensions = {'png', 'jpg', 'gif', 'bmp', 'tiff', 'psd', 'psb', 'webp', 'ico', 'anigif', 'jpeg'}

#     def add_folder(path, name, parent_id=None):
#         folder_id = name
#         tree[folder_id] = {
#             "id": folder_id,
#             "name": name,
#             "children": [],
#             "parentId": parent_id,
#             "parentIdList": [],
#             "imageUrls": []
#         }
#         if parent_id:
#             tree[folder_id]["parentIdList"] = tree[parent_id]["parentIdList"] + [parent_id]
#         return folder_id

#     def create_thumbnail(image_path):
#         try:
#             with Image.open(image_path) as img:
#                 maxHeight = 128
#                 ratio = maxHeight / img.height
#                 new_width = int(img.width * ratio)
#                 new_height = maxHeight

#                 img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
#                 buffer = io.BytesIO()
#                 img.save(buffer, format='PNG')
#                 encoded_string = base64.b64encode(buffer.getvalue()).decode('utf-8')
#                 return "data:image/png;base64," + encoded_string
#         except Exception as e:
#             print(f"Failed to create thumbnail for {image_path}: {e}")
#             return None

#     def encode_image_base64_with_exif(image_path):
#         try:
#             with Image.open(image_path) as img:
#                 info = img.info.copy()
#                 buffer = io.BytesIO()
#                 pnginfo = PngImagePlugin.PngInfo()
                
#                 for key, value in info.items():
#                     if isinstance(value, bytes):
#                         value = value.decode('utf-8', errors='ignore')
#                         pnginfo.add_text(key, value)
#                     elif isinstance(value, tuple) or isinstance(value, int):
#                         pass
                
#                 img.save(buffer, format='PNG', pnginfo=pnginfo)
#                 encoded_string = base64.b64encode(buffer.getvalue()).decode('utf-8')
#                 return f"data:image/png;base64,{encoded_string}"
#         except Exception as e:
#             print(f"Failed to encode image {image_path}: {e}")
#             return None

#     # Directory traversal and JSON structure creation
#     for dirpath, dirnames, filenames in os.walk(root_path):
#         if dirpath == root_path:
#             folder_id = add_folder(dirpath, os.path.basename(root_path))
#         else:
#             parent_id = os.path.basename(os.path.dirname(dirpath))
#             folder_id = add_folder(dirpath, os.path.basename(dirpath), parent_id)
        
#         if 'parentId' in tree[folder_id] and tree[folder_id]['parentId']:
#             tree[tree[folder_id]['parentId']]['children'].append(folder_id)
        
#         # tqdm for file processing progress
#         for filename in tqdm(filenames, desc=f"[Processing files in {dirpath}", unit="file"):
#             ext = filename.split('.')[-1].lower()
#             if ext in valid_extensions:
#                 image_path = os.path.join(dirpath, filename)
#                 original = encode_image_base64_with_exif(image_path)
#                 thumbnail = create_thumbnail(image_path)
#                 if original and thumbnail:
#                     image_data = {
#                         "original": original,
#                         "thumbnail": thumbnail,
#                         "uuid": str(uuid.uuid4())
#                     }
#                     tree[folder_id]["imageUrls"].append(image_data)
    
#     return tree


# def save_json(data, filename):
#     current_time = datetime.now().strftime("%Y%m%d-%H%M%S")
#     target_directory = os.path.join(os.getcwd(), 'generated-bulk-json-files')
#     os.makedirs(target_directory, exist_ok=True)
#     full_file_path = os.path.join(target_directory, f'{filename}-{current_time}.json')
#     with open(full_file_path, 'w', encoding='utf-8') as f:
#         json.dump(data, f, ensure_ascii=False, indent=4)
import os
import json
import uuid
from PIL import Image, PngImagePlugin
import base64
import io
from datetime import datetime
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

def create_thumbnail_128(image_path):
    try:
        with Image.open(image_path) as img:
            maxHeight = 128
            ratio = maxHeight / img.height
            new_width = int(img.width * ratio)
            new_height = maxHeight

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            encoded_string = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return "data:image/png;base64," + encoded_string
    except Exception as e:
        print(f"Failed to create thumbnail for {image_path}: {e}")
        return None
    
def create_thumbnail_512(image_path):
    try:
        with Image.open(image_path) as img:
            maxHeight = 512
            ratio = maxHeight / img.height
            new_width = int(img.width * ratio)
            new_height = maxHeight

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            encoded_string = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return "data:image/png;base64," + encoded_string
    except Exception as e:
        print(f"Failed to create thumbnail for {image_path}: {e}")
        return None

# def encode_image_base64_with_exif(image_path):
#     try:
#         with Image.open(image_path) as img:
#             info = img.info.copy()
#             buffer = io.BytesIO()
#             pnginfo = PngImagePlugin.PngInfo()
            
#             for key, value in info.items():
#                 if isinstance(value, bytes):
#                     value = value.decode('utf-8', errors='ignore')
#                     pnginfo.add_text(key, value)
#                 elif isinstance(value, tuple) or isinstance(value, int):
#                     pass
            
#             img.save(buffer, format='PNG', pnginfo=pnginfo)
#             encoded_string = base64.b64encode(buffer.getvalue()).decode('utf-8')
#             return f"data:image/png;base64,{encoded_string}"
#     except Exception as e:
#         print(f"Failed to encode image {image_path}: {e}")
#         return None

# 0531
def encode_image_base64_with_metadata(image_path):
    try:
        with Image.open(image_path) as img:
            metadata = img.info
            buffer = io.BytesIO()
            
            # 메타데이터를 보존하기 위해 PngInfo 객체 생성
            pnginfo = PngImagePlugin.PngInfo()
            for key, value in metadata.items():
                pnginfo.add_text(key, value)
            
            img.save(buffer, format='PNG', pnginfo=pnginfo)
            encoded_string = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"data:image/png;base64,{encoded_string}"
    except Exception as e:
        print(f"이미지 인코딩 실패: {image_path}: {e}")
        return None
    
def process_image(image_path):
    original = encode_image_base64_with_metadata(image_path)
    # original = encode_image_base64_with_exif(image_path)
    thumbnail_128 = create_thumbnail_128(image_path)
    thumbnail_512 = create_thumbnail_512(image_path)
    if original and thumbnail_128:
        return {
            "original": original,
            "thumbnail": thumbnail_128,
            "thumbnail_512": thumbnail_512, 
            "uuid": str(uuid.uuid4())
        }
    return None

def generate_json_tree(root_path):
    tree = {}
    valid_extensions = {'png', 'jpg', 'gif', 'bmp', 'tiff', 'psd', 'psb', 'webp', 'ico', 'anigif', 'jpeg'}

    def add_folder(path, name, parent_id=None):
        folder_id = name
        tree[folder_id] = {
            "id": folder_id,
            "name": name,
            "children": [],
            "parentId": parent_id,
            "parentIdList": [],
            "imageUrls": []
        }
        if parent_id:
            tree[folder_id]["parentIdList"] = tree[parent_id]["parentIdList"] + [parent_id]
        return folder_id

    # Directory traversal and JSON structure creation
    for dirpath, dirnames, filenames in os.walk(root_path):
        if dirpath == root_path:
            folder_id = add_folder(dirpath, os.path.basename(root_path))
        else:
            parent_id = os.path.basename(os.path.dirname(dirpath))
            folder_id = add_folder(dirpath, os.path.basename(dirpath), parent_id)
        
        if 'parentId' in tree[folder_id] and tree[folder_id]['parentId']:
            tree[tree[folder_id]['parentId']]['children'].append(folder_id)

        image_paths = [
            os.path.join(dirpath, filename)
            for filename in filenames
            if filename.split('.')[-1].lower() in valid_extensions
        ]

        with ProcessPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(process_image, image_path): image_path for image_path in image_paths}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"[Processing files in {dirpath}", unit="file"):
                image_data = future.result()
                if image_data:
                    tree[folder_id]["imageUrls"].append(image_data)
    
    return tree

def save_json(data, filename):
    current_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_directory = os.path.join(os.getcwd(), 'generated-bulk-json-files')
    os.makedirs(target_directory, exist_ok=True)
    full_file_path = os.path.join(target_directory, f'{filename}-{current_time}.json')
    with open(full_file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
