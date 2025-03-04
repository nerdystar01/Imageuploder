#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from typing import List, Optional, Tuple, Any

from sqlalchemy import func
from models import ColorCodeTags, User
from session_utills import get_session, end_session

def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def search_normal_tags(user_id: int, search_term: Optional[str] = "", page: int = 1, page_size: int = 50) -> Tuple[List[Any], int]:
    """
    노말 타입의 태그 리스트를 검색합니다. (소문자로 검색)
    
    Args:
        user_id: 사용자 ID
        search_term: 검색어 (기본값은 빈 문자열)
        page: 페이지 번호 (1부터 시작)
        page_size: 페이지 당 항목 수
        
    Returns:
        Tuple[List[Any], int]: (검색 결과 태그 리스트, 전체 항목 수)
    """
    # 데이터베이스 연결
    session, server = None, None
    
    try:
        session, server = get_session()
        
        # 사용자 검증
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            print(f"사용자 ID {user_id}가 존재하지 않습니다.")
            return [], 0
        
        # 검색 쿼리 구성
        query = session.query(ColorCodeTags).filter(
            ColorCodeTags.type == 'normal'
        )
        
        # 검색어가 있으면 조건 추가
        if search_term:
            query = query.filter(
                func.lower(ColorCodeTags.tag).like(f"%{search_term.lower()}%")
            )
        
        # 전체 항목 수 계산
        total_count = query.count()
        
        # 페이지네이션 적용
        offset = (page - 1) * page_size
        query = query.order_by(ColorCodeTags.id.desc()).offset(offset).limit(page_size)
            
        # 실행 및 결과
        tags = query.all()
        
        # 결과를 딕셔너리 리스트로 변환 (세션 종료 후에도 접근 가능하도록)
        result = []
        for tag in tags:
            result.append({
                'id': tag.id,
                'user_id': tag.user_id,
                'type': tag.type,
                'tag': tag.tag
            })
        
        return result, total_count
            
    except Exception as e:
        print(f"태그 검색 중 오류 발생: {str(e)}")
        return [], 0
    finally:
        if session and server:
            end_session(session, server)

def display_tags(tags: List[Any], page: int = 1, page_size: int = 50, total_count: int = 0):
    """
    태그 목록을 출력합니다.
    
    Args:
        tags: 출력할 태그 리스트
        page: 현재 페이지 번호 (기본값 1)
        page_size: 페이지 당 항목 수 (기본값 50)
        total_count: 전체 항목 수 (기본값 0)
    """
    if tags:
        if total_count > 0:  # 페이지네이션 정보가 있을 경우
            total_pages = (total_count + page_size - 1) // page_size  # 올림 나눗셈
            start_idx = (page - 1) * page_size + 1
            end_idx = min(page * page_size, total_count)
            
            print(f"\n=== 검색 결과: 총 {total_count}개 중 {start_idx}-{end_idx}번 태그 (페이지 {page}/{total_pages}) ===")
        else:  # 간단히 전체 갯수만 표시 (구버전 호환성)
            print(f"\n=== 검색 결과: {len(tags)}개의 태그 발견 ===")
            
        print("ID\t| 유저ID\t| 타입\t| 태그명")
        print("-"*60)
        
        for tag in tags:
            try:
                # 객체가 딕셔너리인 경우
                if isinstance(tag, dict):
                    tag_id = tag.get('id', 'N/A')
                    user_id = tag.get('user_id', None)
                    tag_type = tag.get('type', 'normal')
                    tag_name = tag.get('tag', 'N/A')
                # SQLAlchemy 객체인 경우
                else:
                    tag_id = getattr(tag, 'id', 'N/A')
                    user_id = getattr(tag, 'user_id', None)
                    tag_type = getattr(tag, 'type', 'normal')
                    tag_name = getattr(tag, 'tag', 'N/A')
                
                user_id_str = str(user_id) if user_id else "없음"
                type_str = tag_type if tag_type else "normal"
                
                print(f"{tag_id}\t| {user_id_str}\t| {type_str}\t| {tag_name}")
            except Exception as e:
                print(f"[오류: {str(e)}] - {tag}")
        
        if total_count > 0:  # 페이지네이션 사용 시에만 표시
            print(f"\n--- 페이지 {page}/{total_pages} ---")
            if page > 1:
                print("이전 페이지: p, ", end="")
            if page < total_pages:
                print("다음 페이지: n, ", end="")
            print("종료: q")
    else:
        print("\n검색 결과가 없습니다.")

def browse_tags(user_id: int, search_term: Optional[str] = ""):
    """
    태그를 페이지별로 탐색합니다.
    
    Args:
        user_id: 사용자 ID
        search_term: 검색어 (기본값은 빈 문자열)
    """
    page = 1
    page_size = 50
    
    while True:
        # 태그 검색 수행
        tags, total_count = search_normal_tags(user_id, search_term, page, page_size)
        
        # 결과 출력
        display_tags(tags, page, page_size, total_count)
        
        if total_count == 0:
            break
            
        # 사용자 입력 처리
        choice = input("\n명령을 입력하세요 (p: 이전, n: 다음, q: 종료): ").strip().lower()
        
        if choice == 'q':
            break
        elif choice == 'p' and page > 1:
            page -= 1
        elif choice == 'n' and page * page_size < total_count:
            page += 1
        else:
            print("잘못된 명령입니다.")

def search_tags_simple(user_id: int, search_term: Optional[str] = ""):
    """
    기본 태그 검색 기능 (단일 페이지 표시)
    
    Args:
        user_id: 사용자 ID
        search_term: 검색어 (기본값은 빈 문자열)
    """
    # 태그 검색 수행 (페이지네이션 없이)
    tags, total_count = search_normal_tags(user_id, search_term)
    
    # 결과 출력 (구버전 방식)
    display_tags(tags)

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
        
        # 메뉴 표시
        print("\n=== 태그 검색 시스템 ===")
        print("1. 태그 검색 (단일 페이지)")
        print("2. 태그 리스트 열람 (페이지네이션)")
        print("3. 종료")
        
        choice = input("\n원하는 기능을 선택하세요: ").strip()
        
        if choice == '1':
            # 검색어 입력
            search_term = input("검색할 태그 이름을 입력해주세요 (빈 칸 입력 시 전체 조회): ").strip()
            
            # 태그 검색 수행 (단일 페이지)
            search_tags_simple(user_id, search_term)
            
        elif choice == '2':
            # 태그 열람 여부 확인
            view_tags = input("태그리스트를 열람하시겠습니까? (y/n): ").strip().lower()
            
            if view_tags == 'y':
                # 검색어 입력
                search_term = input("검색할 태그 이름을 입력해주세요 (빈 칸 입력 시 전체 조회): ").strip()
                
                # 태그 페이지별 탐색
                browse_tags(user_id, search_term)
            else:
                print("태그 열람을 취소했습니다.")
        
        elif choice == '3':
            print("프로그램을 종료합니다.")
        
        else:
            print("잘못된 선택입니다.")
        
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")
    except Exception as e:
        logging.error(f"처리 중 오류가 발생했습니다: {str(e)}")
        print(f"오류가 발생했습니다: {str(e)}")
        print("로그를 확인해주세요.")

if __name__ == "__main__":
    main()