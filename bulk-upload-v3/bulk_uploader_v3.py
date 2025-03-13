# Standard Library
import os
import sys
import io
import logging
import re
from typing import Tuple, Dict, Any, List
import time
import functools
from ssl import SSLError
import psycopg2


# Third Party Libraries
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, PngImagePlugin
import piexif
import piexif.helper
from tqdm import tqdm
from google.cloud import storage
from google.oauth2 import service_account

# Database
from sqlalchemy.orm import Session


# Local Imports
from models import (
    setup_database_engine,
    Resource,
    User,
    ColorCodeTags,
    SdModel
)
from manager import CharacterManager, OutfitManager, EventManager

from session_utills import get_session, end_session, check_connection, upload_to_bucket, upload_image_to_gcp_bucket

def retry_on_connection_error(max_retries=3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 세션 객체 가져오기 (self에서)
            session = kwargs.get('session', None)
            if not session and args and isinstance(args[0], Session):
                session = args[0]
                
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except (psycopg2.OperationalError, SSLError) as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"Connection error: {str(e)}. Retrying... ({attempt + 1}/{max_retries})")
                        # 연결 재시도
                        time.sleep(5)
                    else:
                        logging.error(f"Connection failed after {max_retries} attempts")
                        raise
        return wrapper
    return decorator

