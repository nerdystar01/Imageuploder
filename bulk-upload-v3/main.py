#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
from typing import Optional

# 로컬 모듈 임포트
from bulk_uploader_v3 import main as bulk_uploader_main
from prompt_tag_extractor import analyze_prompt, display_extracted_tags
from search_tags import search_normal_tags, display_tags

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_user_input():
    """사용자로부터 기본 정보 입력받기"""
    try:
        # 사용자 ID 입력
        while True:
            try:
                user_id = int(input("사용자 ID를 입력해주세요: ").strip())
                break
            except ValueError:
                print("올바른 숫자를 입력해주세요.")

        return user_id

    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
        sys.exit(0)

def validate_user(session, user_id: int) -> bool:
    """사용자 ID가 유효한지 검증"""
    try:
        from models import User
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            print(f"사용자 ID {user_id}가 존재하지 않습니다.")
            return False
        return True
    except Exception as e:
        print(f"사용자 검증 중 오류 발생: {str(e)}")
        return False

def show_menu():
    """메인 메뉴 표시"""
    print("\n==== 이미지 처리 시스템 ====")
    print("1. 벌크 업로더 실행")
    print("2. 태그 검색")
    print("3. 프롬프트 태그 분석")
    print("0. 종료")
    print("========================")

def search_tag_function(user_id: int):
    """태그 검색 기능 호출"""
    search_term = input("검색할 태그 이름을 입력해주세요 (빈 칸 입력 시 전체 조회): ").strip()
    tags = search_normal_tags(user_id, search_term)
    display_tags(tags)

def prompt_tag_analysis(user_id: int):
    """프롬프트 태그 분석 기능 호출"""
    print("\n===== 프롬프트 태그 분석 =====")
    
    # 데이터베이스 연결 여부 선택
    use_db = input("데이터베이스에 연결하여 태그 존재 여부를 확인하시겠습니까? (y/n): ").strip().lower() == 'y'
    
    # 프롬프트 입력 방식 선택
    input_method = input("\n입력 방식 선택:\n1. 직접 입력\n2. 파일에서 불러오기\n선택: ").strip()
    
    prompt_text = ""
    
    if input_method == '1':
        print("\n프롬프트를 입력하세요 (입력 완료 후 빈 줄에서 엔터):")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        prompt_text = "\n".join(lines)
    elif input_method == '2':
        file_path = input("\n프롬프트 파일 경로: ").strip()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                prompt_text = f.read()
        except Exception as e:
            print(f"파일 읽기 오류: {str(e)}")
            return
    else:
        print("잘못된 선택입니다.")
        return
    
    if not prompt_text:
        print("프롬프트가 비어 있습니다.")
        return
    
    # 프롬프트 분석
    print("\n프롬프트 분석 중...")
    extracted_tags = analyze_prompt(prompt_text, use_db)
    
    # 결과 출력
    display_extracted_tags(extracted_tags)

def main():
    """메인 함수"""
    # 로깅 설정
    setup_logging()
    
    try:
        # 사용자 ID 입력 받기
        user_id = get_user_input()
        
        # 메뉴 루프
        while True:
            show_menu()
            choice = input("메뉴를 선택하세요 (0-3): ").strip()
            
            if choice == '0':
                print("프로그램을 종료합니다.")
                break
            elif choice == '1':
                # 벌크 업로더 실행
                print("\n벌크 업로더를 실행합니다...")
                bulk_uploader_main()
            elif choice == '2':
                # 태그 검색 실행
                print("\n태그 검색을 실행합니다...")
                search_tag_function(user_id)
            elif choice == '3':
                # 프롬프트 태그 분석 실행
                print("\n프롬프트 태그 분석을 실행합니다...")
                prompt_tag_analysis(user_id)
            else:
                print("유효하지 않은 메뉴 선택입니다. 다시 선택해주세요.")
                
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"처리 중 오류 발생: {str(e)}")
        print(f"오류가 발생했습니다: {str(e)}")

if __name__ == "__main__":
    main()