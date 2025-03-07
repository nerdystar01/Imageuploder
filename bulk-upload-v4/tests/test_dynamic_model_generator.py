#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
다이나믹 모델 제너레이터 테스트 스크립트

이 스크립트는 기존 DB 연결을 사용하여 다이나믹 모델 제너레이터를 테스트합니다.
지정된 테이블만 정확히 모델링합니다.
"""

import os
import sys
import logging
import importlib.util
from typing import Dict, Any, List, Optional

# 현재 디렉토리를 모듈 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# 로컬 모듈
from src.database.db_config_manager import DBConfigManager
from src.database.db_connection_manager import DBConnectionManager
from src.database.dynamic_model_generator import DynamicModelGenerator

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 연결 ID (기존에 설정된 연결 ID를 사용)
CONN_ID = 'test_connection'

def test_dynamic_model_generator():
    """다이나믹 모델 제너레이터 테스트"""
    logger.info("다이나믹 모델 제너레이터 테스트 실행")
    
    try:
        # DBConnectionManager 생성
        connection_manager = DBConnectionManager()
        
        # 연결 정보 확인
        config_manager = DBConfigManager()
        connection_info = config_manager.get_connection(CONN_ID)
        
        if not connection_info:
            logger.error(f"연결 정보가 없습니다: {CONN_ID}")
            logger.info("사용 가능한 연결:")
            for conn_id in config_manager.get_connection_names():
                logger.info(f" - {conn_id}")
            return False
        
        logger.info(f"연결 정보 확인: {CONN_ID}")
        logger.info(f" - 호스트: {connection_info.get('host') or connection_info.get('ssh_remote_host')}")
        logger.info(f" - 데이터베이스: {connection_info.get('database')}")
        
        # 데이터베이스 연결 (connect 메서드 사용)
        engine, session, server = connection_manager.connect(CONN_ID)
        
        if not engine:
            logger.error("데이터베이스 연결 실패")
            return False
        
        # 임시 출력 파일 경로 생성
        temp_dir = os.path.join(parent_dir, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(temp_dir, 'generated_models.py')
        
        # 다이나믹 모델 제너레이터 생성 및 실행
        # 지정된 테이블들만 모델링
        required_tables = [
            'user', 'resource', 'color_code_tags', 'resource_tag_v2',
            'sd_model', 'team',
            'resource_likes', 'resource_tags', 'resource_hidden_users',
            'resource_tabbed_users', 'resource_placeholder', 'resource_view_status'
        ]
        
        generator = DynamicModelGenerator(
            conn_id=CONN_ID, 
            output_path=output_path,
            include_tables=required_tables
        )
        
        success = generator.generate_models()
        
        # 성공 여부 확인
        if not success:
            logger.error("모델 생성 실패")
            return False
        
        if not os.path.exists(output_path):
            logger.error("모델 파일이 생성되지 않음")
            return False
        
        # 모델 파일 내용 확인
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 필수 모델 클래스가 있는지 확인
        required_models = ['User', 'Resource', 'ColorCodeTags', 'ResourceTagV2', 'SdModel', 'Team']
        missing_models = []
        
        for model in required_models:
            if f'class {model}(Base)' not in content:
                missing_models.append(model)
        
        if missing_models:
            logger.error(f"누락된 모델: {', '.join(missing_models)}")
            return False
        
        logger.info("필수 모델 클래스 확인 완료")
        logger.info(f"모델 파일 생성 완료: {output_path}")
        
        # 생성된 모델 모듈 로드 시도
        try:
            spec = importlib.util.spec_from_file_location("generated_models", output_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 모델 클래스 확인
            for model in required_models:
                if not hasattr(module, model):
                    logger.error(f"모델 클래스 로드 실패: {model}")
                    return False
            
            logger.info("모델 클래스 로드 성공")
            
            # 테스트 완료
            return True
                
        except Exception as e:
            logger.error(f"모델 로드 중 오류: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
            
    except Exception as e:
        logger.error(f"테스트 중 오류 발생: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == '__main__':
    if test_dynamic_model_generator():
        logger.info("테스트 성공")
        sys.exit(0)
    else:
        logger.error("테스트 실패")
        sys.exit(1)