# ------------------------------
#  Png Utill
# ------------------------------
class PngUtill:
    def read_info_from_image(self, image: Image.Image):
        IGNORED_INFO_KEYS = {
            'jfif', 'jfif_version', 'jfif_unit', 'jfif_density', 'dpi', 'exif',
            'loop', 'background', 'timestamp', 'duration', 'progressive', 'progression',
            'icc_profile', 'chromaticity', 'photoshop',
        }
        
        items = (image.info or {}).copy()
        geninfo = items.pop('parameters', None)
    
        if "exif" in items:
            exif_data = items.pop("exif")
            try:
                exif = piexif.load(exif_data)
            except OSError:
                exif = None
            exif_comment = (exif or {}).get("Exif", {}).get(piexif.ExifIFD.UserComment, b'')
            try:
                exif_comment = piexif.helper.UserComment.load(exif_comment)
            except ValueError:
                exif_comment = exif_comment.decode('utf8', errors="ignore")

            if exif_comment:
                items['exif comment'] = exif_comment
                geninfo = exif_comment
        
        elif "comment" in items: # for gif
            geninfo = items["comment"].decode('utf8', errors="ignore")

        for field in IGNORED_INFO_KEYS:
            items.pop(field, None)

        
        return geninfo

    # def parse_generation_parameters(self, x: str):
    #     res = {}
    #     lines = x.strip().split("\n")  # 입력된 문자열을 줄 단위로 분리

    #     for i, line in enumerate(lines):  # 각 줄과 그 인덱스에 대해 반복
    #         line = line.strip()  # 현재 줄의 앞뒤 공백 제거
    #         if i == 0:  # 첫 번째 줄인 경우
    #             res["Prompt"] = line
    #         elif i == 1 and line.startswith("Negative prompt:"):  # 두 번째 줄이며 "Negative prompt:"로 시작하는 경우
    #             res["Negative prompt"] = line[16:].strip()
    #         elif i == 2:  # 세 번째 줄인 경우, 옵션들을 처리
    #             # 여기에서 각 키-값에 대한 매칭 작업을 수행합니다.
    #             keys = [
    #                 "Steps", "Sampler", "CFG scale", "Seed", "Size", 
    #                 "Model hash", "Model", "VAE hash", "VAE", 
    #                 "Denoising strength", "Clip skip", "Hires upscale",
    #                 "Hires upscaler", 
    #             ]
    #             for key in keys:
    #                 # 정규 표현식을 사용하여 각 키에 해당하는 값을 찾습니다.
    #                 match = re.search(fr'{key}: ([^,]+),', line)
    #                 if match:
    #                     # 찾은 값은 그룹 1에 있습니다.
    #                     value = match.group(1).strip()
    #                     res[key] = value
                
    #             controlnet_patterns = re.findall(r'ControlNet \d+: "(.*?)"', line, re.DOTALL)
    #             for idx, cn_content in enumerate(controlnet_patterns):
    #                 # ControlNet 내부의 키-값 쌍을 추출합니다.
    #                 cn_dict = {}
    #                 cn_pairs = re.findall(r'(\w+): ([^,]+)', cn_content)
    #                 for key, value in cn_pairs:
    #                     cn_dict[key.strip()] = value.strip()
    #                 res[f"ControlNet {idx}"] = cn_dict

    #     return res
    def parse_generation_parameters(x: str):
        """
        스테이블 디퓨전 생성 파라미터를 파싱합니다.
        네거티브 프롬프트를 기준으로 프롬프트와 파라미터를 분리합니다.
        
        Args:
            x (str): 파싱할 생성 파라미터 문자열
            
        Returns:
            dict: 파싱된 파라미터를 담은 딕셔너리
        """
        import re
        
        res = {}
        
        # 네거티브 프롬프트 위치 찾기
        neg_prompt_pattern = r'Negative prompt:'
        neg_prompt_match = re.search(neg_prompt_pattern, x)
        
        if neg_prompt_match:
            # 네거티브 프롬프트 시작 위치
            neg_start = neg_prompt_match.start()
            
            # 프롬프트 추출 (네거티브 프롬프트 이전 텍스트)
            prompt = x[:neg_start].strip()
            res["Prompt"] = prompt
            
            # 네거티브 프롬프트 이후 텍스트 가져오기
            remaining_text = x[neg_start:]
            
            # 네거티브 프롬프트와 파라미터 분리
            # 첫 번째 쉼표+공백 기준으로 나누기 (예: "Steps: 32")
            params_pattern = r'Steps:'
            params_match = re.search(params_pattern, remaining_text)
            
            if params_match:
                params_start = params_match.start()
                
                # 네거티브 프롬프트 추출
                neg_prompt = remaining_text[:params_start].replace('Negative prompt:', '', 1).strip()
                res["Negative prompt"] = neg_prompt
                
                # 파라미터 추출
                params_text = remaining_text[params_start:]
                
                # 주요 파라미터 추출
                # 추출할 주요 파라미터
                keys = [
                    "Steps", "Sampler", "CFG scale", "Seed", "Size", 
                    "Model hash", "Model", "VAE hash", "VAE", 
                    "Denoising strength", "Clip skip", "Hires upscale",
                    "Hires upscaler", "Schedule type"
                ]
                
                # 각 파라미터 추출
                for key in keys:
                    # 정규식을 사용하여 파라미터 찾기
                    # 패턴 1: "키: 값," 형태 (쉼표로 끝나는 경우)
                    pattern1 = fr'{re.escape(key)}: ([^,]+),'
                    match1 = re.search(pattern1, params_text)
                    
                    if match1:
                        value = match1.group(1).strip()
                        res[key] = value
                        continue
                        
                    # 패턴 2: "키: 값" 형태 (줄 끝이나 문자열 끝에 있는 경우)
                    pattern2 = fr'{re.escape(key)}: ([^\n,]+)(?:\n|$)'
                    match2 = re.search(pattern2, params_text)
                    
                    if match2:
                        value = match2.group(1).strip()
                        res[key] = value
                
                # ControlNet 관련 패턴 추출
                controlnet_patterns = re.findall(r'ControlNet \d+: "(.*?)"', params_text, re.DOTALL)
                for idx, cn_content in enumerate(controlnet_patterns):
                    # ControlNet 내부의 키-값 쌍을 추출
                    cn_dict = {}
                    cn_pairs = re.findall(r'(\w+): ([^,]+)', cn_content)
                    for key, value in cn_pairs:
                        cn_dict[key.strip()] = value.strip()
                    res[f"ControlNet {idx}"] = cn_dict
                
                # Lora 해시 추출
                lora_hash_match = re.search(r'Lora hashes: "(.*?)"', params_text)
                if lora_hash_match:
                    res["Lora hashes"] = lora_hash_match.group(1).strip()
                    
            else:
                # Steps가 없는 경우 전체를 네거티브 프롬프트로 처리
                res["Negative prompt"] = remaining_text.replace('Negative prompt:', '', 1).strip()
        else:
            # 네거티브 프롬프트가 없는 경우
            # Steps나 다른 파라미터 찾기
            params_match = re.search(r'Steps:', x)
            
            if params_match:
                params_start = params_match.start()
                
                # 프롬프트 추출
                prompt = x[:params_start].strip()
                res["Prompt"] = prompt
                
                # 파라미터 추출
                params_text = x[params_start:]
                
                # 주요 파라미터 추출
                keys = [
                    "Steps", "Sampler", "CFG scale", "Seed", "Size", 
                    "Model hash", "Model", "VAE hash", "VAE", 
                    "Denoising strength", "Clip skip", "Hires upscale",
                    "Hires upscaler", "Schedule type"
                ]
                
                # 각 파라미터 추출
                for key in keys:
                    # 정규식을 사용하여 파라미터 찾기
                    # 패턴 1: "키: 값," 형태 (쉼표로 끝나는 경우)
                    pattern1 = fr'{re.escape(key)}: ([^,]+),'
                    match1 = re.search(pattern1, params_text)
                    
                    if match1:
                        value = match1.group(1).strip()
                        res[key] = value
                        continue
                        
                    # 패턴 2: "키: 값" 형태 (줄 끝이나 문자열 끝에 있는 경우)
                    pattern2 = fr'{re.escape(key)}: ([^\n,]+)(?:\n|$)'
                    match2 = re.search(pattern2, params_text)
                    
                    if match2:
                        value = match2.group(1).strip()
                        res[key] = value
                
                # ControlNet 관련 패턴 추출
                controlnet_patterns = re.findall(r'ControlNet \d+: "(.*?)"', params_text, re.DOTALL)
                for idx, cn_content in enumerate(controlnet_patterns):
                    # ControlNet 내부의 키-값 쌍을 추출
                    cn_dict = {}
                    cn_pairs = re.findall(r'(\w+): ([^,]+)', cn_content)
                    for key, value in cn_pairs:
                        cn_dict[key.strip()] = value.strip()
                    res[f"ControlNet {idx}"] = cn_dict
                
                # Lora 해시 추출
                lora_hash_match = re.search(r'Lora hashes: "(.*?)"', params_text)
                if lora_hash_match:
                    res["Lora hashes"] = lora_hash_match.group(1).strip()
            else:
                # 파라미터가 없는 경우 전체를 프롬프트로 처리
                res["Prompt"] = x.strip()
        
        return res

    def geninfo_params(self, image):
        try:
            geninfo = self.read_info_from_image(image)
            if geninfo == None:
                params = None
                
                return geninfo, params
            else:
                params = self.parse_generation_parameters(geninfo)
            return geninfo, params
        except Exception as e:
            print("Error:", str(e))

    def scale_image_by_height(self, original_image, height):
        aspect_ratio = original_image.width / original_image.height
        new_width = int(height * aspect_ratio)
        resized_image = original_image.resize((new_width, height))
        image_bytes = io.BytesIO()
        resized_image.save(image_bytes, format='PNG')
        image_bytes.seek(0)
        return Image.open(image_bytes)

    def create_image_scales(self, image_path, heights=(128, 512)):
        original_image = Image.open(image_path)
        resized_images = {height: self.scale_image_by_height(original_image, height) for height in heights}
        return original_image, resized_images[128], resized_images[512]

