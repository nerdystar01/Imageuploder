import subprocess
import sys
import pkg_resources

def install_requirements():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

try:
    with open('requirements.txt', 'r') as f:
        packages = f.readlines()
    installed_packages = {pkg.key for pkg in pkg_resources.working_set}
    missing_packages = [pkg.split('==')[0].strip() for pkg in packages if pkg.split('==')[0].strip() not in installed_packages]

    if missing_packages:
        print("Installing missing packages:", missing_packages)
        install_requirements()
except Exception as e:
    print(f"An error occurred while installing requirements: {e}")

import os
import json
from tqdm import tqdm
import base64
from io import BytesIO
from PIL import Image
from connect_db import start_session, end_session, get_latest_json_data, get_public_folder_by_user_id, merge_json_data, delete_and_upload_new_public_folder_file
from generate_json_tree import generate_json_tree, save_json
from create_new_resource import create_new_resource 
from png_info import PNGInfoAPI
from datetime import datetime

bulk_folder_path = '/Users/nerdystar/Desktop/LOL/champ'

current_script_path = os.path.abspath(__file__)
base_directory = os.path.dirname(current_script_path)  
generated_json_path = os.path.join(base_directory, 'generated-bulk-json-files')

def print_timestamp(message):
    print(f"{message}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    print_timestamp('[GCS 이미지 업로드 시작]')
    load_updated_public_json = json.loads(updated_public_json_file)
    updated_public_json = load_updated_public_json['json']
    updated_public_json_keys = list(updated_public_json.keys())

    for key in updated_public_json_keys:
        image_urls_dict = updated_public_json[key]["imageUrls"]
        for target_dict in tqdm(image_urls_dict, desc=f"[Folder Name '{key}' Uploading images to GCS]", unit="image"):
            original = target_dict["original"]
            thumbnail = target_dict["thumbnail"]

            if original.startswith("data:image/png;base64,"):
                original_base64_data = original.replace("data:image/png;base64,", "")
                thumbnail_base64_data = thumbnail.replace("data:image/png;base64,", "")
                
                original_base64_decode = base64.b64decode(original_base64_data)
                thumbnail_base64_decode = base64.b64decode(thumbnail_base64_data)
                
                original_image = Image.open(BytesIO(original_base64_decode))
                thumbnail_image = Image.open(BytesIO(thumbnail_base64_decode))

                png_info_api_instance = PNGInfoAPI()
                geninfo, params = png_info_api_instance.geninfo_params(image= original_image)
                
                image_path, thumbnail_path, resource_uuid = create_new_resource(
                    session= session,
                    user_id= 1, 
                    original_image= original_image, 
                    thumbnail_image= thumbnail_image,
                    geninfo = geninfo,
                    params = params
                )

                target_dict["original"] = f"https://storage.googleapis.com/wcidfu-bucket/_media/{image_path}"
                target_dict["thumbnail"] = f"https://storage.googleapis.com/wcidfu-bucket/_media/{thumbnail_path}"
                target_dict["uuid"] = resource_uuid
    
    print_timestamp('[GCS 이미지 업로드 종료]')
    delete_and_upload_new_public_folder_file(session, public_folder_id, load_updated_public_json)
    
finally:
    end_session(session, server)
    print_timestamp('[main.py 작동 종료]')