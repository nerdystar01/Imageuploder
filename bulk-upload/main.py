import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import json
from tqdm import tqdm
import base64
from io import BytesIO
from PIL import Image
from connect_db import get_session, end_session, get_latest_json_data, get_public_folder_by_user_id, merge_json_data, delete_and_upload_new_public_folder_file
from generate_json_tree import generate_json_tree, save_json
from create_new_resource import create_new_resource 
from png_info import PNGInfoAPI
from datetime import datetime
from importlib.metadata import distribution, PackageNotFoundError

def install_requirements():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def get_installed_packages():
    installed_packages = set()
    try:
        for dist in distribution().discover():
            installed_packages.add(dist.metadata['Name'].lower())
    except PackageNotFoundError:
        pass
    return installed_packages

try:
    with open('requirements.txt', 'r') as f:
        packages = f.readlines()
    installed_packages = get_installed_packages()
    missing_packages = [pkg.split('==')[0].strip() for pkg in packages if pkg.split('==')[0].strip().lower() not in installed_packages]

    if missing_packages:
        print("Installing missing packages:", missing_packages)
        install_requirements()
except Exception as e:
    print(f"An error occurred while installing requirements: {e}")

def print_timestamp(message):
    print(f"{message}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def decode_image_base64(encoded_string):
    try:
        # 헤더 "data:image/png;base64," 제거
        header, base64_data = encoded_string.split(',', 1)
        image_data = base64.b64decode(base64_data)
        buffer = BytesIO(image_data)
        img = Image.open(buffer)
        return img
    except Exception as e:
        print(f"이미지 디코딩 실패: {e}")
        return None

def process_image(target_dict, session):
    original = target_dict["original"]
    thumbnail = target_dict["thumbnail"]
    thumbnail_512 = target_dict["thumbnail_512"]

    if original.startswith("data:image/png;base64,"):
        original_image = decode_image_base64(original)
        thumbnail_image = decode_image_base64(thumbnail)
        thumbnail_512_image = decode_image_base64(thumbnail_512)

        png_info_api_instance = PNGInfoAPI()
        geninfo, params = png_info_api_instance.geninfo_params(image=original_image)

        image_path, thumbnail_path, thumbnail_image_512_path, resource_uuid = create_new_resource(
            session=session,
            user_id=61, 
            original_image=original_image, 
            thumbnail_image=thumbnail_image,
            thumbnail_image_512 = thumbnail_512_image,
            geninfo=geninfo,
            params=params
        )

        target_dict["original"] = f"https://storage.googleapis.com/wcidfu-bucket/_media/{image_path}"
        target_dict["thumbnail"] = f"https://storage.googleapis.com/wcidfu-bucket/_media/{thumbnail_path}"
        target_dict["thumbnail_512"] = f"https://storage.googleapis.com/wcidfu-bucket/_media/{thumbnail_image_512_path}"
        target_dict["uuid"] = resource_uuid

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python main.py <folder_path_to_upload>")
        sys.exit(1)

    bulk_folder_path = sys.argv[1]
    current_script_path = os.path.abspath(__file__)
    base_directory = os.path.dirname(current_script_path)
    generated_json_path = os.path.join(base_directory, 'generated-bulk-json-files')

    try:
        print_timestamp('[main.py 작동 시작]')
        print_timestamp('[지정한 벌크 디렉토리 .json 파일 화 시작]')
        json_tree = generate_json_tree(bulk_folder_path)
        save_json(json_tree, 'new_json_data')
        print_timestamp('[지정한 벌크 디렉토리 .json 파일 화 종료]')
        
        new_bulk_json = get_latest_json_data(generated_json_path)
        session, server = get_session()
        new_bulk_json_keys = list(new_bulk_json.keys())

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(process_image, target_dict, session): key for key in new_bulk_json_keys for target_dict in new_bulk_json[key]["imageUrls"]}
            with tqdm(total=len(futures), desc="Uploading images to GCS") as pbar:
                for future in as_completed(futures):
                    try:
                        future.result()  # If no exception, image processed successfully
                        pbar.update(1)  # Update the progress bar
                    except Exception as e:
                        print(f"An error occurred while processing an image: {e}")
                        pbar.update(1)  # Still update the progress bar even if there was an error
        print_timestamp('[GCS 이미지 업로드 종료]')

        print_timestamp('[GCS 공용 폴더 업로드 시작]')
        current_public_json_file, public_folder_id = get_public_folder_by_user_id(session, team_id=2)
        print_timestamp('[GCS 최신 공용 폴더 다운로드 완료]')
        updated_public_json_file = merge_json_data(new_data=new_bulk_json, existing_data=current_public_json_file)
        print_timestamp('[GCS 최신 공용 폴더 + 업로드 된 파일 내용 병합 완료]')
        load_updated_public_json = json.loads(updated_public_json_file)
        delete_and_upload_new_public_folder_file(session, public_folder_id, load_updated_public_json)
        print_timestamp('[GCS 최신 공용 폴더 업로드 완료]')
    finally:
        end_session(session)
        print_timestamp('[main.py 작동 종료]')