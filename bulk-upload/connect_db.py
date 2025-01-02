import os
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sshtunnel import SSHTunnelForwarder
from urllib.parse import quote_plus
import threading
import requests
from model import Base, PublicFolder
from google.cloud import storage
import uuid
import threading

engine = None
session_factory = None
server = None
lock = threading.Lock()

def start_ssh_tunnel():
    server = SSHTunnelForwarder(
        ('34.64.105.81', 22),
        ssh_username='nerdystar',
        ssh_private_key='./wcidfu-ssh',
        remote_bind_address=('10.1.31.44', 5432)
    )
    server.start()
    print("SSH tunnel established")
    return server

def setup_database_engine(password, port):
    db_user = "wcidfu"
    db_host = "127.0.0.1"
    db_name = "wcidfu"
    encoded_password = quote_plus(password)
    engine = create_engine(f'postgresql+psycopg2://{db_user}:{encoded_password}@{db_host}:{port}/{db_name}')
    Base.metadata.create_all(engine)
    return engine


def get_session():
    global engine, session_factory, server, lock
    with lock:
        if server is None:
            server = start_ssh_tunnel()
        if engine is None:
            engine = setup_database_engine("nerdy@2024", server.local_bind_port)
        if session_factory is None:
            session_factory = sessionmaker(bind=engine)
    session = scoped_session(session_factory)  # 수정된 부분: 세션 팩토리에서 직접 scoped_session 인스턴스 생성
    return session, server

def end_session(session):
    session.close()
    
def get_latest_json_data(directory):
    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.startswith('new_json_data') and f.endswith('.json')]
    
    if not files:
        return {}  # JSON 파일이 없는 경우 빈 사전 반환
    
    latest_file = max(files, key=os.path.getctime)
    
    with open(latest_file, 'r', encoding='utf-8') as file:
        data = json.load(file)  # 파일 내용을 JSON으로 읽고 파이썬 사전으로 변환
        return data

def get_public_folder_by_user_id(session, team_id):
    public_folder = session.query(PublicFolder).filter(PublicFolder.team_id == team_id).first()
    public_folder_id = public_folder.id
    
    if not public_folder or not public_folder.json_file:
        return {}  # public_folder 또는 JSON 파일이 없는 경우 빈 사전 반환

    file_path = public_folder.json_file
    google_url = f"https://storage.googleapis.com/wcidfu-bucket/_media/{file_path}"

    try:
        response = requests.get(google_url)
        response.raise_for_status()  # 요청 실패 시 예외를 발생시키기 위해

        local_filename = os.path.basename(file_path)
        current_script_path = os.path.abspath(__file__)
        base_directory = os.path.dirname(current_script_path)
    
        local_directory = os.path.join(base_directory, 'current-public-json-files')
        local_path = os.path.join(local_directory, local_filename)
        os.makedirs(local_directory, exist_ok=True)

        with open(local_path, 'wb') as f:
            f.write(response.content)
        
        with open(local_path, 'r' , encoding='utf-8') as f:
            public_json_data = json.load(f)  # 파일 내용을 JSON으로 읽고 사전으로 변환
        
        return public_json_data, public_folder_id
    except requests.RequestException as e:
        print(f"Failed to download or read the file: {e}")
        raise  # 요청 실패 시 빈 사전 반환
    
# from google.cloud import storage

BUCKET_NAME = 'wcidfu-bucket'
CREDENTIALS_JSON = './wcidfu-77f802b00777.json'

def merge_json_data(new_data, existing_data):
    from datetime import datetime
    # 'json' 키에 해당하는 사전을 찾아 new_data로 업데이트
    existing_data = dict(existing_data)
    if 'json' in existing_data:
        existing_data['json'].update(new_data)
    else:
        # 'json' 키가 없는 경우, 새로운 키와 사전을 추가
        existing_data['json'] = new_data

    current_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_directory = os.path.join(os.getcwd(), 'merege-json-files')
    os.makedirs(target_directory, exist_ok=True)
    full_file_path = os.path.join(target_directory, f'merege-folder-data-{current_time}.json')
    
    with open(full_file_path, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=4)

    return json.dumps(existing_data, ensure_ascii=False, indent=4)

def delete_and_upload_new_public_folder_file(session, public_folder_id, load_updated_public_json):
    try:
        current_script_path = os.path.abspath(__file__)
        base_directory = os.path.dirname(current_script_path)
        
        # Google Cloud 서비스 계정 자격 증명 파일 경로 설정
        credentials_path = os.path.join(base_directory, 'wcidfu-77f802b00777.json')
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        storage_client = storage.Client()

        public_folder = session.query(PublicFolder).filter(PublicFolder.id == public_folder_id).first()
        if not public_folder or not public_folder.json_file:
            raise KeyError("Public folder not found or no json file associated.")

        bucket_name = "wcidfu-bucket"
        file_path = public_folder.json_file
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(f"_media/{file_path}")

        backup_blob = bucket.blob(f"_media/backup/{file_path}")
        bucket.copy_blob(blob, bucket, new_name=backup_blob.name) 

        blob.delete()

        new_file_name = f"public_json_file/{uuid.uuid4()}.json"
        new_blob = bucket.blob(f"_media/{new_file_name}")
        updated_json_string = json.dumps(load_updated_public_json, ensure_ascii=False)
        new_blob.upload_from_string(updated_json_string, content_type='application/json')

        public_folder.json_file = new_file_name
        session.commit()

        # If all operations are successful, delete the backup
        backup_blob.delete()

    except Exception as e:
        session.rollback()
        print(f"An error occurred: {e}")
        # Attempt to restore the original file from the backup if it exists
        if backup_blob.exists():
            bucket.copy_blob(backup_blob, bucket, new_name=blob.name)
            print(f"Restored {file_path} from backup.")
        raise

    finally:
        session.close()