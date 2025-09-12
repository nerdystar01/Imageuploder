#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Any
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import and_, text
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 로컬 모듈 임포트
from models import Resource, VertexAiEmbedDbEmbeddings, setup_database_engine
from resource_embedding_helper import ResourceEmbeddingHelper
from session_utills import get_session, stop_ssh_tunnel  # SSH 터널 관련 함수 import

logger = logging.getLogger(__name__)

class MissingEmbeddingsProcessor:
    """7일간 임베딩 누락 리소스를 처리하는 클래스"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        # get_session()을 사용하여 세션과 SSH 터널 생성
        self.session_obj, self.ssh_tunnel = get_session()
        self.session = self.session_obj()  # scoped_session에서 실제 세션 가져오기
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
        if self.ssh_tunnel:
            stop_ssh_tunnel(self.ssh_tunnel)

    def find_missing_embedding_resources(self, days: int = 7) -> List[Resource]:
        """
        지정된 일수 동안 생성되었지만 임베딩이 누락된 리소스들을 찾습니다.
        
        Args:
            days (int): 검색할 일수 (기본값: 7일)
            
        Returns:
            List[Resource]: 임베딩이 누락된 리소스들의 리스트
        """
        try:
            # N일 전 날짜 계산
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 1. 기간 내 이미지가 있는 모든 리소스 가져오기
            resources_with_images = self.session.query(Resource).filter(
                and_(
                    Resource.user_id == self.user_id,
                    Resource.created_at >= cutoff_date,
                    Resource.image.isnot(None),
                    Resource.image != ''
                )
            ).all()
            
            # 2. UUID 문자열 리스트 생성
            resource_uuids = {str(r.uuid): r for r in resources_with_images}
            
            # 3. 임베딩 테이블에 있는 UUID들 가져오기
            existing_embeddings = self.session.query(VertexAiEmbedDbEmbeddings.file_based_uuid).filter(
                VertexAiEmbedDbEmbeddings.file_based_uuid.in_(list(resource_uuids.keys()))
            ).all()
            
            existing_uuid_set = {e[0] for e in existing_embeddings}
            
            # 4. 누락된 리소스들 찾기
            missing_resources = [resource_uuids[uuid] for uuid in resource_uuids if uuid not in existing_uuid_set]
            
            logger.info(f"최근 {days}일간 임베딩이 누락된 리소스 {len(missing_resources)}개를 발견했습니다.")
            return missing_resources
            
        except Exception as e:
            logger.error(f"임베딩 누락 리소스 검색 중 오류 발생: {str(e)}")
            return []

    def display_missing_resources_summary(self, resources: List[Resource]):
        """누락된 리소스들의 요약 정보를 출력합니다."""
        if not resources:
            print("✅ 임베딩이 누락된 리소스가 없습니다.")
            return
            
        print(f"\n📋 임베딩 누락 리소스 요약 ({len(resources)}개)")
        print("=" * 60)
        
        # 날짜별 분류
        date_groups = {}
        for resource in resources:
            date_key = resource.created_at.strftime('%Y-%m-%d')
            if date_key not in date_groups:
                date_groups[date_key] = []
            date_groups[date_key].append(resource)
        
        for date, date_resources in sorted(date_groups.items(), reverse=True):
            print(f"\n📅 {date}: {len(date_resources)}개")
            for i, resource in enumerate(date_resources[:3], 1):  # 각 날짜별로 최대 3개만 표시
                print(f"  {i}. ID: {resource.id}, 파일: {resource.image[:50]}{'...' if len(resource.image) > 50 else ''}")
            if len(date_resources) > 3:
                print(f"  ... 및 {len(date_resources) - 3}개 더")

    def process_embeddings_batch(self, resources: List[Resource], 
                                batch_size: int = 10,
                                max_workers: int = 12) -> dict:
        """
        리소스들의 임베딩을 병렬로 배치 처리합니다.
        
        Args:
            resources (List[Resource]): 처리할 리소스들
            batch_size (int): 진행상황 표시 단위 (기본값: 10)
            max_workers (int): 최대 워커 스레드 수 (기본값: 12)
            
        Returns:
            dict: 처리 결과 통계
        """
        total_count = len(resources)
        success_count = 0
        error_count = 0
        errors = []
        completed_count = 0
        lock = threading.Lock()
        
        print(f"\n🚀 {total_count}개 리소스의 임베딩 처리를 시작합니다...")
        print(f"🔧 최대 워커 수: {max_workers}")
        print(f"📦 진행상황 표시 단위: {batch_size}개마다")
        
        def process_single_resource(resource_id):
            """단일 리소스 처리 함수 - 각 스레드가 독립적인 세션 사용"""
            # 각 스레드마다 새로운 세션과 SSH 터널 생성
            thread_session_obj, thread_ssh_tunnel = get_session()
            thread_session = thread_session_obj()
            
            try:
                print(f"  🔄 처리 시작: ID {resource_id}")
                
                # 새로운 세션으로 ResourceEmbeddingHelper 실행
                helper = ResourceEmbeddingHelper(
                    resource_id=resource_id, 
                    session=thread_session
                )
                helper.run()
                
                # 커밋
                thread_session.commit()
                
                print(f"  ✅ 완료: ID {resource_id}")
                return ('success', resource_id, None)
                
            except Exception as e:
                # 롤백
                thread_session.rollback()
                error_msg = f"Resource ID {resource_id}: {str(e)}"
                logger.error(f"리소스 ID {resource_id} 처리 중 오류: {str(e)}")
                print(f"  ❌ 실패: ID {resource_id} - {str(e)}")
                return ('error', resource_id, error_msg)
                
            finally:
                # 세션과 SSH 터널 정리
                thread_session.close()
                if thread_ssh_tunnel:
                    stop_ssh_tunnel(thread_ssh_tunnel)
        
        # 리소스 ID 리스트 준비 (Resource 객체 대신 ID만 전달)
        resource_ids = [r.id for r in resources]
        
        # ThreadPoolExecutor를 사용한 병렬 처리
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 모든 작업 제출
            future_to_resource_id = {
                executor.submit(process_single_resource, resource_id): resource_id 
                for resource_id in resource_ids
            }
            
            # 완료된 작업들 처리
            for future in as_completed(future_to_resource_id):
                with lock:
                    completed_count += 1
                    result = future.result()
                    
                    if result[0] == 'success':
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append(result[2])
                    
                    # 진행상황 출력
                    if completed_count % batch_size == 0 or completed_count == total_count:
                        print(f"\n📊 진행상황: {completed_count}/{total_count} 완료 ({(completed_count/total_count)*100:.1f}%)")
                        print(f"   ✅ 성공: {success_count}, ❌ 실패: {error_count}")
        
        # 결과 통계
        result = {
            'total': total_count,
            'success': success_count,
            'error': error_count,
            'errors': errors
        }
        
        return result

    def display_processing_results(self, result: dict):
        """처리 결과를 출력합니다."""
        print(f"\n{'='*60}")
        print("🎯 처리 결과 요약")
        print(f"{'='*60}")
        print(f"📊 전체: {result['total']}개")
        print(f"✅ 성공: {result['success']}개")
        print(f"❌ 실패: {result['error']}개")
        
        if result['error'] > 0:
            print(f"\n❌ 실패한 리소스들:")
            for i, error in enumerate(result['errors'][:10], 1):  # 최대 10개만 표시
                print(f"  {i}. {error}")
            if len(result['errors']) > 10:
                print(f"  ... 및 {len(result['errors']) - 10}개 더")
        
        success_rate = (result['success'] / result['total'] * 100) if result['total'] > 0 else 0
        print(f"\n📈 성공률: {success_rate:.1f}%")


def process_missing_embeddings_interactive(user_id: int):
    """대화형 임베딩 누락 리소스 처리 함수"""
    print("\n===== 7일간 임베딩 누락 리소스 임베딩 =====")
    
    try:
        with MissingEmbeddingsProcessor(user_id) as processor:
            # 1. 누락된 리소스 찾기
            print("🔍 임베딩이 누락된 리소스를 검색 중...")
            missing_resources = processor.find_missing_embedding_resources()
            
            # 2. 요약 정보 출력
            processor.display_missing_resources_summary(missing_resources)
            
            if not missing_resources:
                return
            
            # 3. 사용자 확인
            print(f"\n❓ {len(missing_resources)}개의 리소스에 임베딩을 생성하시겠습니까?")
            proceed = input("계속하려면 'y', 취소하려면 다른 키를 입력하세요: ").strip().lower()
            
            if proceed != 'y':
                print("❌ 임베딩 생성을 취소했습니다.")
                return
            
            # 4. 배치 크기 설정
            try:
                batch_size = int(input("\n진행상황 표시 단위를 입력하세요 (기본값: 10): ").strip() or "10")
                if batch_size <= 0:
                    batch_size = 10
            except ValueError:
                batch_size = 10
                
            # 5. 워커 수 설정
            try:
                max_workers = int(input("최대 워커 수를 입력하세요 (기본값: 12): ").strip() or "12")
                if max_workers <= 0:
                    max_workers = 12
            except ValueError:
                max_workers = 12
                
            print(f"📦 진행상황 표시: {batch_size}개마다")
            print(f"🔧 최대 워커 수: {max_workers}로 설정되었습니다.")
            
            # 6. 임베딩 처리 실행
            result = processor.process_embeddings_batch(missing_resources, batch_size, max_workers)
            
            # 7. 결과 출력
            processor.display_processing_results(result)
            
    except Exception as e:
        logger.error(f"임베딩 처리 중 전체 오류 발생: {str(e)}")
        print(f"❌ 오류가 발생했습니다: {str(e)}")


def process_missing_embeddings_with_options(user_id: int):
    """옵션이 있는 임베딩 누락 리소스 처리 함수"""
    print("\n===== 임베딩 누락 리소스 처리 (고급) =====")
    
    try:
        # 검색 기간 설정
        print("\n📅 검색 기간을 설정하세요:")
        print("1. 최근 1일")
        print("2. 최근 3일")  
        print("3. 최근 7일 (기본값)")
        print("4. 최근 14일")
        print("5. 최근 30일")
        print("6. 사용자 지정")
        
        period_choice = input("\n선택 (1-6, 기본값: 3): ").strip() or "3"
        
        days_map = {"1": 1, "2": 3, "3": 7, "4": 14, "5": 30}
        
        if period_choice in days_map:
            days = days_map[period_choice]
        elif period_choice == "6":
            try:
                days = int(input("검색할 일수를 입력하세요: ").strip())
                if days <= 0:
                    days = 7
            except ValueError:
                days = 7
        else:
            days = 7
            
        print(f"📆 최근 {days}일간의 리소스를 검색합니다.")
        
        with MissingEmbeddingsProcessor(user_id) as processor:
            # 누락된 리소스 찾기
            missing_resources = processor.find_missing_embedding_resources(days)
            processor.display_missing_resources_summary(missing_resources)
            
            if not missing_resources:
                return
            
            # 처리 방식 선택
            print(f"\n🔧 처리 방식을 선택하세요:")
            print("1. 전체 처리")
            print("2. 미리보기 후 처리 (처음 5개만 먼저 처리)")
            print("3. 취소")
            
            mode_choice = input("\n선택 (1-3): ").strip()
            
            if mode_choice == "3":
                print("❌ 처리를 취소했습니다.")
                return
            elif mode_choice == "2":
                # 미리보기 모드
                preview_resources = missing_resources[:5]
                print(f"\n🔍 미리보기: 처음 {len(preview_resources)}개 리소스를 처리합니다.")
                
                # 미리보기에서는 워커 수를 적게 설정
                result = processor.process_embeddings_batch(preview_resources, batch_size=5, max_workers=3)
                processor.display_processing_results(result)
                
                if len(missing_resources) > 5:
                    continue_all = input(f"\n나머지 {len(missing_resources) - 5}개도 처리하시겠습니까? (y/n): ").strip().lower()
                    if continue_all == 'y':
                        remaining_resources = missing_resources[5:]
                        
                        # 나머지 처리를 위한 워커 수 설정
                        try:
                            max_workers = int(input("최대 워커 수를 입력하세요 (기본값: 12): ").strip() or "12")
                            if max_workers <= 0:
                                max_workers = 12
                        except ValueError:
                            max_workers = 12
                            
                        result2 = processor.process_embeddings_batch(remaining_resources, batch_size=10, max_workers=max_workers)
                        # 전체 결과 합계
                        total_result = {
                            'total': result['total'] + result2['total'],
                            'success': result['success'] + result2['success'],
                            'error': result['error'] + result2['error'],
                            'errors': result['errors'] + result2['errors']
                        }
                        processor.display_processing_results(total_result)
            else:
                # 전체 처리
                batch_size = int(input("\n진행상황 표시 단위 (기본값: 10): ").strip() or "10")
                max_workers = int(input("최대 워커 수 (기본값: 12): ").strip() or "12")
                result = processor.process_embeddings_batch(missing_resources, batch_size, max_workers)
                processor.display_processing_results(result)
            
    except Exception as e:
        logger.error(f"임베딩 처리 중 오류 발생: {str(e)}")
        print(f"❌ 오류가 발생했습니다: {str(e)}")


if __name__ == "__main__":
    # 테스트용
    import sys
    
    if len(sys.argv) > 1:
        user_id = int(sys.argv[1])
        process_missing_embeddings_interactive(user_id)
    else:
        print("사용법: python missing_embeddings_processor.py <user_id>")