# ------------------------------
#  PromptParser
# ------------------------------
class PromptParser:
    def __init__(self):
        self.tag_mapping = create_tag_mapping()
        # Lora 태그를 찾기 위한 정규식 패턴
        self.lora_regex = r'<lora:([^:]+):([0-9.]+)>'
        self.added_tag_ids = set()

    def _get_or_create_tag(self, session: Session, tag_name: str) -> ColorCodeTags:
        """
        주어진 태그 이름으로 태그를 조회하거나 없으면 새로 생성합니다.
        """
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

    def _extract_lora_tags(self, prompt_text: str) -> List[Tuple[str, float]]:
        """
        프롬프트 텍스트에서 모든 Lora 태그와 가중치를 추출합니다.
        """
        matches = re.findall(self.lora_regex, prompt_text)
        return [(model, float(weight)) for model, weight in matches]
    
    @retry_on_connection_error()
    def _process_single_resource(self, session: Session, resource: Resource, prompt_text: str) -> int:
        """
        단일 리소스의 프롬프트를 처리하고 태그를 추가합니다.
        """
        print(f"\n리소스 ID {resource.id} 처리 시작")
        print(f"프롬프트: {prompt_text[:100]}...")
        
        converted_count = 0
        added_tag_ids = set()  # 이미 추가된 태그 ID를 추적
        
        # 기존 태그 매핑 처리
        for search_term, tag_name in self.tag_mapping.items():
            if search_term.lower() in prompt_text.lower():
                print(f"매칭된 검색어: {search_term} -> 태그: {tag_name}")
                converted_tag = self._get_or_create_tag(session, tag_name)
                if converted_tag and converted_tag.id not in added_tag_ids:
                    print(f"태그 추가: {tag_name} (ID: {converted_tag.id})")
                    resource.tags.append(converted_tag)
                    added_tag_ids.add(converted_tag.id)
                    converted_count += 1
                else:
                    print(f"태그 중복 건너뛰기: {tag_name}")
        
        # Lora 태그 처리
        try:
            lora_count = self._process_lora_tags(session, resource, prompt_text, added_tag_ids)
            print(f"Lora 태그 처리 결과: {lora_count}개")
            converted_count += lora_count
            
            print(f"리소스 {resource.id}에 총 {converted_count}개 태그 추가됨")
            session.flush()
            return converted_count
        except Exception as e:
            print(f"태그 처리 중 오류 발생: {str(e)}")
            raise

    def _process_lora_tags(self, session: Session, resource: Resource, prompt_text: str, added_tag_ids: set) -> int:
        """
        프롬프트 텍스트에서 Lora 태그를 처리하고 리소스에 태그를 추가합니다.
        """
        if not prompt_text:
            return 0
            
        converted_count = 0
        lora_tags = self._extract_lora_tags(prompt_text)
        print(f"\nLora 태그 추출 결과: {lora_tags}")
        
        for model_name, weight in lora_tags:
            if model_name.lower() in self.tag_mapping:
                tag_name = self.tag_mapping[model_name.lower()]
                print(f"Lora 매핑: {model_name} -> {tag_name}")
            else:
                tag_name = model_name
                print(f"Lora 직접 사용: {model_name}")
            
            base_tag = self._get_or_create_tag(session, tag_name)
            if base_tag and base_tag.id not in added_tag_ids:
                print(f"Lora 태그 추가: {tag_name} (ID: {base_tag.id})")
                resource.tags.append(base_tag)
                added_tag_ids.add(base_tag.id)
                converted_count += 1
            else:
                print(f"Lora 태그 중복 건너뛰기: {tag_name}")
        
        return converted_count

    def process_resources(self, session: Session, resources: List[Resource], prompt_field: str = 'prompt') -> int:
        """
        여러 리소스의 프롬프트를 처리하고 태그를 추가합니다.
        """
        total_converted = 0
        
        for resource in resources:
            prompt_text = getattr(resource, prompt_field, '')
            if prompt_text:
                total_converted += self._process_single_resource(session, resource, prompt_text)
        
        return total_converted

