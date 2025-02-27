#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
from typing import List, Optional

from sqlalchemy import func
from models import ColorCodeTags, User
from utills import Utills

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def search_normal_tags(user_id: int, search_term: Optional[str] = None) -> List[ColorCodeTags]:
    """
    노말 타입의 태그 리스트를 검색합니다. (소문자로 검색)
    
    Args:
        user_id: 사용자 ID
        search_term: 검색어 (선택적)
        
    Returns:
        List[ColorCodeTags]: 검색 결과 태그 리스트
    """
    utils = Utills()
    
    # 검색어가 제공되지 않았으면 입력 받기
    if search_term is None:
        search_term = input("검색할 태그 이름을 입력해주세요 (빈 칸 입력 시 전체 조회): ").strip()
    
    # 데이터베이스 연결
    session, server = utils.get_session()
    
    try:
        # 검색 쿼리 구성
        query = session.query(ColorCodeTags).filter(
            ColorCodeTags.type == 'normal'
        )
        
        # 검색어가 있으면 조건 추가
        if search_term:
            query = query.filter(
                func.lower(ColorCodeTags.tag).like(f"%{search_term.lower()}%")
            )
            
        # 실행 및 결과 정렬
        tags = query.order_by(ColorCodeTags.tag).all()
        
        # 결과 반환
        return tags
            
    except Exception as e:
        print(f"태그 검색 중 오류 발생: {str(e)}")
        return []
    finally:
        utils.end_session(session)

def display_tags(tags: List[ColorCodeTags]):
    """
    태그 목록을 출력합니다.
    
    Args:
        tags: 출력할 태그 리스트
    """
    if tags:
        print(f"\n=== 검색 결과: {len(tags)}개의 태그 발견 ===")
        print("ID\t| 유저ID\t| 타입\t| 태그명")
        print("-"*60)
        for tag in tags:
            user_id_str = str(tag.user_id) if tag.user_id else "없음"
            type_str = tag.type if tag.type else "normal"
            print(f"{tag.id}\t| {user_id_str}\t| {type_str}\t| {tag.tag}")
    else:
        print("\n검색 결과가 없습니다.")

def main():
    """
    태그 검색 기능의 메인 함수
    """
    setup_logging()
    
    try:
        # 사용자 ID 입력
        while True:
            try:
                user_id = int(input("사용자 ID를 입력해주세요: ").strip())
                break
            except ValueError:
                print("올바른 숫자를 입력해주세요.")
        
        # 검색어 입력
        search_term = input("검색할 태그 이름을 입력해주세요 (빈 칸 입력 시 전체 조회): ").strip()
        
        # 태그 검색 수행
        tags = search_normal_tags(user_id, search_term)
        
        # 결과 출력
        display_tags(tags)
        
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")
    except Exception as e:
        logging.error(f"처리 중 오류가 발생했습니다: {str(e)}")
        print("오류가 발생했습니다. 로그를 확인해주세요.")

if __name__ == "__main__":
    main()