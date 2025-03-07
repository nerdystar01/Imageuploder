#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
테스트 메인 실행 파일

이 스크립트는 tests 폴더에 있는 테스트 파일들을 실행합니다.
"""

import os
import sys
import importlib
import logging
from typing import List

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def discover_tests(test_dir: str) -> List[str]:
    """
    테스트 디렉토리에서 테스트 파일 검색
    
    Args:
        test_dir: 테스트 디렉토리 경로
        
    Returns:
        List[str]: 테스트 모듈 이름 목록
    """
    test_modules = []
    
    # 디렉토리가 존재하는지 확인
    if not os.path.exists(test_dir) or not os.path.isdir(test_dir):
        logger.error(f"테스트 디렉토리가 존재하지 않습니다: {test_dir}")
        return []
    
    # 테스트 파일 검색
    for file in os.listdir(test_dir):
        if file.startswith('test_') and file.endswith('.py'):
            # .py 확장자 제거하고 모듈 이름으로 변환
            module_name = os.path.splitext(file)[0]
            test_modules.append(module_name)
    
    return test_modules

def run_test(test_module: str) -> bool:
    """
    지정된 테스트 모듈 실행
    
    Args:
        test_module: 테스트 모듈 이름
        
    Returns:
        bool: 테스트 성공 여부
    """
    logger.info(f"테스트 실행: {test_module}")
    
    try:
        # 테스트 모듈 임포트
        module = importlib.import_module(f"tests.{test_module}")
        
        # 모듈에 run_test 함수가 있는지 확인
        if hasattr(module, 'run_test') and callable(module.run_test):
            # 테스트 실행
            result = module.run_test()
            
            if result:
                logger.info(f"테스트 성공: {test_module}")
            else:
                logger.error(f"테스트 실패: {test_module}")
                
            return result
        else:
            logger.error(f"테스트 모듈에 run_test 함수가 없습니다: {test_module}")
            return False
            
    except Exception as e:
        logger.error(f"테스트 실행 중 오류 발생: {str(e)}", exc_info=True)
        return False

def main():
    """테스트 메인 함수"""
    # 현재 디렉토리를 시스템 경로에 추가하여 모듈을 찾을 수 있도록 함
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    
    # 테스트 디렉토리 경로
    test_dir = os.path.join(current_dir, 'tests')
    
    # 실행할 특정 테스트가 명령줄 인수로 제공되었는지 확인
    if len(sys.argv) > 1:
        test_modules = [f"test_{sys.argv[1]}"]
    else:
        # 테스트 모듈 검색
        test_modules = discover_tests(test_dir)
    
    if not test_modules:
        logger.warning("실행할 테스트가 없습니다.")
        return
    
    # 테스트 결과 추적
    results = []
    
    # 각 테스트 모듈 실행
    for test_module in test_modules:
        success = run_test(test_module)
        results.append((test_module, success))
    
    # 테스트 결과 요약
    logger.info("\n=== 테스트 결과 요약 ===")
    for module, success in results:
        status = "성공" if success else "실패"
        logger.info(f"{module}: {status}")
    
    # 모든 테스트 성공 여부
    all_success = all(success for _, success in results)
    logger.info(f"\n전체 테스트 결과: {'성공' if all_success else '실패'}")
    
    # 종료 코드 설정 (성공: 0, 실패: 1)
    sys.exit(0 if all_success else 1)

if __name__ == "__main__":
    main()