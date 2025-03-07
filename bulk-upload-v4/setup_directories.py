#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
디렉토리 구조 설정 스크립트

이 스크립트는 필요한 디렉토리 구조를 생성합니다.
"""

import os
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_directories():
    """필요한 디렉토리 구조 생성"""
    # 현재 스크립트의 디렉토리 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 생성할 디렉토리 목록
    directories = [
        # 소스 디렉토리
        os.path.join(current_dir, 'src'),
        os.path.join(current_dir, 'src', 'database'),
        os.path.join(current_dir, 'src', 'database', 'data'),
        os.path.join(current_dir, 'src', 'ui'),
        os.path.join(current_dir, 'src', 'utils'),
        
        # 테스트 디렉토리
        os.path.join(current_dir, 'tests'),
        
        # 자산 디렉토리
        os.path.join(current_dir, 'assets'),
        os.path.join(current_dir, 'assets', 'icons'),
        os.path.join(current_dir, 'assets', 'images'),
        os.path.join(current_dir, 'assets', 'styles'),
        
        # 자격 증명 디렉토리
        os.path.join(current_dir, 'credentials')
    ]
    
    # 디렉토리 생성
    for directory in directories:
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logger.info(f"디렉토리 생성: {directory}")
            else:
                logger.info(f"디렉토리 이미 존재: {directory}")
        except Exception as e:
            logger.error(f"디렉토리 생성 실패: {directory} - {str(e)}")
    
    # __init__.py 파일 생성
    init_files = [
        os.path.join(current_dir, 'src', '__init__.py'),
        os.path.join(current_dir, 'src', 'database', '__init__.py'),
        os.path.join(current_dir, 'src', 'ui', '__init__.py'),
        os.path.join(current_dir, 'src', 'utils', '__init__.py'),
        os.path.join(current_dir, 'tests', '__init__.py')
    ]
    
    # __init__.py 파일 생성
    for init_file in init_files:
        if not os.path.exists(init_file):
            with open(init_file, 'w', encoding='utf-8') as f:
                f.write(f'"""\n{os.path.basename(os.path.dirname(init_file))} 패키지\n"""\n')
            logger.info(f"파일 생성: {init_file}")
        else:
            logger.info(f"파일 이미 존재: {init_file}")
    
    logger.info("디렉토리 구조 설정 완료")

if __name__ == "__main__":
    create_directories()