# ------------------------------
#  New Resource
# ------------------------------
class CreateResource:
    def __init__(self):
        pass

    def create_resource(self, user_id: int, original_image: Image.Image, 
                       image_128: Image.Image, image_512: Image.Image, 
                       session: Session) -> Resource:
        """Create a new resource with uploaded images
        
        Args:
            user_id: User ID for the resource
            original_image: Original PIL image
            image_128: Thumbnail image (128px)
            image_512: Thumbnail image (512px)
            session: Database session
            
        Returns:
            Resource: Created resource object
        """
        try:
            # Create new resource
            new_resource = Resource(user_id=user_id)
            session.add(new_resource)
            session.flush()  # Get the ID without committing
            
            # Upload images
            try:
                self._upload_images(new_resource, original_image, image_128, image_512)
                session.commit()
                return new_resource
            except Exception as e:
                session.rollback()
                logging.error(f"Failed to upload images: {str(e)}")
                raise

        except Exception as e:
            session.rollback()
            logging.error(f"Failed to create resource: {str(e)}")
            raise
    
    def _upload_images(self, resource: Resource, original_image: Image.Image,
                      image_128: Image.Image, image_512: Image.Image) -> None:
        """Upload original and thumbnail images to storage
        
        Args:
            resource: Resource object to update
            original_image: Original PIL image
            image_128: Thumbnail image (128px)
            image_512: Thumbnail image (512px)
        """
        # Convert images to bytes
        original_buffer = io.BytesIO()
        original_image.save(original_buffer, format="PNG")
        original_buffer.seek(0)

        image_128_buffer = io.BytesIO()
        image_128.save(image_128_buffer, format="PNG")
        image_128_buffer.seek(0)

        image_512_buffer = io.BytesIO()
        image_512.save(image_512_buffer, format="PNG")
        image_512_buffer.seek(0)

        try:
            # Upload original image
            original_blob_name = f"_media/resource/{resource.uuid}.png"
            resource.image = upload_to_bucket(
                original_blob_name,
                original_buffer.getvalue(),
                "wcidfu-bucket"
            )

            # Upload 128px thumbnail
            thumb_128_blob_name = f"_media/resource_thumbnail/{resource.uuid}_128.png"
            resource.thumbnail_image = upload_to_bucket(
                thumb_128_blob_name,
                image_128_buffer.getvalue(),
                "wcidfu-bucket"
            )

            # Upload 512px thumbnail
            thumb_512_blob_name = f"_media/thumbnail_512/{resource.uuid}_512.png"
            resource.thumbnail_image_512 = upload_to_bucket(
                thumb_512_blob_name,
                image_512_buffer.getvalue(),
                "wcidfu-bucket"
            )

        except Exception as e:
            logging.error(f"Failed to upload images for resource {resource.uuid}: {str(e)}")
            raise

    def _resource_parser(self, geninfo: str, params: dict, resource: Resource, 
                        session: Session, generation_data: str = None) -> None:
        """Parse parameters and update resource attributes"""
        try:
            # 기본 파라미터 매핑
            param_mapping = {
                "Prompt": "prompt",
                "Negative prompt": "negative_prompt",
                "Steps": "steps",
                "CFG scale": "cfg_scale", 
                "Seed": "seed",
                "VAE": "sd_vae",
                "Clip skip": "clip_skip"
            }

            # generation_data 처리
            if generation_data:
                resource.generation_data = generation_data

            # 기본 파라미터 처리
            for param_key, resource_attr in param_mapping.items():
                if param_key in params:
                    setattr(resource, resource_attr, params[param_key])

            # Sampler 특별 처리
            if "Sampler" in params:
                schedule_label_list = ["Uniform", "Karras", "Exponential", "Polyexponential"]
                sampler = params["Sampler"].strip()
                
                found_label = next(
                    (label for label in schedule_label_list if label.lower() in sampler.lower()),
                    None
                )
                
                if found_label:
                    resource.sampler = sampler.replace(found_label, "").strip()
                    resource.sampler_scheduler = found_label
                else:
                    resource.sampler = sampler
                    resource.sampler_scheduler = None

            # Size 처리
            if "Size" in params:
                width, height = map(int, params["Size"].split('x'))
                resource.width = width
                resource.height = height

            # Model hash 처리
            if "Model hash" in params:
                sd_model = session.query(SdModel).filter_by(hash=params["Model hash"]).first()
                if sd_model:
                    resource.model_hash = sd_model.hash
                    resource.model_name = sd_model.model_name
                else:
                    resource.model_hash = params["Model hash"]
                    resource.model_name = params.get("Model")

            # Highres 관련 처리
            if "Denoising strength" in params:
                resource.is_highres = True
                resource.hr_denoising_strength = params["Denoising strength"]
                
                highres_params = {
                    "Hires upscale": "hr_upscale_by",
                    "Hires upscaler": "hr_upscaler"
                }
                
                for param_key, resource_attr in highres_params.items():
                    if param_key in params:
                        setattr(resource, resource_attr, params[param_key])

            session.commit()

        except Exception as e:
            session.rollback()
            logging.error(f"Resource parsing failed: {str(e)}")
            raise

