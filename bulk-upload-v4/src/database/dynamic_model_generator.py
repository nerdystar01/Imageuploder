#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
다이나믹 모델 제너레이터 모듈

이 모듈은 데이터베이스 스키마를 자동으로 분석하여 SQLAlchemy 모델 클래스를 동적으로 생성합니다.
연관 테이블과 관계를 자동으로 감지합니다.
"""

import os
import sys
import inspect
import importlib
import logging
import datetime
import pytz
from typing import Dict, List, Set, Any, Optional, Tuple
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, Table
from sqlalchemy import MetaData, inspect, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.ext.automap import automap_base

# 로컬 모듈
from .db_connection_manager import DBConnectionManager
from .db_config_manager import DBConfigManager

# 로깅 설정
logger = logging.getLogger(__name__)

# 서울 timezone 설정
seoul_tz = pytz.timezone('Asia/Seoul')
Base = declarative_base()

class DynamicModelGenerator:
    """동적 SQLAlchemy 모델 생성기 클래스"""
    
    def __init__(self, conn_id, output_path, include_tables=None, exclude_tables=None):
        """
        다이나믹 모델 제너레이터 초기화
        
        Args:
            conn_id: 데이터베이스 연결 ID
            output_path: 생성된 모델 파일 경로
            include_tables: 포함할 테이블 목록 (None이면 모든 테이블)
            exclude_tables: 제외할 테이블 목록
        """
        # DBConfigManager와 DBConnectionManager 초기화
        self.config_manager = DBConfigManager()
        self.connection_manager = DBConnectionManager()
        
        self.conn_id = conn_id
        self.output_path = output_path
        
        # include_tables가 제공되면 사용, 아니면 모든 테이블
        self.include_tables = include_tables or []
        self.exclude_tables = exclude_tables or []
        
        # Django 관련 테이블 자동 제외
        if not self.include_tables:
            self.exclude_tables.extend([
                'django_migrations', 'django_content_type', 'django_admin_log',
                'django_session', 'social_auth_association', 'social_auth_code',
                'social_auth_nonce', 'social_auth_usersocialauth', 'social_auth_partial',
                'auth_permission', 'auth_group', 'auth_group_permissions',
                'user_groups', 'user_user_permissions'
            ])
        
        # 연결 정보 로드
        self.connection_info = self.config_manager.get_connection(conn_id)
        if not self.connection_info:
            raise ValueError(f"연결 정보를 찾을 수 없습니다: {conn_id}")
        
        # 데이터베이스 연결 설정
        self.engine, self.session, self.server = self.connection_manager.connect(conn_id)
        
        if not self.engine:
            raise ValueError(f"데이터베이스 연결 실패: {conn_id}")
        
        # 테이블 정보 저장할 딕셔너리 초기화
        self.tables_info = {}
        self.association_tables = {}
        self.relationships = {}
        
        # 모델 생성 여부를 결정하는 테이블 목록
        self.tables_to_generate = set()
        
        # 자동 매핑 베이스 생성 (관계 분석용)
        self.automap_base = automap_base()
        self.automap_base.prepare(self.engine, reflect=True)
        
        # 메타데이터 생성
        self.metadata = MetaData()
        self.metadata.reflect(bind=self.engine)

    def __del__(self):
        """
        객체 삭제 시 데이터베이스 연결 종료
        """
        try:
            if hasattr(self, 'connection_manager') and hasattr(self, 'conn_id'):
                self.connection_manager.disconnect(self.conn_id)
        except Exception as e:
            logger.warning(f"연결 종료 중 오류 발생: {str(e)}")

    def _should_generate_model(self, table_name):
        """
        테이블 모델 생성 여부 결정
        """
        # 포함 리스트가 있다면 그 리스트에 있는 테이블만 생성
        if self.include_tables:
            return table_name in self.include_tables
        
        # 제외 리스트에 있는 테이블은 생성하지 않음
        if table_name in self.exclude_tables:
            return False
        
        # 기본적으로 모든 테이블 생성
        return True
    
    def generate_models(self):
        """
        동적 모델 생성
        
        Returns:
            bool: 모델 생성 성공 여부
        """
        try:
            # 데이터베이스 연결 및 테이블 정보 추출
            inspector = inspect(self.engine)
            
            # 테이블 목록 조회
            tables = inspector.get_table_names()
            if not tables:
                logger.warning("데이터베이스에 테이블이 없습니다.")
                return False
            
            logger.info(f"총 {len(tables)}개 테이블 발견: {tables}")
            
            # 각 테이블 정보 수집
            for table_name in tables:
                if self._should_generate_model(table_name):
                    self._collect_table_info(inspector, table_name)
            
            # 테이블 분류 (일반 테이블과 연관 테이블)
            self._classify_tables()
            
            # 관계 정보 분석
            self._analyze_relationships()
            
            # 모델 파일 생성
            return self._write_model_file()
            
        except Exception as e:
            logger.error(f"모델 생성 중 오류 발생: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _collect_table_info(self, inspector, table_name: str) -> None:
        """
        테이블 정보 수집 함수
        
        Args:
            inspector: SQLAlchemy 인스펙터 객체
            table_name: 테이블 이름
        """
        # 컬럼 정보 수집
        columns = inspector.get_columns(table_name)
        
        # 기본 키 정보 수집
        pk_constraint = inspector.get_pk_constraint(table_name)
        primary_keys = pk_constraint.get('constrained_columns', [])
        
        # 외래 키 정보 수집
        foreign_keys = inspector.get_foreign_keys(table_name)
        
        # 유니크 제약 조건 수집
        unique_constraints = inspector.get_unique_constraints(table_name)
        
        # 인덱스 정보 수집
        indices = inspector.get_indexes(table_name)
        
        # 테이블 정보 저장
        self.tables_info[table_name] = {
            'columns': columns,
            'primary_keys': primary_keys,
            'foreign_keys': foreign_keys,
            'unique_constraints': unique_constraints,
            'indices': indices
        }
        
        # 생성할 테이블 목록에 추가
        self.tables_to_generate.add(table_name)
        
    def _classify_tables(self) -> None:
        """
        테이블을 일반 테이블과 연관 테이블로 분류하는 함수
        연관 테이블은 다대다 관계를 나타내는 중간 테이블
        """
        for table_name, info in self.tables_info.items():
            # 연관 테이블 판별 기준:
            # 1. 외래 키가 2개 이상
            # 2. 컬럼 수가 외래 키 수 + 몇 개 정도 (기본 키, 타임스탬프 등)
            # 3. 테이블 이름에 '_' 포함 (일반적인 명명 규칙)
            
            # 외래 키 개수 확인
            fk_count = len(info['foreign_keys'])
            
            # 컬럼 수가 적고, 외래 키가 대부분인 경우 연관 테이블로 간주
            total_columns = len(info['columns'])
            
            # 특수 케이스 처리: resource_tag_v2는 연관 테이블이 아닌 일반 테이블
            if table_name.endswith('_v2'):
                logger.info(f"일반 테이블로 분류 (특수 케이스): {table_name}")
                continue
                
            if (fk_count >= 2 and total_columns <= fk_count + 3) or ('_' in table_name and not table_name.endswith('_v2')):
                # 기본 키가 아닌 추가 컬럼 확인 (타임스탬프 등)
                non_pk_fk_columns = []
                for col in info['columns']:
                    is_fk_column = False
                    for fk in info['foreign_keys']:
                        if col['name'] in fk['constrained_columns']:
                            is_fk_column = True
                            break
                    if not is_fk_column and col['name'] not in info['primary_keys']:
                        non_pk_fk_columns.append(col)
                
                # 추가 컬럼이 많으면 일반 테이블로 간주
                if len(non_pk_fk_columns) > 3:
                    logger.info(f"일반 테이블로 분류 (추가 컬럼 다수): {table_name}")
                else:
                    self.association_tables[table_name] = info
                    logger.info(f"연관 테이블로 분류: {table_name}")
            else:
                logger.info(f"일반 테이블로 분류: {table_name}")
    
    def _analyze_relationships(self) -> None:
        """
        테이블 간 관계 정보 자동 분석 함수
        """
        # 각 테이블에 대한 관계 정보 저장 딕셔너리 초기화
        for table_name in self.tables_to_generate:
            if table_name not in self.association_tables:
                self.relationships[table_name] = []
        
        # 외래 키 기반 관계 분석 (일대다, 다대일)
        for table_name, info in self.tables_info.items():
            if table_name in self.association_tables:
                continue  # 연관 테이블은 별도 처리
                
            # 외래 키 관계 분석
            for fk in info['foreign_keys']:
                target_table = fk['referred_table']
                
                # 생성되지 않는 테이블에 대한 관계는 스킵
                if target_table not in self.tables_to_generate:
                    continue
                    
                local_cols = fk['constrained_columns']
                referred_cols = fk['referred_columns']
                
                # 관계 이름 생성 (외래 키 컬럼에서 _id 제거)
                relation_name = local_cols[0]
                if relation_name.endswith('_id'):
                    relation_name = relation_name[:-3]
                
                # 관계 정보 저장
                self.relationships[table_name].append({
                    'type': 'many_to_one',
                    'target_table': target_table,
                    'local_cols': local_cols,
                    'referred_cols': referred_cols,
                    'relation_name': relation_name,
                    'backref_name': f"{table_name}_set"  # 역참조 이름
                })
        
        # 연관 테이블 기반 다대다 관계 분석
        for assoc_name, assoc_info in self.association_tables.items():
            assoc_fks = assoc_info['foreign_keys']
            
            # 각 외래 키 테이블에 대해 관계 설정
            for i, fk1 in enumerate(assoc_fks):
                source_table = fk1['referred_table']
                
                # 생성되지 않는 테이블은 스킵
                if source_table not in self.tables_to_generate:
                    continue
                
                for j, fk2 in enumerate(assoc_fks):
                    if i != j:  # 같은 외래 키는 스킵
                        target_table = fk2['referred_table']
                        
                        # 생성되지 않는 테이블은 스킵
                        if target_table not in self.tables_to_generate:
                            continue
                        
                        # 관계 이름 생성
                        relation_name = f"{target_table}s"  # 복수형으로
                        
                        # 이미 존재하는 관계인지 확인
                        existing = False
                        for rel in self.relationships.get(source_table, []):
                            if rel.get('type') == 'many_to_many' and rel.get('target_table') == target_table and rel.get('association_table') == assoc_name:
                                existing = True
                                break
                        
                        if not existing:
                            # 관계 정보 저장
                            self.relationships.setdefault(source_table, []).append({
                                'type': 'many_to_many',
                                'target_table': target_table,
                                'association_table': assoc_name,
                                'relation_name': relation_name,
                                'backref_name': f"{source_table}s"  # 역참조 이름
                            })
        
        # 특수 관계 처리 (resource_tag_v2 사용 관계)
        if 'resource' in self.tables_to_generate and 'color_code_tags' in self.tables_to_generate and 'resource_tag_v2' in self.tables_to_generate:
            # 이미 존재하는 관계 확인
            has_tags_rel = False
            for rel in self.relationships.get('resource', []):
                if rel.get('relation_name') == 'tags':
                    has_tags_rel = True
                    break
                    
            if not has_tags_rel:
                # resource -> color_code_tags 특수 관계 추가
                self.relationships.setdefault('resource', []).append({
                    'type': 'special',
                    'target_table': 'color_code_tags',
                    'relation_name': 'tags',
                    'secondary': 'resource_tag_v2',
                    'backref_name': 'resources',
                    'additional_options': 'overlaps="tag_resources"'
                })
                
            # color_code_tags -> resource 특수 관계 추가
            has_resources_rel = False
            for rel in self.relationships.get('color_code_tags', []):
                if rel.get('relation_name') == 'resources':
                    has_resources_rel = True
                    break
                    
            if not has_resources_rel:
                self.relationships.setdefault('color_code_tags', []).append({
                    'type': 'special',
                    'target_table': 'resource',
                    'relation_name': 'resources',
                    'secondary': 'resource_tag_v2',
                    'backref_name': 'tags',
                    'additional_options': 'overlaps="tag_resources"'
                })
    
    def _get_column_type(self, column_info: Dict[str, Any]) -> str:
        """
        SQLAlchemy 컬럼 타입 문자열 반환
        
        Args:
            column_info: 컬럼 정보 딕셔너리
            
        Returns:
            str: SQLAlchemy 컬럼 타입 문자열
        """
        # 타입 이름과 기타 정보
        type_name = column_info['type'].__class__.__name__
        
        # PostgreSQL 특수 타입 처리
        if 'UUID' in type_name:
            return 'UUID(as_uuid=True)'
        elif 'ARRAY' in type_name:
            return 'ARRAY(Integer)'  # 기본값으로 Integer 배열 사용
        elif 'TIMESTAMP' in type_name:
            return 'DateTime'  # TIMESTAMP를 DateTime으로 변환
        elif 'DOUBLE_PRECISION' in type_name:
            return 'Float'  # DOUBLE_PRECISION을 Float로 변환
        
        # 기본 타입 처리
        common_types = {
            'INTEGER': 'Integer',
            'BIGINT': 'BigInteger',
            'SMALLINT': 'SmallInteger',
            'VARCHAR': 'String',
            'TEXT': 'Text',
            'BOOLEAN': 'Boolean',
            'FLOAT': 'Float',
            'NUMERIC': 'Numeric',
            'REAL': 'Float',
            'DATETIME': 'DateTime',
            'DATE': 'Date',
            'TIME': 'Time',
            'BINARY': 'LargeBinary',
            'BLOB': 'LargeBinary',
            'ENUM': 'Enum',  # 실제 값 목록은 별도 처리 필요
            'JSON': 'JSON'
        }
        
        for key, value in common_types.items():
            if key in type_name:
                if key == 'VARCHAR':
                    try:
                        length = getattr(column_info['type'], 'length', 255)
                        return f"String({length})"
                    except:
                        return 'String(255)'
                return value
        
        # 알 수 없는 타입
        logger.warning(f"알 수 없는 컬럼 타입: {type_name}")
        return 'String'  # 기본값
    
    def _write_model_file(self) -> bool:
        """
        SQLAlchemy 모델 코드 파일 생성
        
        Returns:
            bool: 파일 생성 성공 여부
        """
        try:
            with open(self.output_path, 'w', encoding='utf-8') as f:
                # 파일 헤더 작성
                f.write('#!/usr/bin/env python\n')
                f.write('# -*- coding: utf-8 -*-\n\n')
                f.write('"""\n')
                f.write('자동 생성된 SQLAlchemy 모델 파일\n\n')
                f.write(f'생성 시간: {datetime.datetime.now(seoul_tz).strftime("%Y-%m-%d %H:%M:%S")}\n')
                f.write('이 파일은 자동으로 생성되었으므로 직접 수정하지 마십시오.\n')
                f.write('"""\n\n')
                
                # 임포트 작성
                f.write('# Standard Library\n')
                f.write('from datetime import datetime\n')
                f.write('import uuid\n')
                f.write('from typing import List\n')
                f.write('from urllib.parse import quote_plus\n\n')
                
                f.write('# SQLAlchemy\n')
                f.write('from sqlalchemy import create_engine, Column, Integer, BigInteger, SmallInteger, String, Float, Boolean, ForeignKey, DateTime, Text, Table, UniqueConstraint, func, JSON\n')
                f.write('from sqlalchemy.orm import relationship\n')
                f.write('from sqlalchemy.ext.declarative import declarative_base\n')
                f.write('from sqlalchemy.dialects.postgresql import UUID, ARRAY\n')
                f.write('import pytz\n\n')
                
                f.write('# 서울 timezone 설정\n')
                f.write('seoul_tz = pytz.timezone(\'Asia/Seoul\')\n')
                f.write('Base = declarative_base()\n\n')
                
                # 연관 테이블 작성
                if self.association_tables:
                    f.write('# ------------------------------\n')
                    f.write('#  Association Tables\n')
                    f.write('# ------------------------------\n')
                    
                    for table_name, info in self.association_tables.items():
                        f.write(f'{table_name} = Table(\n')
                        f.write(f'   \'{table_name}\', \n')
                        f.write('   Base.metadata,\n')
                        
                        # 컬럼 작성
                        for col in info['columns']:
                            col_name = col['name']
                            
                            # 외래 키인지 확인
                            is_fk = False
                            referred_table = None
                            
                            for fk in info['foreign_keys']:
                                if col_name in fk['constrained_columns']:
                                    is_fk = True
                                    referred_table = fk['referred_table']
                                    break
                            
                            if is_fk and referred_table and referred_table in self.tables_to_generate:
                                f.write(f'   Column(\'{col_name}\', Integer, ForeignKey(\'{referred_table}.id\')),\n')
                            elif col_name in info['primary_keys']:
                                f.write(f'   Column(\'{col_name}\', Integer, primary_key=True),\n')
                            else:
                                col_type = self._get_column_type(col)
                                f.write(f'   Column(\'{col_name}\', {col_type}),\n')
                        
                        # 유니크 제약 조건 작성
                        unique_constraints = [
                            constraint for constraint in info['unique_constraints'] 
                            if constraint['column_names']
                        ]

                        for i, constraint in enumerate(unique_constraints):
                            col_names = ', '.join([f"'{col}'" for col in constraint['column_names']])
                            constraint_name = constraint.get('name', f"unique_{table_name}")
                            
                            # 마지막 UniqueConstraint가 아니면 쉼표 추가
                            trailing_comma = ',' if i < len(unique_constraints) - 1 else ''
                            f.write(f'   UniqueConstraint({col_names}, name=\'{constraint_name}\'){trailing_comma}\n')
                        
                        f.write(')\n\n')
                
                # 모델 클래스 작성
                f.write('# ------------------------------\n')
                f.write('#  Models\n')
                f.write('# ------------------------------\n')
                
                # 일반 테이블에 대한 모델 클래스 작성
                for table_name, info in self.tables_info.items():
                    if table_name in self.association_tables:
                        continue
                    
                    # 클래스 이름 생성 (테이블 이름을 CamelCase로 변환)
                    class_name = ''.join(word.capitalize() for word in table_name.split('_'))
                    
                    f.write(f'class {class_name}(Base):\n')
                    f.write(f'   __tablename__ = \'{table_name}\'\n\n')
                    
                    # 기본 속성 작성
                    for col in info['columns']:
                        col_name = col['name']
                        nullable = 'nullable=True' if col.get('nullable', True) else 'nullable=False'
                        unique = 'unique=True' if col.get('unique', False) else ''
                        default = ''
                        
                        # 기본값 설정
                        if col.get('default') is not None:
                            default_val = col['default']
                            if isinstance(default_val, str):
                                default = f', default="{default_val}"'
                            elif isinstance(default_val, bool):
                                default = f', default={str(default_val)}'
                            elif isinstance(default_val, (int, float)):
                                default = f', default={default_val}'
                            else:
                                # 복잡한 기본값 (함수 등)
                                if 'now' in str(default_val).lower():
                                    default = ', default=lambda: datetime.now(seoul_tz)'
                        
                        # 외래 키인지 확인
                        is_fk = False
                        referred_table = None
                        
                        for fk in info['foreign_keys']:
                            if col_name in fk['constrained_columns']:
                                is_fk = True
                                referred_table = fk['referred_table']
                                break
                        
                        # 컬럼 정의 작성
                        if col_name in info['primary_keys']:
                            f.write(f'   {col_name} = Column({self._get_column_type(col)}, primary_key=True)\n')
                        elif is_fk and referred_table and referred_table in self.tables_to_generate:
                            f.write(f'   {col_name} = Column(Integer, ForeignKey(\'{referred_table}.id\'), {nullable})\n')
                        else:
                            col_type = self._get_column_type(col)
                            extras = ', '.join(filter(None, [unique, nullable, default[2:] if default else None]))
                            extras_str = f', {extras}' if extras else ''
                            f.write(f'   {col_name} = Column({col_type}{extras_str})\n')
                    
                    f.write('\n')
                    
                    # 관계 정의 작성
                    if table_name in self.relationships and self.relationships[table_name]:
                        f.write('   # Relationships\n')
                        
                        for rel in self.relationships[table_name]:
                            target_class = ''.join(word.capitalize() for word in rel['target_table'].split('_'))
                            
                            if rel['type'] == 'many_to_one':
                                # 문자열로 지연 로딩 관계 정의
                                relationship_def = f'   {rel["relation_name"]} = relationship("{target_class}", foreign_keys=[{rel["local_cols"][0]}])\n'
                                f.write(relationship_def)
                            
                            elif rel['type'] == 'one_to_many':
                                # 문자열로 지연 로딩 관계 정의
                                relationship_def = f'   {rel["relation_name"]} = relationship("{target_class}", back_populates="{rel["backref_name"]}")\n'
                                f.write(relationship_def)
                            
                            elif rel['type'] == 'many_to_many':
                                # 문자열로 지연 로딩 관계 정의
                                relationship_def = f'   {rel["relation_name"]} = relationship("{target_class}", secondary={rel["association_table"]}, back_populates="{rel["backref_name"]}")\n'
                                f.write(relationship_def)
                                
                            elif rel['type'] == 'special':
                                # 특별한 관계 정의
                                additional = f', {rel["additional_options"]}' if rel.get("additional_options") else ''
                                relationship_def = f'   {rel["relation_name"]} = relationship(\n      "{target_class}",\n      secondary="{rel["secondary"]}",\n      back_populates="{rel["backref_name"]}"{additional}\n   )\n'
                                f.write(relationship_def)
                    
                    f.write('\n')
                 
                # 파일 끝
                f.write('\n# 생성 완료')
            
            logger.info(f"모델 파일 생성 완료: {self.output_path}")
            return True
            
        except Exception as e:
            logger.error(f"모델 파일 생성 실패: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def load_generated_models(self):
        """
        생성된 모델 파일을 동적으로 로드
        
        Returns:
            모듈 객체
        """
        try:
            # 모듈 경로 계산
            module_path = os.path.splitext(os.path.basename(self.output_path))[0]
            package_path = '.'.join(os.path.dirname(self.output_path).split(os.sep)[-2:])
            full_module_path = f"{package_path}.{module_path}"
            
            # 이미 로드된 모듈이 있으면 리로드
            if full_module_path in sys.modules:
                return importlib.reload(sys.modules[full_module_path])
            
            # 모듈 로드
            return importlib.import_module(full_module_path)
        except Exception as e:
            logger.error(f"모델 로드 실패: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None