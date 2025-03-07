#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
DB 연결 및 유저리스트 조회 테스트

이 테스트는 다음 항목을 검증합니다:
1. DB 연결 정보가 올바르게 저장되는지
2. db_config.json 파일이 생성되는지
3. DB에서 유저 리스트를 가져올 수 있는지
4. 모델을 JSON 및 Python 파일로 내보낼 수 있는지
"""

import os
import logging
import tempfile
import json
import shutil
from typing import Dict, Any, List

# 로컬 모듈
from src.database.db_config_manager import DBConfigManager
from src.database.db_connection_manager import DBConnectionManager
# from src.database.table_inspector import TableInspector
# from src.database.model_exporter import ModelExporter

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 테스트 연결 정보 (이 값은 실제 환경에 맞게 변경해야 함)
from src.config import CREDENTIALS_DIR

# SSH 키 파일 경로
SSH_KEY_PATH = os.path.join(CREDENTIALS_DIR, 'wcidfu-ssh')

TEST_DB_CONNECTION = {
    'host': 'localhost',
    'port': 5432,
    'database': 'wcidfu',
    'user': 'wcidfu',
    'password': 'nerdy@2024',
    'use_ssh': True,
    'ssh_host': '34.64.105.81',
    'ssh_port': 22,
    'ssh_username': 'nerdystar',
    'ssh_key': SSH_KEY_PATH,
    'ssh_password': '',
    'ssh_remote_host': '10.1.31.44',
    'ssh_remote_port': 5432
}

def test_db_config_manager() -> bool:
    """
    DB 설정 관리자 테스트
    
    Returns:
        bool: 테스트 성공 여부
    """
    logger.info("===== DB 설정 관리자 테스트 시작 =====")
    
    try:
        # 임시 디렉토리에 설정 파일 생성하여 테스트
        with tempfile.TemporaryDirectory() as temp_dir:
            # 설정 관리자 초기화
            config_manager = DBConfigManager(temp_dir)
            
            # 연결 정보 추가
            conn_id = "test_connection"
            success = config_manager.add_connection(conn_id, TEST_DB_CONNECTION)
            
            if not success:
                logger.error("연결 정보 추가 실패")
                return False
            
            # 설정 파일 존재 확인
            config_file = os.path.join(temp_dir, "db_config.json")
            if not os.path.exists(config_file):
                logger.error(f"설정 파일이 생성되지 않았습니다: {config_file}")
                return False
            
            # 설정 파일 내용 확인
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if conn_id not in content:
                        logger.error(f"설정 파일에 연결 정보가 없습니다: {conn_id}")
                        return False
            except Exception as e:
                logger.error(f"설정 파일 읽기 실패: {str(e)}")
                return False
            
            # 연결 정보 가져오기
            connection_info = config_manager.get_connection(conn_id)
            if not connection_info:
                logger.error(f"연결 정보를 가져올 수 없습니다: {conn_id}")
                return False
            
            # 연결 정보 비교
            for key, value in TEST_DB_CONNECTION.items():
                if key in ["password", "ssh_key", "ssh_password"]:
                    # 암호화된 필드는 비교하지 않음
                    continue
                    
                if connection_info.get(key) != value:
                    logger.error(f"연결 정보 불일치: {key}")
                    return False
        
        logger.info("DB 설정 관리자 테스트 성공")
        return True
        
    except Exception as e:
        logger.error(f"DB 설정 관리자 테스트 실패: {str(e)}", exc_info=True)
        return False

def test_db_connection_manager() -> bool:
    """
    DB 연결 관리자 테스트
    
    Returns:
        bool: 테스트 성공 여부
    """
    logger.info("===== DB 연결 관리자 테스트 시작 =====")
    
    try:
        # 설정 관리자 초기화
        config_manager = DBConfigManager()
        
        # 연결 정보 추가
        conn_id = "test_connection"
        config_manager.add_connection(conn_id, TEST_DB_CONNECTION)
        
        # 연결 관리자 초기화
        connection_manager = DBConnectionManager(config_manager)
        
        # 연결 테스트
        success, message = connection_manager.test_connection(TEST_DB_CONNECTION)
        if not success:
            logger.error(f"연결 테스트 실패: {message}")
            return False
        
        # 실제 연결
        engine, session, server = connection_manager.connect(conn_id)
        if not all([engine, session, server]):
            logger.error("DB 연결 실패")
            return False
        
        # 테이블 목록 조회
        tables = connection_manager.list_tables(conn_id)
        if not tables:
            logger.error("테이블 목록 조회 실패")
            connection_manager.disconnect(conn_id)
            return False
        
        logger.info(f"테이블 목록: {tables}")
        
        # 연결 종료
        connection_manager.disconnect(conn_id)
        
        logger.info("DB 연결 관리자 테스트 성공")
        return True
        
    except Exception as e:
        logger.error(f"DB 연결 관리자 테스트 실패: {str(e)}", exc_info=True)
        return False

def test_get_user_list() -> bool:
    """
    유저 리스트 조회 테스트
    
    Returns:
        bool: 테스트 성공 여부
    """
    logger.info("===== 유저 리스트 조회 테스트 시작 =====")
    
    try:
        # 설정 관리자 초기화
        config_manager = DBConfigManager()
        
        # 연결 정보 추가
        conn_id = "test_connection"
        config_manager.add_connection(conn_id, TEST_DB_CONNECTION)
        
        # 연결 관리자 초기화
        connection_manager = DBConnectionManager(config_manager)
        
        # 테이블 검색기 초기화
        table_inspector = TableInspector(connection_manager)
        
        # DB 연결
        engine, session, server = connection_manager.connect(conn_id)
        if not all([engine, session, server]):
            logger.error("DB 연결 실패")
            return False
        
        try:
            # 유저 테이블 존재 확인
            tables = connection_manager.list_tables(conn_id)
            if 'user' not in tables:
                logger.error("user 테이블이 존재하지 않습니다.")
                return False
            
            # 유저 테이블 컬럼 조회
            columns = connection_manager.get_table_columns(conn_id, 'user')
            logger.info(f"User 테이블 컬럼: {[col['name'] for col in columns]}")
            
            # 유저 리스트 조회
            user_list = connection_manager.execute_query(conn_id, "SELECT id, email, nickname FROM \"user\" LIMIT 10")
            if user_list is None or len(user_list) == 0:
                logger.error("유저 리스트 조회 실패 또는 빈 리스트")
                return False
            
            logger.info(f"유저 목록 (최대 10개):")
            for user in user_list:
                logger.info(f"  ID: {user['id']}, 이메일: {user['email']}, 닉네임: {user.get('nickname', 'N/A')}")
            
            # 테이블 검색기를 사용한 모델 생성
            models = table_inspector.generate_models(conn_id)
            if not models:
                logger.error("모델 생성 실패")
                return False
            
            # User 모델 확인
            user_model = table_inspector.get_model_by_table_name('user')
            if not user_model:
                logger.error("User 모델을 찾을 수 없습니다.")
                return False
            
            logger.info(f"User 모델 생성 성공: {user_model.__name__}")
            
            return True
            
        finally:
            # 연결 종료
            connection_manager.disconnect(conn_id)
        
    except Exception as e:
        logger.error(f"유저 리스트 조회 테스트 실패: {str(e)}", exc_info=True)
        return False

def test_export_models() -> bool:
    """
    모델 내보내기 테스트
    
    Returns:
        bool: 테스트 성공 여부
    """
    logger.info("===== 모델 내보내기 테스트 시작 =====")
    
    # 내보내기 디렉토리
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    export_dir = os.path.join(base_dir, 'src', 'database', 'models')
    os.makedirs(export_dir, exist_ok=True)
    
    # 테스트를 위한 임시 디렉토리 생성
    temp_export_dir = os.path.join(export_dir, 'temp_test')
    os.makedirs(temp_export_dir, exist_ok=True)
    
    try:
        # 설정 관리자 초기화
        config_manager = DBConfigManager()
        
        # 연결 정보 추가
        conn_id = "test_connection"
        config_manager.add_connection(conn_id, TEST_DB_CONNECTION)
        
        # 연결 관리자 초기화
        connection_manager = DBConnectionManager(config_manager)
        
        # 테이블 검색기 초기화
        table_inspector = TableInspector(connection_manager)
        
        # 모델 내보내기 초기화
        model_exporter = ModelExporter(temp_export_dir)
        
        # DB 연결 및 모델 생성
        models = table_inspector.generate_models(conn_id)
        if not models:
            logger.error("모델 생성 실패")
            return False
        
        logger.info(f"생성된 모델 수: {len(models)}")
        
        # JSON으로 내보내기 테스트
        json_file_path = model_exporter.export_to_json(table_inspector, conn_id)
        if not json_file_path or not os.path.exists(json_file_path):
            logger.error("JSON 파일 내보내기 실패")
            return False
        
        logger.info(f"JSON 파일 내보내기 성공: {json_file_path}")
        
        # Python 모듈로 내보내기 테스트
        package_dir = model_exporter.export_to_python(table_inspector, conn_id)
        if not package_dir or not os.path.exists(package_dir):
            logger.error("Python 모듈 내보내기 실패")
            return False
        
        logger.info(f"Python 모듈 내보내기 성공: {package_dir}")
        
        # 생성된 모델 파일 확인
        init_file = os.path.join(package_dir, '__init__.py')
        if not os.path.exists(init_file):
            logger.error("__init__.py 파일이 생성되지 않았습니다.")
            return False
        
        # 특정 모델 파일 확인 (User 모델)
        user_model = table_inspector.get_model_by_table_name('user')
        if user_model:
            user_file = os.path.join(package_dir, f'{user_model.__name__.lower()}.py')
            if not os.path.exists(user_file):
                logger.error(f"User 모델 파일이 생성되지 않았습니다: {user_file}")
                return False
            
            logger.info(f"User 모델 파일 생성 확인: {user_file}")
            
            # 파일 내용 검증
            with open(user_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if "relationship(" not in content:
                    logger.error("User 모델 파일에 관계 정의가 없습니다.")
                    return False
                logger.info("User 모델 파일 내용 확인 성공")
        
        logger.info("모델 내보내기 테스트 성공")
        return True
        
    except Exception as e:
        logger.error(f"모델 내보내기 테스트 실패: {str(e)}", exc_info=True)
        return False
    finally:
        # 테스트 후 임시 디렉토리 정리
        try:
            if os.path.exists(temp_export_dir):
                import shutil
                shutil.rmtree(temp_export_dir)
                logger.info(f"테스트 임시 디렉토리 제거: {temp_export_dir}")
        except Exception as e:
            logger.warning(f"임시 디렉토리 정리 중 오류: {str(e)}")
            
        # 테스트용 설정 파일 정리
        try:
            config_dir = os.path.join(base_dir, 'src', 'database', 'data')
            test_config_file = os.path.join(config_dir, 'db_config.json')
            if os.path.exists(test_config_file):
                os.remove(test_config_file)
                logger.info(f"테스트 설정 파일 제거: {test_config_file}")
                
            keyfile = os.path.join(config_dir, '.keyfile')
            if os.path.exists(keyfile):
                os.remove(keyfile)
                logger.info(f"테스트 키 파일 제거: {keyfile}")
        except Exception as e:
            logger.warning(f"설정 파일 정리 중 오류: {str(e)}")

def run_test() -> bool:
    """
    모든 테스트 실행
    
    Returns:
        bool: 모든 테스트 성공 여부
    """
    # DB 설정 관리자 테스트
    if not test_db_config_manager():
        logger.error("DB 설정 관리자 테스트 실패")
        return False
    
    # DB 연결 관리자 테스트
    if not test_db_connection_manager():
        logger.error("DB 연결 관리자 테스트 실패")
        return False
    
    # 유저 리스트 조회 테스트
    if not test_get_user_list():
        logger.error("유저 리스트 조회 테스트 실패")
        return False
    
    # 모델 내보내기 테스트
    if not test_export_models():
        logger.error("모델 내보내기 테스트 실패")
        return False
    
    logger.info("모든 테스트 성공")
    return True

if __name__ == "__main__":
    # 직접 실행될 때 테스트 실행
    run_test()