# ------------------------------
#  Image Processing
# ------------------------------
class ImageProcessingSystem:
    def __init__(self, user_id: int, default_tag_ids: List[int] = None):
        self.png_util = PngUtill()
        self.prompt_parser = PromptParser()
        self.resource_creator = CreateResource()
        self.default_tag_ids = default_tag_ids or []
        self.user_id = user_id

    def add_create_tags(self, resource: Resource, session: Session) -> None:
        try:
            # 사용자의 collect 타입 태그 조회
            create_tags = session.query(ColorCodeTags).filter(
                ColorCodeTags.user_id == self.user_id,
                ColorCodeTags.type == 'create'
            ).all()
            
            if not create_tags:
                print(f"사용자 {self.user_id}의 create 타입 태그가 없습니다.")
                return

            print(f"\n사용자 {self.user_id}의 create 태그 처리 시작")
            added_tag_ids = {tag.id for tag in resource.tags}  # 기존 태그 ID 집합
            
            for tag in create_tags:
                if tag.id not in added_tag_ids:
                    print(f"Collect 태그 추가: {tag.tag} (ID: {tag.id})")
                    resource.tags.append(tag)
                    added_tag_ids.add(tag.id)
                else:
                    print(f"create 태그 중복 건너뛰기: {tag.tag}")
                    
            session.flush()
            print(f"create 태그 처리 완료")
            
        except Exception as e:
            print(f"create 태그 처리 중 오류 발생: {str(e)}")
            session.rollback()
            raise

    def add_default_tags(self, resource: Resource, session: Session) -> None:
        """Add default tags to a resource using tag IDs"""
        try:
            existing_tag_ids = {tag.id for tag in resource.tags}
            
            for tag_id in self.default_tag_ids:
                if tag_id not in existing_tag_ids:
                    tag = session.query(ColorCodeTags).filter_by(id=tag_id).first()
                    if tag:
                        resource.tags.append(tag)
            session.commit()
                
        except Exception as e:
            logging.error(f"Error adding default tags: {str(e)}")
            session.rollback()
        
    def process_single_image(self, image_path: str, session: Session):
        try:
            original_image = Image.open(image_path)
            image_128 = self.png_util.scale_image_by_height(original_image, 128)
            image_512 = self.png_util.scale_image_by_height(original_image, 512)
            
            geninfo, params = self.png_util.geninfo_params(original_image)
            
            resource = self.resource_creator.create_resource(
                self.user_id, original_image, image_128, image_512, session
            )
            
            if params:
                self.resource_creator._resource_parser(
                    geninfo, params, resource, session, geninfo
                )
                if params.get("Prompt"):
                    self.prompt_parser._process_single_resource(
                        session=session,
                        resource=resource,
                        prompt_text=params["Prompt"]
                    )

            
            self.add_create_tags(resource, session)
            self.add_default_tags(resource, session)

            resource.tag_ids = [tag.id for tag in resource.tags]
            session.commit()

            return resource  # resource 객체 자체를 반환

        except Exception as e:
            logging.error(f"Error processing image {image_path}: {str(e)}")
            raise

    def process_folder(self, folder_path: str) -> None:
        if not os.path.exists(folder_path):
            raise ValueError(f"Folder path does not exist: {folder_path}")
        
        image_files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
        
        if not image_files:
            logging.warning(f"No image files found in {folder_path}")
            return
            
        session, server = get_session()
        first_id = None
        last_id = None
        processed_count = 0
        total_images = len(image_files)
        results = []
        failed_images = []  # 실패한 이미지 목록
        
        try:
            folder_name = os.path.basename(folder_path)
            
            with ThreadPoolExecutor(max_workers=12) as executor:
                futures = {
                    executor.submit(
                        self.process_single_image, 
                        os.path.join(folder_path, img),
                        session
                    ): img for img in image_files
                }
                
                pbar = tqdm(
                    total=len(futures),
                    desc=f"Processing images in {folder_name}"
                )
                
                for future in as_completed(futures):
                    img = futures[future]
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                            if not first_id:  # 첫 번째 성공한 결과
                                first_id = result.id
                            last_id = result.id  # 마지막으로 성공한 결과
                        processed_count += 1
                    except Exception as e:
                        failed_images.append(img)
                        print(f"\nError processing file: {img}")
                        print(f"Error details: {str(e)}")
                    finally:
                        pbar.update(1)
                
                pbar.close()
            
            # 처리 결과 출력
            print("\n=== 처리 결과 ===")
            print(f"총 처리 시도: {total_images}개")
            print(f"성공: {len(results)}개")
            print(f"실패: {len(failed_images)}개")
            if first_id and last_id:
                print(f"성공한 리소스 ID 범위: {first_id} ~ {last_id}")
            
            # 실패한 파일 목록 출력
            if failed_images:
                print("\n=== 실패한 파일 목록 ===")
                for i, failed_img in enumerate(failed_images, 1):
                    print(f"{i}. {failed_img}")
            
            session.commit()
            
        except Exception as e:
            logging.error(f"Folder processing error: {str(e)}")
        finally:
            end_session(session, server)

