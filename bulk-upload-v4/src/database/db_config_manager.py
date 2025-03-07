#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
데이터베이스 설정 관리자 모듈

이 모듈은 데이터베이스 연결 정보를 저장하고 관리하는 기능을 제공합니다.
연결 정보는 JSON 파일에 암호화되어 저장됩니다.
"""

import os
import json
import base64
import logging
from typing import Dict, Optional, List, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 로깅 설정
logger = logging.getLogger(__name__)

class DBConfigManager:
    """데이터베이스 설정 관리자 클래스"""
    
    def __init__(self, config_dir: str = None, config_file: str = 'db_config.json'):
        """
        초기화 함수
        
        Args:
            config_dir: 설정 파일 디렉토리 경로 (기본값: src/database/data)
            config_file: 설정 파일 이름 (기본값: db_config.json)
        """
        # 실행 파일의 디렉토리 경로 파악
        if config_dir is None:
            # 기본 경로: 현재 모듈이 있는 디렉토리의 data 폴더
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.config_dir = os.path.join(base_dir, 'data')
        else:
            self.config_dir = config_dir
            
        # 설정 파일 경로
        self.config_file = os.path.join(self.config_dir, config_file)
        
        # 디렉토리가 없으면 생성
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 암호화 키 (실제 애플리케이션에서는 더 안전한 방법으로 키 관리 필요)
        self._key = self._get_encryption_key()
        
        # 연결 정보를 저장할 딕셔너리
        self.connections = {}
        
        # 설정 파일이 있으면 로드
        self.load_config()
        
    def _get_encryption_key(self) -> bytes:
        key_file = os.path.join(self.config_dir, '.keyfile')
        
        # 키 파일 생성 로직에 더 자세한 로깅 추가
        try:
            # 기존 키 파일 로드 시도
            if os.path.exists(key_file):
                logger.info(f"키 파일 경로: {key_file}")
                logger.info(f"키 파일 크기: {os.path.getsize(key_file)} 바이트")
                
                with open(key_file, 'rb') as f:
                    key = f.read()
                    logger.info(f"키 파일 로드 성공, 키 길이: {len(key)} 바이트")
                    return key
            
            # 새 키 생성 로직에 더 자세한 로깅 추가
            logger.info("새 키 생성 시작")
            salt = b'static_salt_for_app'
            password = b'app_encryption_password'
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                salt=salt,
                iterations=100000,
                length=32
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
            
            logger.info(f"새 키 생성 완료, 길이: {len(key)} 바이트")
            
            # 키 파일 저장
            with open(key_file, 'wb') as f:
                f.write(key)
            logger.info(f"키 파일 저장 완료: {key_file}")
            
            return key
        
        except Exception as e:
            logger.error(f"키 생성/로드 중 심각한 오류 발생: {str(e)}")
            raise  # 예외를 다시 발생시켜 상위 호출자에게 전달
    
    def _encrypt(self, data: str) -> str:
        """
        문자열 암호화
        
        Args:
            data: 암호화할 문자열
            
        Returns:
            str: 암호화된 문자열 (base64 인코딩)
        """
        try:
            fernet = Fernet(self._key)
            return fernet.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"암호화 실패: {str(e)}")
            return data  # 암호화 실패 시 원본 반환 (보안상 좋지 않음)
    
    def _decrypt(self, encrypted_data: str) -> str:
        """
        문자열 복호화
        
        Args:
            encrypted_data: 복호화할 문자열 (base64 인코딩)
            
        Returns:
            str: 복호화된 문자열
        """
        try:
            logger.info(f"복호화 시도: {encrypted_data}")
            logger.info(f"키 길이: {len(self._key)} 바이트")
            
            fernet = Fernet(self._key)
            decrypted = fernet.decrypt(encrypted_data.encode()).decode()
            
            logger.info(f"복호화 성공: {decrypted}")
            return decrypted
        except Exception as e:
            logger.error(f"복호화 실패 상세 정보: {str(e)}")
            logger.error(f"암호화된 데이터: {encrypted_data}")
            logger.error(f"사용된 키: {self._key}")
            raise
    
    def load_config(self) -> bool:
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                encrypted_data = json.load(f)
            
            self.connections = {}
            for conn_id, conn_data in encrypted_data.items():
                decrypted_conn = {}
                for key, value in conn_data.items():
                    if key in ['password', 'ssh_key', 'ssh_password']:
                        # 값이 비어있지 않은 경우에만 복호화 시도
                        if value:
                            try:
                                decrypted_conn[key] = self._decrypt(value)
                            except Exception as e:
                                logger.warning(f"{key} 복호화 실패: {str(e)}")
                                decrypted_conn[key] = value
                        else:
                            decrypted_conn[key] = value
                    else:
                        decrypted_conn[key] = value
                
                self.connections[conn_id] = decrypted_conn
            
            logger.info(f"설정 파일 로드 성공: {len(self.connections)} 개의 연결 정보")
            return True
        except Exception as e:
            logger.error(f"설정 파일 로드 실패: {str(e)}")
            return False
    
    def save_config(self) -> bool:
        """
        연결 정보를 설정 파일에 저장
        
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # 데이터 암호화
            encrypted_data = {}
            for conn_id, conn_data in self.connections.items():
                encrypted_conn = {}
                for key, value in conn_data.items():
                    if key in ['password', 'ssh_key', 'ssh_password'] and value:
                        encrypted_conn[key] = self._encrypt(value)
                    else:
                        encrypted_conn[key] = value
                encrypted_data[conn_id] = encrypted_conn
            
            # 파일 저장
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(encrypted_data, f, indent=2)
                
            logger.info(f"설정 파일 저장 성공: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"설정 파일 저장 실패: {str(e)}")
            return False
    
    def add_connection(self, conn_id: str, conn_data: Dict[str, Any]) -> bool:
        """
        새 연결 정보 추가
        
        Args:
            conn_id: 연결 ID (고유 식별자)
            conn_data: 연결 정보 딕셔너리
            
        Returns:
            bool: 추가 성공 여부
        """
        if conn_id in self.connections:
            logger.warning(f"이미 존재하는 연결 ID입니다: {conn_id}")
            return False
        
        self.connections[conn_id] = conn_data
        return self.save_config()
    
    def update_connection(self, conn_id: str, conn_data: Dict[str, Any]) -> bool:
        """
        기존 연결 정보 업데이트
        
        Args:
            conn_id: 연결 ID (고유 식별자)
            conn_data: 새 연결 정보 딕셔너리
            
        Returns:
            bool: 업데이트 성공 여부
        """
        if conn_id not in self.connections:
            logger.warning(f"존재하지 않는 연결 ID입니다: {conn_id}")
            return False
        
        self.connections[conn_id] = conn_data
        return self.save_config()
    
    def delete_connection(self, conn_id: str) -> bool:
        """
        연결 정보 삭제
        
        Args:
            conn_id: 삭제할 연결 ID
            
        Returns:
            bool: 삭제 성공 여부
        """
        if conn_id not in self.connections:
            logger.warning(f"존재하지 않는 연결 ID입니다: {conn_id}")
            return False
        
        del self.connections[conn_id]
        return self.save_config()
    
    def get_connection(self, conn_id: str) -> Optional[Dict[str, Any]]:
        """
        특정 연결 정보 조회
        
        Args:
            conn_id: 조회할 연결 ID
            
        Returns:
            Optional[Dict[str, Any]]: 연결 정보 딕셔너리 또는 None
        """
        return self.connections.get(conn_id)
    
    def get_all_connections(self) -> Dict[str, Dict[str, Any]]:
        """
        모든 연결 정보 조회
        
        Returns:
            Dict[str, Dict[str, Any]]: 모든 연결 정보 딕셔너리
        """
        return self.connections
    
    def get_connection_names(self) -> List[str]:
        """
        등록된 모든 연결 이름 목록 조회
        
        Returns:
            List[str]: 연결 ID 목록
        """
        return list(self.connections.keys())
    
    def connection_exists(self, conn_id: str) -> bool:
        """
        특정 이름의 연결이 존재하는지 확인
        
        Args:
            conn_id: 확인할 연결 ID
            
        Returns:
            bool: 존재 여부
        """
        return conn_id in self.connections