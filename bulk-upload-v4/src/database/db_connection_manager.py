#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
데이터베이스 접속 관리자 모듈

이 모듈은 데이터베이스 연결 및 세션 관리를 담당합니다.
SSH 터널링을 지원하며, SQLAlchemy를 사용하여 데이터베이스에 접속합니다.
"""

import os
import logging
import time
from typing import Dict, Tuple, Any, Optional, List
from urllib.parse import quote_plus

# 서드파티 라이브러리
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from sshtunnel import SSHTunnelForwarder

# 로컬 모듈
from .db_config_manager import DBConfigManager

# 로깅 설정
logger = logging.getLogger(__name__)

class DBConnectionManager:
    """데이터베이스 접속 관리자 클래스"""
    
    def __init__(self, config_manager: DBConfigManager = None):
        """
        초기화 함수
        
        Args:
            config_manager: 데이터베이스 설정 관리자 (없으면 새로 생성)
        """
        self.config_manager = config_manager or DBConfigManager()
        self.active_connections = {}  # 활성 연결 저장 {conn_id: (engine, session, server)}
        self.base = declarative_base()  # SQLAlchemy Base 클래스
        
    def connect(self, conn_id: str) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
        """
        지정된 연결 정보로 데이터베이스에 연결
        
        Args:
            conn_id: 연결 ID
            
        Returns:
            Tuple[Optional[Any], Optional[Any], Optional[Any]]: (엔진, 세션, SSH 터널 서버)
        """
        # 이미 활성화된 연결이 있는지 확인
        if conn_id in self.active_connections:
            engine, session, server = self.active_connections[conn_id]
            
            # SSH 서버가 활성화되어 있는지 확인
            if server and not server.is_active:
                logger.info(f"SSH 연결이 비활성화되어 있습니다. 재연결 시도: {conn_id}")
                self.disconnect(conn_id)
            else:
                # 연결 테스트
                try:
                    session().execute(text("SELECT 1"))
                    logger.info(f"기존 연결 재사용: {conn_id}")
                    return engine, session, server
                except Exception as e:
                    logger.warning(f"기존 연결 테스트 실패: {str(e)}. 재연결 시도")
                    self.disconnect(conn_id)
        
        # 연결 정보 가져오기
        connection_info = self.config_manager.get_connection(conn_id)
        if not connection_info:
            logger.error(f"연결 정보를 찾을 수 없습니다: {conn_id}")
            return None, None, None
        
        # SSH 터널 사용 여부 확인
        if connection_info.get('use_ssh', False):
            return self._connect_via_ssh(conn_id, connection_info)
        else:
            return self._connect_direct(conn_id, connection_info)
    
    def _connect_via_ssh(self, conn_id: str, connection_info: Dict[str, Any]) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
        """
        SSH 터널을 통한 데이터베이스 연결
        
        Args:
            conn_id: 연결 ID
            connection_info: 연결 정보 딕셔너리
            
        Returns:
            Tuple[Optional[Any], Optional[Any], Optional[Any]]: (엔진, 세션, SSH 터널 서버)
        """
        server = None
        engine = None
        session = None
        
        try:
            # SSH 연결 정보
            ssh_host = connection_info.get('ssh_host')
            ssh_port = connection_info.get('ssh_port', 22)
            ssh_username = connection_info.get('ssh_username')
            ssh_password = connection_info.get('ssh_password')
            ssh_key = connection_info.get('ssh_key')
            remote_host = connection_info.get('ssh_remote_host', 'localhost')
            remote_port = connection_info.get('ssh_remote_port', 5432)
            
            # SSH 터널 생성
            ssh_args = {
                'ssh_username': ssh_username,
                'remote_bind_address': (remote_host, remote_port),
                'set_keepalive': 60
            }
            
            # SSH 키 또는 비밀번호 설정
            if ssh_key and os.path.exists(ssh_key):
                ssh_args['ssh_pkey'] = ssh_key
            elif ssh_password:
                ssh_args['ssh_password'] = ssh_password
            
            # SSH 터널 생성
            server = SSHTunnelForwarder(
                (ssh_host, ssh_port),
                **ssh_args
            )
            server.start()
            logger.info(f"SSH 터널 생성 성공: {ssh_host}:{ssh_port}")
            
            # 데이터베이스 연결
            db_host = 'localhost'
            db_port = server.local_bind_port
            db_name = connection_info.get('database')
            db_user = connection_info.get('user')
            db_password = connection_info.get('password')
            
            # 엔진 생성
            connection_string = self._get_connection_string(
                db_host, db_port, db_name, db_user, db_password
            )
            engine = create_engine(connection_string)
            
            # 세션 생성
            session_factory = sessionmaker(bind=engine)
            session = scoped_session(session_factory)
            
            # 연결 테스트
            session().execute(text("SELECT 1"))
            logger.info(f"SSH 터널을 통한 데이터베이스 연결 성공: {conn_id}")
            
            # 활성 연결 저장
            self.active_connections[conn_id] = (engine, session, server)
            
            return engine, session, server
            
        except Exception as e:
            logger.error(f"SSH 터널을 통한 연결 실패: {str(e)}")
            
            # 자원 정리
            if session:
                try:
                    session.close()
                except:
                    pass
            
            if server and server.is_active:
                try:
                    server.stop()
                except:
                    pass
                
            return None, None, None
    
    def _connect_direct(self, conn_id: str, connection_info: Dict[str, Any]) -> Tuple[Optional[Any], Optional[Any], None]:
        """
        직접 데이터베이스 연결 (SSH 없음)
        
        Args:
            conn_id: 연결 ID
            connection_info: 연결 정보 딕셔너리
            
        Returns:
            Tuple[Optional[Any], Optional[Any], None]: (엔진, 세션, None)
        """
        try:
            # 연결 정보
            db_host = connection_info.get('host')
            db_port = connection_info.get('port', 5432)
            db_name = connection_info.get('database')
            db_user = connection_info.get('user')
            db_password = connection_info.get('password')
            
            # 연결 문자열 생성
            connection_string = self._get_connection_string(
                db_host, db_port, db_name, db_user, db_password
            )
            
            # 엔진 생성
            engine = create_engine(connection_string)
            
            # 세션 생성
            session_factory = sessionmaker(bind=engine)
            session = scoped_session(session_factory)
            
            # 연결 테스트
            session().execute(text("SELECT 1"))
            logger.info(f"직접 데이터베이스 연결 성공: {conn_id}")
            
            # 활성 연결 저장
            self.active_connections[conn_id] = (engine, session, None)
            
            return engine, session, None
            
        except Exception as e:
            logger.error(f"직접 데이터베이스 연결 실패: {str(e)}")
            return None, None, None
    
    def _get_connection_string(self, host: str, port: int, database: str, user: str, password: str) -> str:
        """
        SQLAlchemy 연결 문자열 생성
        
        Args:
            host: 데이터베이스 호스트
            port: 데이터베이스 포트
            database: 데이터베이스 이름
            user: 사용자 이름
            password: 비밀번호
            
        Returns:
            str: 연결 문자열
        """
        encoded_password = quote_plus(password) if password else ""
        return f'postgresql+psycopg2://{user}:{encoded_password}@{host}:{port}/{database}'
    
    def disconnect(self, conn_id: str) -> bool:
        """
        데이터베이스 연결 종료
        
        Args:
            conn_id: 연결 ID
            
        Returns:
            bool: 성공 여부
        """
        if conn_id not in self.active_connections:
            logger.warning(f"종료할 연결이 없습니다: {conn_id}")
            return False
        
        engine, session, server = self.active_connections[conn_id]
        
        try:
            # 세션 종료
            if session:
                try:
                    session.close()
                except:
                    pass
                
                try:
                    session.remove()
                except:
                    pass
            
            # 엔진 연결 풀 정리
            if engine:
                try:
                    engine.dispose()
                except:
                    pass
            
            # SSH 터널 종료
            if server and server.is_active:
                try:
                    server.stop()
                    logger.info(f"SSH 터널 종료: {conn_id}")
                except Exception as e:
                    logger.warning(f"SSH 터널 종료 오류: {str(e)}")
            
            # 활성 연결 목록에서 제거
            del self.active_connections[conn_id]
            logger.info(f"연결 종료 성공: {conn_id}")
            
            return True
        except Exception as e:
            logger.error(f"연결 종료 오류: {str(e)}")
            return False
    
    def disconnect_all(self) -> None:
        """모든 활성 연결 종료"""
        connection_ids = list(self.active_connections.keys())
        for conn_id in connection_ids:
            self.disconnect(conn_id)
    
    def test_connection(self, connection_info: Dict[str, Any]) -> Tuple[bool, str]:
        """
        연결 정보를 테스트
        
        Args:
            connection_info: 연결 정보 딕셔너리
            
        Returns:
            Tuple[bool, str]: (성공 여부, 메시지)
        """
        server = None
        engine = None
        session = None
        
        try:
            # SSH 터널 사용 여부
            if connection_info.get('use_ssh', False):
                # SSH 연결 정보
                ssh_host = connection_info.get('ssh_host')
                ssh_port = connection_info.get('ssh_port', 22)
                ssh_username = connection_info.get('ssh_username')
                ssh_password = connection_info.get('ssh_password')
                ssh_key = connection_info.get('ssh_key')
                remote_host = connection_info.get('ssh_remote_host', 'localhost')
                remote_port = connection_info.get('ssh_remote_port', 5432)
                
                # SSH 터널 생성
                ssh_args = {
                    'ssh_username': ssh_username,
                    'remote_bind_address': (remote_host, remote_port),
                    'set_keepalive': 60
                }
                
                # SSH 키 또는 비밀번호 설정
                if ssh_key and os.path.exists(ssh_key):
                    ssh_args['ssh_pkey'] = ssh_key
                elif ssh_password:
                    ssh_args['ssh_password'] = ssh_password
                
                # SSH 터널 생성
                server = SSHTunnelForwarder(
                    (ssh_host, ssh_port),
                    **ssh_args
                )
                server.start()
                logger.info(f"SSH 터널 생성 성공: {ssh_host}:{ssh_port}")
                
                # 데이터베이스 연결
                db_host = 'localhost'
                db_port = server.local_bind_port
                db_name = connection_info.get('database')
                db_user = connection_info.get('user')
                db_password = connection_info.get('password')
                
            else:
                # 직접 연결 정보
                db_host = connection_info.get('host')
                db_port = connection_info.get('port', 5432)
                db_name = connection_info.get('database')
                db_user = connection_info.get('user')
                db_password = connection_info.get('password')
            
            # 연결 문자열 생성
            connection_string = self._get_connection_string(
                db_host, db_port, db_name, db_user, db_password
            )
            
            # 엔진 생성
            engine = create_engine(connection_string)
            
            # 세션 생성
            session_factory = sessionmaker(bind=engine)
            session = scoped_session(session_factory)
            
            # 연결 테스트
            session().execute(text("SELECT 1"))
            
            return True, "연결 테스트 성공"
            
        except Exception as e:
            logger.error(f"연결 테스트 실패: {str(e)}")
            return False, f"연결 테스트 실패: {str(e)}"
            
        finally:
            # 자원 정리
            if session:
                try:
                    session.close()
                except:
                    pass
            
            if engine:
                try:
                    engine.dispose()
                except:
                    pass
            
            if server and server.is_active:
                try:
                    server.stop()
                except:
                    pass
    
    def list_tables(self, conn_id: str) -> List[str]:
        """
        데이터베이스의 모든 테이블 목록 조회
        
        Args:
            conn_id: 연결 ID
            
        Returns:
            List[str]: 테이블 목록
        """
        engine, _, _ = self.connect(conn_id)
        if not engine:
            logger.error(f"데이터베이스 연결 실패: {conn_id}")
            return []
        
        try:
            inspector = inspect(engine)
            return inspector.get_table_names()
        except Exception as e:
            logger.error(f"테이블 목록 조회 실패: {str(e)}")
            return []
    
    def get_table_columns(self, conn_id: str, table_name: str) -> List[Dict[str, Any]]:
        """
        테이블 컬럼 정보 조회
        
        Args:
            conn_id: 연결 ID
            table_name: 테이블 이름
            
        Returns:
            List[Dict[str, Any]]: 컬럼 정보 목록
        """
        engine, _, _ = self.connect(conn_id)
        if not engine:
            logger.error(f"데이터베이스 연결 실패: {conn_id}")
            return []
        
        try:
            inspector = inspect(engine)
            return inspector.get_columns(table_name)
        except Exception as e:
            logger.error(f"테이블 컬럼 정보 조회 실패: {str(e)}")
            return []
    
    def get_table_primary_keys(self, conn_id: str, table_name: str) -> List[str]:
        """
        테이블 기본 키 조회
        
        Args:
            conn_id: 연결 ID
            table_name: 테이블 이름
            
        Returns:
            List[str]: 기본 키 목록
        """
        engine, _, _ = self.connect(conn_id)
        if not engine:
            logger.error(f"데이터베이스 연결 실패: {conn_id}")
            return []
        
        try:
            inspector = inspect(engine)
            pk_constraint = inspector.get_pk_constraint(table_name)
            return pk_constraint.get('constrained_columns', [])
        except Exception as e:
            logger.error(f"테이블 기본 키 조회 실패: {str(e)}")
            return []
    
    def get_table_foreign_keys(self, conn_id: str, table_name: str) -> List[Dict[str, Any]]:
        """
        테이블 외래 키 조회
        
        Args:
            conn_id: 연결 ID
            table_name: 테이블 이름
            
        Returns:
            List[Dict[str, Any]]: 외래 키 정보 목록
        """
        engine, _, _ = self.connect(conn_id)
        if not engine:
            logger.error(f"데이터베이스 연결 실패: {conn_id}")
            return []
        
        try:
            inspector = inspect(engine)
            return inspector.get_foreign_keys(table_name)
        except Exception as e:
            logger.error(f"테이블 외래 키 조회 실패: {str(e)}")
            return []
    
    def execute_query(self, conn_id: str, query: str, params: Dict[str, Any] = None) -> Optional[List[Dict[str, Any]]]:
        """
        SQL 쿼리 실행 및 결과 반환
        
        Args:
            conn_id: 연결 ID
            query: SQL 쿼리 문자열
            params: 쿼리 파라미터 (선택)
            
        Returns:
            Optional[List[Dict[str, Any]]]: 쿼리 결과 또는 None
        """
        _, session, _ = self.connect(conn_id)
        if not session:
            logger.error(f"데이터베이스 연결 실패: {conn_id}")
            return None
        
        try:
            if params:
                result = session().execute(text(query), params)
            else:
                result = session().execute(text(query))
                
            # 결과를 딕셔너리 목록으로 변환
            column_names = result.keys()
            result_dicts = [dict(zip(column_names, row)) for row in result]
            
            return result_dicts
        except Exception as e:
            logger.error(f"쿼리 실행 실패: {str(e)}")
            return None
    
    def get_table_schema_info(self, conn_id: str, table_name: str) -> Dict[str, Any]:
        """
        테이블 스키마 정보 종합 조회
        
        Args:
            conn_id: 연결 ID
            table_name: 테이블 이름
            
        Returns:
            Dict[str, Any]: 테이블 스키마 정보
        """
        schema_info = {
            'table_name': table_name,
            'columns': self.get_table_columns(conn_id, table_name),
            'primary_keys': self.get_table_primary_keys(conn_id, table_name),
            'foreign_keys': self.get_table_foreign_keys(conn_id, table_name)
        }
        
        return schema_info
    
    def get_database_schema(self, conn_id: str) -> Dict[str, Dict[str, Any]]:
        """
        데이터베이스 전체 스키마 정보 조회
        
        Args:
            conn_id: 연결 ID
            
        Returns:
            Dict[str, Dict[str, Any]]: 데이터베이스 스키마 정보
        """
        tables = self.list_tables(conn_id)
        schema_info = {}
        
        for table in tables:
            schema_info[table] = self.get_table_schema_info(conn_id, table)
            
        return schema_info