def get_user_input():
    """Get interactive user input for processing parameters"""
    try:
        # Get user ID
        while True:
            try:
                user_id = int(input("사용자 ID를 입력해주세요: ").strip())
                break
            except ValueError:
                print("올바른 숫자를 입력해주세요.")

        # Get base folder path
        while True:
            base_folder_path = input("작업할 폴더 경로를 입력해주세요: ").strip()
            if os.path.exists(base_folder_path):
                break
            print("존재하지 않는 경로입니다. 다시 입력해주세요.")
        
        # 자동으로 하위 폴더 감지 여부 확인
        process_subfolders = False
        while True:
            subfolder_option = input("하위 폴더들을 각각 처리하시겠습니까? (y/n): ").strip().lower()
            if subfolder_option in ['y', 'n']:
                process_subfolders = (subfolder_option == 'y')
                break
            print("'y' 또는 'n'을 입력해주세요.")
            
        # 폴더를 캐릭터 폴더로 처리할지 기본값 설정
        default_character_folder = False
        if process_subfolders:
            while True:
                auto_character = input("각 하위 폴더를 캐릭터 폴더로 처리할까요? (y/n): ").strip().lower()
                if auto_character in ['y', 'n']:
                    default_character_folder = (auto_character == 'y')
                    break
                print("'y' 또는 'n'을 입력해주세요.")

        # Get default tag IDs
        default_tag_ids = []
        while True:
            add_tags = input("모든 폴더에 공통으로 적용할 디폴트 태그를 추가하시겠습니까? (y/n): ").strip().lower()
            if add_tags in ['y', 'n']:
                if add_tags == 'y':
                    while True:
                        tag_input = input("태그 ID를 입력해주세요 (완료시 엔터): ").strip()
                        if not tag_input:
                            break
                        try:
                            tag_id = int(tag_input)
                            default_tag_ids.append(tag_id)
                        except ValueError:
                            print("올바른 숫자를 입력해주세요.")
                break
            print("'y' 또는 'n'을 입력해주세요.")

        return user_id, base_folder_path, default_tag_ids, process_subfolders, default_character_folder

    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
        sys.exit(0)

def validate_inputs(session, user_id: int, tag_ids: list) -> Tuple[bool, str]:
    """
    입력받은 user_id와 tag_ids가 데이터베이스에 존재하는지 검증합니다.
    
    Args:
        session: 데이터베이스 세션
        user_id (int): 검증할 사용자 ID
        tag_ids (list): 검증할 태그 ID 리스트
        
    Returns:
        Tuple[bool, str]: (검증 성공 여부, 오류 메시지)
    """
    try:
        # 사용자 검증
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return False, f"사용자 ID {user_id}가 존재하지 않습니다."

        # 태그 검증
        if tag_ids:
            existing_tags = session.query(ColorCodeTags).filter(ColorCodeTags.id.in_(tag_ids)).all()
            existing_tag_ids = {tag.id for tag in existing_tags}
            
            missing_tags = set(tag_ids) - existing_tag_ids
            if missing_tags:
                return False, f"다음 태그 ID가 존재하지 않습니다: {missing_tags}"

        return True, "검증 성공"

    except Exception as e:
        return False, f"데이터베이스 검증 중 오류 발생: {str(e)}"

def create_tag_mapping() -> Dict[str, str]:
    """
    CharacterManager, OutfitManager, EventManager의 
    별칭(aliases)들을 하나의 태그 매핑 딕셔너리로 변환합니다.
    """
    # 기존 매니저들 초기화
    character_manager = CharacterManager()
    outfit_manager = OutfitManager()
    event_manager = EventManager()
    
    tag_mapping = {}
    
    # 각 매니저의 items를 순회하면서 태그 매핑 생성
    managers = [
        ('character', character_manager),
        ('outfit', outfit_manager),
        ('event', event_manager)
    ]
    
    for manager_name, manager in managers:
        for standard_name, item in manager.items.items():
            # 각 별칭을 표준 이름에 매핑
            for alias in item.aliases:
                tag_mapping[alias] = standard_name
    
    return tag_mapping

