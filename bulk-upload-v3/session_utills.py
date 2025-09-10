#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import time
import io
from typing import Tuple, Any

# Third Party Libraries
from sshtunnel import SSHTunnelForwarder
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy import text
from google.cloud import storage
from google.oauth2 import service_account

# Local Imports
from models import setup_database_engine

def start_ssh_tunnel(max_retries=3, retry_delay=5):
    """
    SSH 터널을 설정합니다.
    
    Args:
        max_retries: 최대 재시도 횟수
        retry_delay: 재시도 간 대기 시간(초)
        
    Returns:
        SSHTunnelForwarder: 생성된 SSH 터널
    """
    for attempt in range(max_retries):
        try:
            server = SSHTunnelForwarder(
                ('34.64.105.81', 22),
                ssh_username='nerdystar',
                ssh_pkey='./wcidfu-ssh',
                remote_bind_address=('10.1.31.44', 5432),
                set_keepalive=60
            )
            server.start()
            logging.info("SSH tunnel established")
            return server
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(f"SSH tunnel attempt {attempt + 1} failed: {str(e)}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logging.error(f"Failed to establish SSH tunnel after {max_retries} attempts: {str(e)}")
                raise

def get_session() -> Tuple[Any, SSHTunnelForwarder]:
    """
    SSH 터널과 데이터베이스 세션을 생성합니다.
    
    Returns:
        Tuple[Any, SSHTunnelForwarder]: (세션 객체, SSH 터널)
    """
    retries = 3
    for attempt in range(retries):
        try:
            server = start_ssh_tunnel()
            engine = setup_database_engine("wcidfu", server.local_bind_port)
            session_factory = sessionmaker(bind=engine)
            session = scoped_session(session_factory)
            
            # 연결 테스트
            session().execute(text("SELECT 1"))
            
            return session, server
        except Exception as e:
            if attempt < retries - 1:
                logging.warning(f"Database connection attempt {attempt + 1} failed. Retrying...")
                time.sleep(5)
                if server:
                    stop_ssh_tunnel(server)
            else:
                logging.error(f"Failed to establish database connection after {retries} attempts")
                raise

def end_session(session, server):
    """
    세션과 SSH 터널을 종료합니다.
    
    Args:
        session: 데이터베이스 세션
        server: SSH 터널
    """
    try:
        # 먼저 데이터베이스 작업을 완료
        if session:
            try:
                session.close()
            except:
                pass
            
            try:
                session.remove()
            except:
                pass
        
        # SSH 터널 종료
        if server:
            stop_ssh_tunnel(server)
                
    except Exception as e:
        logging.warning(f"Session cleanup warning: {str(e)}")

def stop_ssh_tunnel(server):
    """
    SSH 터널을 종료합니다.
    
    Args:
        server: 종료할 SSH 터널
    """
    if server:
        try:
            server.stop()
            logging.info("SSH tunnel closed")
        except Exception as e:
            logging.warning(f"Error closing SSH tunnel: {str(e)}")

def check_connection(server):
    """
    SSH 연결 상태를 확인하고 필요시 재연결합니다.
    
    Args:
        server: 확인할 SSH 터널
        
    Returns:
        SSHTunnelForwarder: 활성 상태의 SSH 터널
    """
    if server is None or not server.is_active:
        logging.info("SSH connection is not active. Reconnecting...")
        return start_ssh_tunnel()
    return server

def upload_to_bucket(blob_name, data, bucket_name):
    """
    데이터를 Google Cloud Storage 버킷에 업로드합니다.
    
    Args:
        blob_name: 저장할 객체 이름
        data: 저장할 데이터
        bucket_name: 버킷 이름
        
    Returns:
        str: 정리된 객체 이름 (경로 프리픽스 제거됨)
    """
    current_script_path = os.path.abspath(__file__)
    base_directory = os.path.dirname(current_script_path)
    
    credentials_path = os.path.join(base_directory, 'wcidfu-77f802b00777.json')
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    credentials = service_account.Credentials.from_service_account_file(credentials_path)

    storage_client = storage.Client(credentials=credentials)
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data)
    clean_blob_name = blob_name.replace("_media/", "")    
    return clean_blob_name

def upload_image_to_gcp_bucket(blob_name, data, bucket_name):
    """
    이미지 데이터를 Google Cloud Storage 버킷에 업로드합니다.
    
    Args:
        blob_name: 저장할 객체 이름
        data: 저장할 이미지 데이터
        bucket_name: 버킷 이름
        
    Returns:
        str: 정리된 객체 이름 (경로 프리픽스 제거됨)
    """
    return upload_to_bucket(blob_name, data, bucket_name)