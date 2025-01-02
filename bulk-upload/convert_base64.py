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
from connect_db import start_session, end_session, get_latest_json_data, get_public_folder_by_user_id, merge_json_data
from generate_json_tree import generate_json_tree, save_json


from datetime import datetime

bulk_folder_path = '/Users/nerdystar/Desktop/LOL/champ'

current_script_path = os.path.abspath(__file__)
base_directory = os.path.dirname(current_script_path)  
generated_json_path = os.path.join(base_directory, 'generated-bulk-json-files')

def print_timestamp(message):
    print(f"{message}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

try:
    print_timestamp('[main.py 작동 시작]')
    # ssh 시작 및 DB 연결.
    session, server = start_session()
    # 벌크 이미지 루트 디렉토리 설정 및 업데이트를 위한 벌크 json data 생성.
    print_timestamp('[지정한 벌크 디렉토리 .json 파일 화 시작]')
    json_tree = generate_json_tree(bulk_folder_path)
    save_json(json_tree, 'new_json_data')
    print_timestamp('[지정한 벌크 디렉토리 .json 파일 화 종료]')
    # 최신 벌크 .json 가져오기
    new_bulk_json = get_latest_json_data(generated_json_path)
    # 현재 공용 폴더 json file 가져오기
    current_public_json_file, public_folder_id = get_public_folder_by_user_id(session, user_id = 1)
    # 최신 벌크 json data 공용폴더 json에 'json' 에 적용시키기
    updated_public_json_file = merge_json_data(new_data= new_bulk_json, existing_data= current_public_json_file)
    # DB에 최신 공용 폴더 json file 적용하기.

finally:
    end_session(session, server)
    print_timestamp('[main.py 작동 종료]')