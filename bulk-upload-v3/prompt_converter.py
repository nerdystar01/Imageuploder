# Standard Library
import os
import sys
import logging
from typing import List, Tuple
import re
import threading
import time
import itertools
import sys

# Third Party Libraries
from tqdm import tqdm
from sshtunnel import SSHTunnelForwarder
from sqlalchemy.orm import Session, scoped_session, sessionmaker

# Local Imports
from models import (
    setup_database_engine,
    Resource,
    User,
    ColorCodeTags
)
from tag_mappings import CharacterManager, OutfitManager, EventManager
from concurrent.futures import ThreadPoolExecutor


from sqlalchemy.orm import Session
from models import ColorCodeTags
from tag_mappings import CharacterManager

class TagExtensions:
    def __init__(self, session, character_manager):
        self.session = session
        self.character_manager = character_manager
        self.lora_regex = r'<lora:([^:]+):([0-9.]+)>' # 로라 정규식

    def convert_tags(self, resource, from_tag_id: int, to_tag_id: int) -> None:
        """특정 태그를 다른 태그로 전환합니다."""
        try:
            # 태그 존재 여부 확인
            from_tag = self.session.query(ColorCodeTags).filter_by(id=from_tag_id).first()
            to_tag = self.session.query(ColorCodeTags).filter_by(id=to_tag_id).first()
            
            if not from_tag or not to_tag:
                print(f"태그를 찾을 수 없음: from_id={from_tag_id}, to_id={to_tag_id}")
                return

            # 리소스의 현재 태그에서 전환 대상 태그 확인
            if from_tag in resource.tags:
                print(f"태그 전환: {from_tag.tag}(ID:{from_tag_id}) -> {to_tag.tag}(ID:{to_tag_id})")
                resource.tags.remove(from_tag)
                if to_tag not in resource.tags:
                    resource.tags.append(to_tag)
                self.session.commit()
                    
        except Exception as e:
            print(f"태그 전환 중 오류 발생: {str(e)}")
            self.session.rollback()
    
    def check_multiple_characters(self, prompt_text: str, resource, added_tag_ids: set) -> None:
        """여러 인물이 존재하는 경우 multiple 태그를 추가합니다.
        다음과 같은 경우에 multiple로 처리:
        1. boy와 girl이 동시에 존재하는 경우
        2. 2명 이상의 boy가 존재하는 경우 (예: 2boys, 3 boys)
        3. 2명 이상의 girl이 존재하는 경우 (예: 2girls, 3 girls)
        """
        import re

        # 프롬프트를 소문자로 변환
        prompt_text = prompt_text.lower()

        # boy/girl 패턴 정의
        boy_patterns = [
            r'\d+\s*boys?[,\s]',  # '1boy,', '2 boy,', '3boys,', '3 boys ' 등
            r'\bboys[,\s]'        # 'boys,' - 복수형만
        ]
        
        girl_patterns = [
            r'\d+\s*girls?[,\s]',  # '1girl,', '2 girl,', '3girls,', '3 girls ' 등
            r'\bgirls[,\s]'        # 'girls,' - 복수형만
        ]

        # 숫자 + boy/girl 패턴에서 숫자 추출
        def extract_number(text, patterns):
            all_matches = []
            for pattern in patterns:
                matches = re.finditer(pattern, text)
                for match in matches:
                    matched_text = match.group()
                    # 숫자 추출 시도
                    number_match = re.search(r'\d+', matched_text)
                    if number_match:
                        all_matches.append(int(number_match.group()))
                    # 'boys' or 'girls'로 끝나는 경우 2로 처리
                    elif matched_text.strip('[], ').endswith('s'):
                        all_matches.append(2)
            return max(all_matches) if all_matches else 0

        boy_count = extract_number(prompt_text, boy_patterns)
        girl_count = extract_number(prompt_text, girl_patterns)

        # 단순 존재 여부 체크 (1인 경우)
        has_single_boy = bool(re.search(r'\b1\s*boy[,\s]|\bboy[,\s]', prompt_text))
        has_single_girl = bool(re.search(r'\b1\s*girl[,\s]|\bgirl[,\s]', prompt_text))

        # Multiple 조건 체크:
        # 1. boy나 girl 중 하나라도 2명 이상
        # 2. boy와 girl이 각각 1명 이상 존재
        is_multiple = (boy_count >= 2 or girl_count >= 2 or 
                    (has_single_boy and (has_single_girl or girl_count > 0)) or
                    (has_single_girl and (has_single_boy or boy_count > 0)))

        if is_multiple:
            try:
                multiple_tag = self.session.query(ColorCodeTags).filter_by(tag='Multiple').first()
                if multiple_tag and multiple_tag.id not in added_tag_ids:
                    condition = []
                    if boy_count >= 2 or has_single_boy:
                        condition.append(f"{boy_count if boy_count >= 2 else 1} boy(s)")
                    if girl_count >= 2 or has_single_girl:
                        condition.append(f"{girl_count if girl_count >= 2 else 1} girl(s)")
                    
                    print(f"Multiple 태그 추가 - 발견된 인물: {' and '.join(condition)}")
                    resource.tags.append(multiple_tag)
                    added_tag_ids.add(multiple_tag.id)
                    self.session.commit()
            except Exception as e:
                print(f"Multiple 태그 추가 중 오류 발생: {str(e)}")
                self.session.rollback()

    def check_manage_4ground9_tag(self, prompt_text: str, resource) -> None:
        """캐릭터 관련 태그 유무에 따라 4GROUND9 태그를 관리합니다.
        캐릭터 태그가 있으면 4GROUND9를 추가하고, 없으면 삭제합니다."""
        try:
            prompt_text = prompt_text.lower()
            has_character = False

            # 각 캐릭터의 별칭을 확인
            for character_name, character_item in self.character_manager.items.items():
                # 해당 캐릭터의 모든 별칭에 대해 검사
                for alias in character_item.aliases:
                    if alias.lower() in prompt_text:
                        has_character = True
                        print(f"캐릭터 발견: {character_name} (alias: {alias})")
                        break
                if has_character:
                    break

            # 4GROUND9 태그 찾기
            ground9_tag = self.session.query(ColorCodeTags).filter_by(tag='4GROUND9').first()
            
            if has_character:
                # 캐릭터가 있을 경우 태그 추가
                if ground9_tag and ground9_tag not in resource.tags:
                    print(f"캐릭터 관련 내용 있음 - 4GROUND9 태그 추가")
                    resource.tags.append(ground9_tag)
                    self.session.commit()
            else:
                # 캐릭터가 없을 경우 태그 삭제
                if ground9_tag and ground9_tag in resource.tags:
                    print(f"캐릭터 관련 내용 없음 - 4GROUND9 태그 삭제")
                    resource.tags.remove(ground9_tag)
                    self.session.commit()

        except Exception as e:
            print(f"4GROUND9 태그 처리 중 오류 발생: {str(e)}")
            self.session.rollback()

    def check_lora_tag(self, prompt_text: str, resource, added_tag_ids: set) -> None:
        if not prompt_text:
            return

        try:
            lora_matches = re.findall(self.lora_regex, prompt_text)
            if not lora_matches:
                return
                
            print(f"\n로라 태그 추출 결과: {lora_matches}")
            
            current_tags = {tag.tag for tag in resource.tags}
            
            for model_name, weight in lora_matches:
                try:
                    # 여기서 직접 session을 사용해야 함
                    tag = self.session.query(ColorCodeTags).filter_by(tag=model_name).first()
                    if tag is None:
                        tag = ColorCodeTags(
                            tag=model_name,
                            color_code='#FFFFFF'
                        )
                        self.session.add(tag)
                        self.session.commit()
                        print(f"새로운 태그 생성됨: {model_name}")
                    
                    if tag.id not in added_tag_ids:
                        print(f"로라 태그 추가: {model_name} (ID: {tag.id})")
                        resource.tags.append(tag)
                        added_tag_ids.add(tag.id)
                    else:
                        print(f"로라 태그 중복 건너뛰기: {model_name}")
                            
                except Exception as e:
                    print(f"태그 생성/조회 중 오류 발생: {str(e)}")
                    self.session.rollback()
                    continue

            self.session.commit()
                
        except Exception as e:
            print(f"로라 태그 처리 중 오류 발생: {str(e)}")
            self.session.rollback()