def save_tag_mapping(tag_mapping: Dict[str, str]):
    """
    생성된 태그 매핑을 현재 디렉토리의 tag_mappings.py 파일로 저장합니다.
    """
    import os
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, 'tag_mappings.py')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("# Generated Tag Mapping\n\n")
        f.write("TAG_MAPPING = {\n")
        
        # 알파벳 순으로 정렬하여 저장
        for alias, standard_name in sorted(tag_mapping.items()):
            f.write(f"    {repr(alias)}: {repr(standard_name)},\n")
            
        f.write("}\n")

def get_or_create_character_tag(session, folder_name, user_id, created_tags_dict=None):
    """
    폴더 이름으로 태그를 검색하고 없으면 생성합니다.
    
    Args:
        session: 데이터베이스 세션
        folder_name: 검색할 폴더 이름
        user_id: 사용자 ID
        created_tags_dict: 새로 생성된 태그를 저장할 딕셔너리 (선택 사항)
        
    Returns:
        list: 찾거나 생성한 태그 ID 목록
    """
    try:
        # 소문자로 변환하여 검색
        from sqlalchemy import func
        
        # 폴더 이름을 '_'로 분리하여 각 부분을 개별 태그로 처리
        tag_names = folder_name.split('_')
        if len(tag_names) > 5:  # 최대 5개까지만 처리
            print(f"경고: 폴더 이름에 '_'로 구분된 부분이 5개를 초과합니다. 처음 5개만 처리합니다.")
            tag_names = tag_names[:5]
            
        tag_ids = []
        
        for tag_name in tag_names:
            if not tag_name:  # 빈 문자열 건너뛰기
                continue
                
            search_name = tag_name.lower()
            tag = session.query(ColorCodeTags).filter(
                func.lower(ColorCodeTags.tag) == search_name,
                ColorCodeTags.type == 'normal'
            ).first()
            
            if tag:
                print(f"기존 태그를 찾았습니다: {tag.tag} (ID: {tag.id})")
                tag_ids.append(tag.id)
            else:
                # 태그가 없으면 새로 생성
                new_tag = ColorCodeTags(
                    tag=tag_name,  # 원래 대소문자 유지
                    color_code='#FFFFFF',
                    type='normal',
                    user_id=user_id
                )
                session.add(new_tag)
                session.flush()  # ID를 얻기 위해 flush
                print(f"새로운 태그를 생성했습니다: {new_tag.tag} (ID: {new_tag.id})")
                tag_ids.append(new_tag.id)
                
                # 생성된 태그 정보를 딕셔너리에 추가
                if created_tags_dict is not None:
                    created_tags_dict[new_tag.id] = new_tag.tag
        
        return tag_ids
            
    except Exception as e:
        session.rollback()
        logging.error(f"태그 생성/조회 중 오류 발생: {str(e)}")
        print(f"오류: {str(e)}")
        return []

