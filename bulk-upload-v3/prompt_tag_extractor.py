#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import logging
from typing import List, Tuple, Dict, Any

from sqlalchemy import func

# 로컬 모듈 임포트
from manager import CharacterManager, OutfitManager, EventManager
from models import ColorCodeTags
from session_utills import get_session, end_session

class PromptTagExtractor:
    """
    프롬프트에서 태그를 추출하고 분석하는 클래스
    """
    def __init__(self, session=None):
        self.character_manager = CharacterManager()
        self.outfit_manager = OutfitManager()
        self.event_manager = EventManager()
        self.session = session
        self.lora_regex = r'<lora:([^:]+):([0-9.]+)>'  # 로라 태그 정규식

    def extract_tags_from_prompt(self, prompt_text: str) -> Dict[str, List[Tuple[str, str]]]:
        """
        프롬프트 텍스트에서 태그를 추출
        
        Args:
            prompt_text: 분석할 프롬프트 텍스트
            
        Returns:
            Dict: 카테고리별로 분류된 태그 목록
                - characters: 캐릭터 태그 목록 [(별칭, 표준이름)]
                - outfits: 의상 태그 목록 [(별칭, 표준이름)]
                - events: 이벤트/배경 태그 목록 [(별칭, 표준이름)]
                - loras: 로라 태그 목록 [(로라이름, 가중치)]
                - multiple: 여러 인물 감지 여부
                - has_4ground9_character: 4GROUND9 캐릭터 포함 여부
        """
        if not prompt_text:
            return {
                'characters': [],
                'outfits': [],
                'events': [],
                'loras': [],
                'multiple': False,
                'has_4ground9_character': False
            }
            
        # 대소문자 구분 없이 검색하기 위해 소문자 변환
        lower_prompt = prompt_text.lower()
        
        result = {
            'characters': [],
            'outfits': [],
            'events': [],
            'loras': [],
            'multiple': False,
            'has_4ground9_character': False
        }
        
        # 캐릭터 태그 추출
        for standard_name, item in self.character_manager.items.items():
            for alias in item.aliases:
                if alias.lower() in lower_prompt:
                    result['characters'].append((alias, standard_name))
                    result['has_4ground9_character'] = True
                    break
        
        # 의상 태그 추출
        for standard_name, item in self.outfit_manager.items.items():
            for alias in item.aliases:
                if alias.lower() in lower_prompt:
                    result['outfits'].append((alias, standard_name))
                    break
        
        # 이벤트/배경 태그 추출
        for standard_name, item in self.event_manager.items.items():
            for alias in item.aliases:
                if alias.lower() in lower_prompt:
                    result['events'].append((alias, standard_name))
                    break
        
        # 로라 태그 추출
        lora_matches = re.findall(self.lora_regex, prompt_text)
        for model_name, weight in lora_matches:
            result['loras'].append((model_name, weight))
        
        # Multiple 태그 검사
        result['multiple'] = self._check_multiple_characters(lower_prompt)
        
        return result

    def _check_multiple_characters(self, prompt_text: str) -> bool:
        """여러 인물이 존재하는지 확인"""
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
                      
        return is_multiple

    def check_existing_tags(self, extracted_tags: Dict[str, List[Tuple[str, str]]]) -> Dict[str, List[Tuple[str, str, bool]]]:
        """
        추출된 태그 중 이미 데이터베이스에 존재하는 태그 확인
        
        Args:
            extracted_tags: extract_tags_from_prompt()에서 반환된 태그 정보
            
        Returns:
            Dict: 카테고리별로 분류된 태그 목록(존재 여부 추가)
                - characters: 캐릭터 태그 목록 [(별칭, 표준이름, 존재여부)]
                - outfits: 의상 태그 목록 [(별칭, 표준이름, 존재여부)]
                - events: 이벤트/배경 태그 목록 [(별칭, 표준이름, 존재여부)]
                - loras: 로라 태그 목록 [(로라이름, 가중치, 존재여부)]
        """
        if not self.session:
            # 세션이 없으면 모두 존재하지 않는 것으로 가정
            result = {}
            for key, tags in extracted_tags.items():
                if key in ['characters', 'outfits', 'events']:
                    result[key] = [(alias, name, False) for alias, name in tags]
                elif key == 'loras':
                    result[key] = [(name, weight, False) for name, weight in tags]
                else:
                    result[key] = tags
            return result
            
        # 결과 딕셔너리 초기화
        result = {k: [] for k in extracted_tags.keys()}
        result['multiple'] = extracted_tags['multiple']
        result['has_4ground9_character'] = extracted_tags['has_4ground9_character']
        
        try:
            # 각 카테고리별로 태그 존재 여부 확인
            for category in ['characters', 'outfits', 'events']:
                for alias, name in extracted_tags[category]:
                    tag = self.session.query(ColorCodeTags).filter(
                        func.lower(ColorCodeTags.tag) == name.lower()
                    ).first()
                    exists = tag is not None
                    result[category].append((alias, name, exists))
            
            # 로라 태그 확인
            for name, weight in extracted_tags['loras']:
                tag = self.session.query(ColorCodeTags).filter(
                    func.lower(ColorCodeTags.tag) == name.lower()
                ).first()
                exists = tag is not None
                result['loras'].append((name, weight, exists))
            
        except Exception as e:
            print(f"태그 존재 여부 확인 중 오류 발생: {str(e)}")
            
        return result