class Converter:
    def __init__(self, extension_options=None):
        self.character_manager = CharacterManager()
        self.outfit_manager = OutfitManager()
        self.event_manager = EventManager()
        self.server = None
        self.extension_options = extension_options or {
            'use_multiple_tag': False,
            'check_4ground9': False,
            'convert_tags': False,
            'from_tag_id': None,
            'to_tag_id': None
        }

    def _process_single_resource(self, session: Session, resource: Resource, prompt_text: str) -> int:
        print(f"\n리소스 ID {resource.id} 처리 시작")
        
        converted_count = 0
        added_tag_ids = {tag.id for tag in resource.tags}
        
        try:
            tag_extensions = TagExtensions(session, self.character_manager)
            
            managers = [
                (self.character_manager, "캐릭터"),
                (self.outfit_manager, "의상"),
                (self.event_manager, "이벤트/배경")
            ]
            
            for manager, category in managers:
                count = self.process_with_manager(
                    session, resource, prompt_text, 
                    added_tag_ids, manager
                )
                print(f"{category} 태그 처리 결과: {count}개")
                converted_count += count
            
            # 설정된 익스텐션 옵션에 따라 처리
            if self.extension_options['use_multiple_tag']:
                tag_extensions.check_multiple_characters(prompt_text, resource, added_tag_ids)
            
            if self.extension_options['check_4ground9']:
                tag_extensions.check_manage_4ground9_tag(prompt_text, resource)
            
            if self.extension_options['convert_tags']:
                tag_extensions.convert_tags(
                    resource, 
                    self.extension_options['from_tag_id'],
                    self.extension_options['to_tag_id']
                )
            
            session.commit()
            print(f"리소스 {resource.id}에 총 {converted_count}개 태그 추가됨")
            return converted_count
            
        except Exception as e:
            print(f"태그 처리 중 오류 발생: {str(e)}")
            session.rollback()
            raise
        
    def start_ssh_tunnel(self):
        try:
            self.server = SSHTunnelForwarder(
                ('34.64.105.81', 22),
                ssh_username='nerdystar',
                ssh_pkey='./wcidfu-ssh',
                remote_bind_address=('10.1.31.44', 5432),
                set_keepalive=60
            )
            self.server.start()
            logging.info("SSH tunnel established")
            return self.server
        except Exception as e:
            logging.error(f"Error establishing SSH tunnel: {str(e)}")
            raise
            
    def stop_ssh_tunnel(self):
        if self.server:
            self.server.stop()
            logging.info("SSH tunnel closed")

    def get_session(self):
        server = self.start_ssh_tunnel()
        engine = setup_database_engine("nerdy@2024", server.local_bind_port)
        session_factory = sessionmaker(bind=engine)
        session = scoped_session(session_factory)
        return session, server
        
    def _get_or_create_tag(self, session: Session, tag_name: str) -> ColorCodeTags:
        """주어진 태그 이름으로 태그를 조회하거나 없으면 새로 생성합니다."""
        try:
            tag = session.query(ColorCodeTags).filter_by(tag=tag_name).first()
            if tag is None:
                tag = ColorCodeTags(
                    tag=tag_name,
                    color_code='#FFFFFF'
                )
                session.add(tag)
                session.commit()
                logging.info(f"새로운 태그 생성됨: {tag_name}")
            return tag
            
        except Exception as e:
            session.rollback()
            logging.error(f"태그 생성/조회 중 오류 발생: {str(e)}")
            raise

    def process_with_manager(
        self, session: Session, resource: Resource, 
        prompt_text: str, added_tag_ids: set, manager
    ) -> int:
        converted_count = 0
        prompt_text = prompt_text.lower()
        
        current_tags = {tag.tag for tag in resource.tags}
        
        for standard_name, item in manager.items.items():
            for alias in item.aliases:
                if alias.lower() in prompt_text:
                    # 이미 존재하는 태그인지 확인
                    if standard_name in current_tags:
                        print(f"태그 건너뛰기 (이미 존재): {standard_name}")
                        break
                        
                    print(f"매칭된 태그: {alias} -> {standard_name}")
                    try:
                        tag = self._get_or_create_tag(session, standard_name)
                        resource.tags.append(tag)
                        added_tag_ids.add(tag.id)
                        converted_count += 1
                        print(f"태그 추가됨: {standard_name}")
                        session.commit()
                    except Exception as e:
                        print(f"태그 처리 중 오류 발생: {str(e)}")
                        session.rollback()
                    break
        
        return converted_count

    def loading_animation(self, stop_event):
        """로딩 애니메이션을 표시하는 함수"""
        spinner = itertools.cycle(['', '.', '..', '...'])
        while not stop_event.is_set():
            sys.stdout.write('\r리소스 데이터를 불러오는 중' + next(spinner))
            sys.stdout.flush()
            time.sleep(0.5)


    def process_resources(self, session: Session, start_id: int = None, end_id: int = None):
        """지정된 범위의 리소스들의 프롬프트를 처리합니다."""
        try:
            # 리소스 쿼리 구성
            query = session.query(Resource)
            if start_id is not None:
                query = query.filter(Resource.id >= start_id)
            if end_id is not None:
                query = query.filter(Resource.id <= end_id)
                    
            total_resources = query.count()
            print(f"\n총 {total_resources}개의 리소스를 처리합니다.")
            
            stop_animation = threading.Event()
            animation_thread = threading.Thread(target=self.loading_animation, args=(stop_animation,))
            animation_thread.start()

            try:
                resources = query.all()
            finally:
                stop_animation.set()
                animation_thread.join()
                print('\n데이터 로딩 완료')

            # 세션 팩토리 생성
            Session = sessionmaker(bind=session.get_bind())

            def process_resource(resource):
                """각 리소스를 처리하는 함수"""
                if not resource.prompt:
                    return 0
                    
                # 각 쓰레드마다 새로운 세션 생성
                thread_session = Session()
                try:
                    # 리소스 재조회 (새로운 세션에서)
                    resource = thread_session.merge(resource)
                    converted = self._process_single_resource(
                        session=thread_session,
                        resource=resource,
                        prompt_text=resource.prompt
                    )
                    thread_session.commit()
                    return converted or 0
                except Exception as e:
                    logging.error(f"리소스 {resource.id} 처리 중 오류 발생: {str(e)}")
                    thread_session.rollback()
                    return 0
                finally:
                    thread_session.close()

            total_converted = 0
            with ThreadPoolExecutor(max_workers=12) as executor:
                # tqdm으로 진행상황 표시
                futures = list(tqdm(
                    executor.map(process_resource, resources),
                    total=len(resources),
                    desc="리소스 처리 중"
                ))
                total_converted = sum(filter(None, futures))

            print(f"\n처리 완료: 총 {total_converted}개의 태그가 추가되었습니다.")

        except Exception as e:
            logging.error(f"리소스 처리 중 오류 발생: {str(e)}")
            print(f"에러 발생: {str(e)}")
            raise