def get_subfolders(base_path):
    """
    주어진 경로에서 모든 하위 폴더를 찾아 반환합니다.
    
    Args:
        base_path: 기본 경로
        
    Returns:
        list: 하위 폴더 경로 목록
    """
    subfolders = []
    
    # 경로가 파일인지 폴더인지 확인
    if os.path.isfile(base_path):
        return [os.path.dirname(base_path)]
    
    # 직접 이미지 파일이 있는지 확인
    image_files = [f for f in os.listdir(base_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if image_files:
        # 이미지 파일이 직접 있으면 현재 폴더 추가
        subfolders.append(base_path)
    
    # 하위 폴더 확인
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path):
            # 해당 폴더에 이미지 파일이 있는지 확인
            files = [f for f in os.listdir(item_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            if files:  # 이미지 파일이 있는 폴더만 추가
                subfolders.append(item_path)
    
    return subfolders

def process_single_folder(utils, session, user_id, folder_path, default_tag_ids, is_character_folder, created_tags_dict=None):
    """
    단일 폴더를 처리하는 함수
    
    Args:
        utils: 사용하지 않음 (이전 코드와의 호환성을 위해 유지)
        session: 데이터베이스 세션
        user_id: 사용자 ID
        folder_path: 처리할 폴더 경로
        default_tag_ids: 기본 태그 ID 목록
        is_character_folder: 캐릭터 폴더 여부
        created_tags_dict: 새로 생성된 태그를 저장할 딕셔너리 (선택 사항)
    """
    from sqlalchemy import func
    
    # 현재 폴더의 태그 ID 목록 복사 (원본 목록 수정하지 않기 위해)
    folder_tag_ids = default_tag_ids.copy()
    
    # 캐릭터 폴더 처리
    if is_character_folder:
        folder_name = os.path.basename(folder_path)
        print(f"\n폴더 '{folder_name}'을 캐릭터 폴더로 처리합니다.")
        
        # 폴더 이름으로 태그 찾기 또는 생성 (이제 여러 태그 ID를 반환함)
        character_tag_ids = get_or_create_character_tag(session, folder_name, user_id, created_tags_dict)
        
        if character_tag_ids:
            # 각 태그를 현재 폴더의 태그 목록에 추가
            added_count = 0
            for tag_id in character_tag_ids:
                if tag_id not in folder_tag_ids:
                    folder_tag_ids.append(tag_id)
                    added_count += 1
            
            if added_count > 0:
                print(f"{added_count}개의 태그를 태그 목록에 추가했습니다.")
            else:
                print("모든 태그가 이미 태그 목록에 존재합니다.")
        
        # 변경 사항 확정
        session.commit()
    
    # Initialize processor for this folder
    processor = ImageProcessingSystem(
        user_id=user_id,
        default_tag_ids=folder_tag_ids
    )
    
    # Show processing information
    print("\n처리 정보:")
    print(f"폴더 경로: {folder_path}")
    print(f"폴더가 캐릭터 폴더로 처리됨: {'예' if is_character_folder else '아니오'}")
    print(f"적용될 태그 ID: {folder_tag_ids}")
    
    # Process the folder
    processor.process_folder(folder_path)
    print(f"폴더 '{os.path.basename(folder_path)}' 처리가 완료되었습니다.")

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        tag_mapping = create_tag_mapping()
        
        # 매핑 결과 출력
        print(f"총 {len(tag_mapping)}개의 태그 매핑이 생성되었습니다.")
        
        # 파일로 저장
        save_tag_mapping(tag_mapping)

        # Get user input with enhanced options
        user_id, base_folder_path, default_tag_ids, process_subfolders, default_character_folder = get_user_input()
        
        # 데이터베이스 연결
        session, server = get_session()
        
        try:
            # sqlalchemy func 가져오기
            from sqlalchemy import func
            
            # 새로 생성된 태그를 저장할 딕셔너리
            created_tags = {}
            
            # 입력값 검증
            is_valid, error_message = validate_inputs(session, user_id, default_tag_ids)
            if not is_valid:
                print(f"\n오류: {error_message}")
                return
            
            # 폴더 목록 결정
            if process_subfolders:
                # 하위 폴더 검색
                folders = get_subfolders(base_folder_path)
                if not folders:
                    print(f"'{base_folder_path}' 내에 이미지가 포함된 폴더가 없습니다.")
                    return
                
                print(f"\n{len(folders)}개의 폴더가 감지되었습니다:")
                for i, folder in enumerate(folders, 1):
                    print(f"{i}. {folder}")
            else:
                # 단일 폴더 처리
                folders = [base_folder_path]
            
            # 처리 시작 확인
            confirm = input("\n처리를 시작하시겠습니까? (y/n): ").strip().lower()
            if confirm != 'y':
                print("프로그램을 종료합니다.")
                return
            
            # 각 폴더 처리
            for i, folder_path in enumerate(folders, 1):
                print(f"\n[{i}/{len(folders)}] '{os.path.basename(folder_path)}' 폴더 처리 중...")
                
                if process_subfolders and len(folders) > 1:
                    # 여러 폴더 처리 모드에서는 각 폴더를 캐릭터 폴더로 처리하는지 여부 결정
                    is_character_folder = default_character_folder
                    
                    # 기본값이 False인 경우에만 물어봄
                    if not default_character_folder:
                        character_prompt = input(f"'{os.path.basename(folder_path)}'를 캐릭터 폴더로 처리할까요? (y/n, 기본값=n): ").strip().lower()
                        is_character_folder = (character_prompt == 'y')
                else:
                    # 단일 폴더 모드에서는 사용자에게 직접 물어봄
                    character_prompt = input(f"'{os.path.basename(folder_path)}'를 캐릭터 폴더로 처리할까요? (y/n): ").strip().lower()
                    is_character_folder = (character_prompt == 'y')
                
                # 현재 폴더 처리
                process_single_folder(
                    utils=None,  # utils 매개변수는 더 이상 사용하지 않음
                    session=session,
                    user_id=user_id,
                    folder_path=folder_path,
                    default_tag_ids=default_tag_ids,
                    is_character_folder=is_character_folder,
                    created_tags_dict=created_tags
                )
            
            print("\n모든 폴더 처리가 완료되었습니다.")
            
            # 새로 생성된 태그 정보 출력
            if created_tags:
                print("\n=== 이번 작업에서 새로 생성된 태그 ===")
                print("ID\t| 태그명")
                print("-"*50)
                for tag_id, tag_name in created_tags.items():
                    print(f"{tag_id}\t| {tag_name}")
            else:
                print("\n이번 작업에서 새로 생성된 태그가 없습니다.")
            
        finally:
            end_session(session, server)
            
    except Exception as e:
        logging.error(f"처리 중 오류가 발생했습니다: {str(e)}")
        print("오류가 발생했습니다. 로그를 확인해주세요.")
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")

if __name__ == "__main__":
    main()