def analyze_prompt(prompt_text: str, use_db: bool = False) -> Dict[str, Any]:
    """
    프롬프트 텍스트를 분석하여 태그 정보 반환
    
    Args:
        prompt_text: 분석할 프롬프트 텍스트
        use_db: 데이터베이스 연결 사용 여부
        
    Returns:
        Dict: 추출된 태그 정보
    """
    session, server = None, None
    
    try:
        extractor = None
        
        if use_db:
            # 데이터베이스 연결
            session, server = get_session()
            extractor = PromptTagExtractor(session)
        else:
            extractor = PromptTagExtractor()
        
        # 태그 추출
        extracted_tags = extractor.extract_tags_from_prompt(prompt_text)
        
        # 데이터베이스 연결 시 태그 존재 여부 확인
        if use_db:
            extracted_tags = extractor.check_existing_tags(extracted_tags)
            
        return extracted_tags
        
    except Exception as e:
        print(f"프롬프트 분석 중 오류 발생: {str(e)}")
        return {
            'characters': [],
            'outfits': [],
            'events': [],
            'loras': [],
            'multiple': False,
            'has_4ground9_character': False,
            'error': str(e)
        }
    finally:
        if session and server:
            end_session(session, server)

def display_extracted_tags(extracted_tags: Dict[str, Any]) -> None:
    """
    추출된 태그 정보를 화면에 출력
    
    Args:
        extracted_tags: analyze_prompt()에서 반환된 태그 정보
    """
    print("\n===== 태그 분석 결과 =====")
    
    # 카테고리별 태그 출력 함수
    def print_category(category_name, tags):
        if not tags:
            print(f"\n{category_name}: 없음")
            return
            
        print(f"\n{category_name}:")
        for idx, item in enumerate(tags, 1):
            if len(item) == 3:  # (별칭, 표준이름, 존재여부)
                alias, name, exists = item
                exists_str = "✓" if exists else "✗"
                print(f"{idx}. {name} (매칭: {alias}) [{exists_str}]")
            elif len(item) == 2:  # (별칭, 표준이름) 또는 (로라이름, 가중치)
                if category_name == "로라 태그":
                    name, weight = item
                    print(f"{idx}. {name} (가중치: {weight})")
                else:
                    alias, name = item
                    print(f"{idx}. {name} (매칭: {alias})")
    
    # 각 카테고리 출력
    print_category("캐릭터 태그", extracted_tags.get('characters', []))
    print_category("의상 태그", extracted_tags.get('outfits', []))
    print_category("이벤트/배경 태그", extracted_tags.get('events', []))
    print_category("로라 태그", extracted_tags.get('loras', []))
    
    # 특수 태그 정보
    print("\n특수 태그:")
    if extracted_tags.get('multiple', False):
        print("- Multiple 태그 추가 예정 (여러 인물 감지됨)")
    if extracted_tags.get('has_4ground9_character', False):
        print("- 4GROUND9 태그 추가 예정 (캐릭터 감지됨)")
    
    print("\n참고: [✓] 이미 존재하는 태그, [✗] 새로 생성될 태그")
    print("==========================")

def main():
    """메인 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n===== 프롬프트 태그 추출기 =====")
    print("프롬프트에서 태그를 추출하고 분석합니다.")
    
    # 데이터베이스 연결 여부 선택
    use_db = input("\n데이터베이스에 연결하여 태그 존재 여부를 확인하시겠습니까? (y/n): ").strip().lower() == 'y'
    
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

if __name__ == "__main__":
    main()