def get_user_input() -> Tuple[int, int]:
    """시작 ID와 종료 ID를 입력받습니다."""
    try:
        start_id = input("시작 리소스 ID를 입력하세요 (전체 처리시 엔터): ").strip()
        end_id = input("종료 리소스 ID를 입력하세요 (전체 처리시 엔터): ").strip()
        
        start_id = int(start_id) if start_id else None
        end_id = int(end_id) if end_id else None
        
        return start_id, end_id
        
    except ValueError:
        print("올바른 숫자를 입력해주세요.")
        sys.exit(1)

def get_extension_options(session: Session) -> dict:
    options = {}
    
    print("\n=== 태그 익스텐션 설정 ===")
    
    # Multiple 태그 옵션
    options['use_multiple_tag'] = input(
        "boy/girl 동시 존재시 Multiple 태그를 추가하시겠습니까? (y/n): "
    ).strip().lower() == 'y'
    
    # 4GROUND9 태그 옵션
    options['check_4ground9'] = input(
        "캐릭터 태그가 없을 때 4GROUND9 태그를 제거하시겠습니까? (y/n): "
    ).strip().lower() == 'y'
    
    # 태그 전환 옵션들
    print("\n=== 태그 전환 설정 ===")
    print("태그 전환 쌍을 입력하세요. 종료하려면 엔터를 입력하세요.")
    
    options['convert_tags'] = False  # 기본값 설정
    options['from_tag_id'] = None
    options['to_tag_id'] = None
    
    from_id = input("\n전환할 태그 ID (종료하려면 엔터): ").strip()
    if from_id:
        to_id = input("새로운 태그 ID: ").strip()
        try:
            from_tag_id = int(from_id)
            to_tag_id = int(to_id)
            
            # 태그 존재 여부 검증
            from_tag = session.query(ColorCodeTags).filter_by(id=from_tag_id).first()
            to_tag = session.query(ColorCodeTags).filter_by(id=to_tag_id).first()
            
            if not from_tag:
                print(f"전환할 태그 ID {from_tag_id}가 존재하지 않습니다.")
            elif not to_tag:
                print(f"새로운 태그 ID {to_tag_id}가 존재하지 않습니다.")
            else:
                options['convert_tags'] = True
                options['from_tag_id'] = from_tag_id
                options['to_tag_id'] = to_tag_id
                print(f"태그 전환 추가됨: {from_tag.tag}({from_tag_id}) -> {to_tag.tag}({to_tag_id})")
                
        except ValueError:
            print("올바른 태그 ID를 입력해주세요.")
    
    return options

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # SSH 터널과 세션 생성은 한 번만
    converter = None
    session = None
    server = None
    
    try:
        start_id, end_id = get_user_input()
        
        print("\n처리 정보:")
        print(f"시작 ID: {start_id if start_id else '처음부터'}")
        print(f"종료 ID: {end_id if end_id else '끝까지'}")

        # Converter 인스턴스 생성
        converter = Converter()
        
        # 세션 생성
        session, server = converter.get_session()
        
        # 태그 익스텐션 옵션 설정
        extension_options = get_extension_options(session)
        
        print("\n=== 설정된 옵션 ===")
        print(f"Multiple 태그 추가: {'예' if extension_options['use_multiple_tag'] else '아니오'}")
        print(f"4GROUND9 태그 검사: {'예' if extension_options['check_4ground9'] else '아니오'}")
        print(f"태그 전환: {'예' if extension_options['convert_tags'] else '아니오'}")
        if extension_options['convert_tags']:
            print(f"- 전환: {extension_options['from_tag_id']} -> {extension_options['to_tag_id']}")
        
        confirm = input("\n위 설정으로 처리를 시작하시겠습니까? (y/n): ").strip().lower()
        if confirm != 'y':
            print("프로그램을 종료합니다.")
            return
        
        converter.extension_options = extension_options
        converter.process_resources(session=session, start_id=start_id, end_id=end_id)
        
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")
    except Exception as e:
        logging.error(f"처리 중 오류가 발생했습니다: {str(e)}")
    finally:
        if session:
            session.remove()
        if server:
            server.stop()
    
if __name__ == "__main__":
    main()