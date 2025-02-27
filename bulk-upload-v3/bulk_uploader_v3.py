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
from sshtunnel import SSHTunnelForwarder
from google.cloud import storage
from google.oauth2 import service_account

# Database
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from sqlalchemy import func

# Local Imports
from models import (
    setup_database_engine,
    Resource,
    User,
    ColorCodeTags,
    SdModel
)
from manager import CharacterManager, OutfitManager, EventManager



def retry_on_connection_error(max_retries=3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except (psycopg2.OperationalError, SSLError) as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"Connection error: {str(e)}. Retrying... ({attempt + 1}/{max_retries})")
                        self.check_connection()  # 연결 상태 확인 및 재연결
                        time.sleep(5)
                    else:
                        logging.error(f"Connection failed after {max_retries} attempts")
                        raise
        return wrapper
    return decorator
# ------------------------------
#  SSH Connection    
# ------------------------------
class Utills:
    def __init__(self):
        self.server = None

    def start_ssh_tunnel(self, max_retries=3, retry_delay=5):
        for attempt in range(max_retries):
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
                if attempt < max_retries - 1:
                    logging.warning(f"SSH tunnel attempt {attempt + 1} failed: {str(e)}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"Failed to establish SSH tunnel after {max_retries} attempts: {str(e)}")
                    raise

    def check_connection(self):
        if self.server is None or not self.server.is_active:
            logging.info("SSH connection is not active. Reconnecting...")
            self.start_ssh_tunnel()

    def stop_ssh_tunnel(self):
        if self.server:
            self.server.stop()
            logging.info("SSH tunnel closed")

    @classmethod
    def upload_to_bucket(cls, blob_name, data, bucket_name):
        current_script_path = os.path.abspath(__file__)
        base_directory = os.path.dirname(current_script_path)
        
        credentials_path = os.path.join(base_directory, 'wcidfu-77f802b00777.json')
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        credentials = service_account.Credentials.from_service_account_file(credentials_path)

        storage_client = storage.Client(credentials = credentials)
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data)
        clean_blob_name = blob_name.replace("_media/", "")    
        return clean_blob_name
    
    def get_session(self):
        retries = 3
        for attempt in range(retries):
            try:
                server = self.start_ssh_tunnel()
                engine = setup_database_engine("nerdy@2024", server.local_bind_port)
                session_factory = sessionmaker(bind=engine)
                session = scoped_session(session_factory)
                
                # Test connection - SQLAlchemy 2.0 스타일로 수정
                from sqlalchemy import text
                session().execute(text("SELECT 1"))
                
                return session, server
            except Exception as e:
                if attempt < retries - 1:
                    logging.warning(f"Database connection attempt {attempt + 1} failed. Retrying...")
                    time.sleep(5)
                    if self.server:
                        self.stop_ssh_tunnel()
                else:
                    logging.error(f"Failed to establish database connection after {retries} attempts")
                    raise

    def end_session(self, session):
        try:
            # 먼저 SSH 터널을 종료하기 전에 모든 데이터베이스 작업을 완료
            if session:
                try:
                    session.close()
                except:
                    pass
                
                try:
                    session.remove()
                except:
                    pass
                
            # 마지막으로 SSH 터널 종료
            if self.server:
                try:
                    self.server.stop()
                    logging.info("SSH tunnel closed")
                except:
                    pass
                    
        except Exception as e:
            logging.warning(f"Session cleanup warning: {str(e)}")
            pass
        
    @classmethod
    def upload_image_to_gcp_bucket(cls, blob_name, data, bucket_name):
        current_script_path = os.path.abspath(__file__)
        base_directory = os.path.dirname(current_script_path)
        
        credentials_path = os.path.join(base_directory, 'wcidfu-77f802b00777.json')
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        credentials = service_account.Credentials.from_service_account_file(credentials_path)

        storage_client = storage.Client(credentials = credentials)
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data)
        clean_blob_name = blob_name.replace("_media/", "")    
        return clean_blob_name

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

    def parse_generation_parameters(self, x: str):
        res = {}
        lines = x.strip().split("\n")  # 입력된 문자열을 줄 단위로 분리

        for i, line in enumerate(lines):  # 각 줄과 그 인덱스에 대해 반복
            line = line.strip()  # 현재 줄의 앞뒤 공백 제거
            if i == 0:  # 첫 번째 줄인 경우
                res["Prompt"] = line
            elif i == 1 and line.startswith("Negative prompt:"):  # 두 번째 줄이며 "Negative prompt:"로 시작하는 경우
                res["Negative prompt"] = line[16:].strip()
            elif i == 2:  # 세 번째 줄인 경우, 옵션들을 처리
                # 여기에서 각 키-값에 대한 매칭 작업을 수행합니다.
                keys = [
                    "Steps", "Sampler", "CFG scale", "Seed", "Size", 
                    "Model hash", "Model", "VAE hash", "VAE", 
                    "Denoising strength", "Clip skip", "Hires upscale",
                    "Hires upscaler", 
                ]
                for key in keys:
                    # 정규 표현식을 사용하여 각 키에 해당하는 값을 찾습니다.
                    match = re.search(fr'{key}: ([^,]+),', line)
                    if match:
                        # 찾은 값은 그룹 1에 있습니다.
                        value = match.group(1).strip()
                        res[key] = value
                
                controlnet_patterns = re.findall(r'ControlNet \d+: "(.*?)"', line, re.DOTALL)
                for idx, cn_content in enumerate(controlnet_patterns):
                    # ControlNet 내부의 키-값 쌍을 추출합니다.
                    cn_dict = {}
                    cn_pairs = re.findall(r'(\w+): ([^,]+)', cn_content)
                    for key, value in cn_pairs:
                        cn_dict[key.strip()] = value.strip()
                    res[f"ControlNet {idx}"] = cn_dict

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
        self.utils = Utills()

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
            resource.image = Utills.upload_to_bucket(
                original_blob_name,
                original_buffer.getvalue(),
                "wcidfu-bucket"
            )

            # Upload 128px thumbnail
            thumb_128_blob_name = f"_media/resource_thumbnail/{resource.uuid}_128.png"
            resource.thumbnail_image = Utills.upload_to_bucket(
                thumb_128_blob_name,
                image_128_buffer.getvalue(),
                "wcidfu-bucket"
            )

            # Upload 512px thumbnail
            thumb_512_blob_name = f"_media/thumbnail_512/{resource.uuid}_512.png"
            resource.thumbnail_image_512 = Utills.upload_to_bucket(
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
        self.utils = Utills()
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

    # def add_default_tags(self, resource: Resource, session: Session) -> None:
    #     """Add default tags to a resource using tag IDs"""
    #     try:
    #         for tag_id in self.default_tag_ids:
    #             tag = session.query(ColorCodeTags).filter_by(id=tag_id).first()
    #             if tag:
    #                 resource.tags.append(tag)
    #             else:
    #                 logging.warning(f"Tag ID {tag_id} not found in database")
    #         session.commit()
    #     except Exception as e:
    #         logging.error(f"Error adding default tags: {str(e)}")
    #         session.rollback()

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
            
        session, server = self.utils.get_session()
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
            session.remove()

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

        # Get folder path
        while True:
            folder_path = input("이미지가 있는 폴더 경로를 입력해주세요: ").strip()
            if os.path.exists(folder_path):
                break
            print("존재하지 않는 경로입니다. 다시 입력해주세요.")
        
        # 폴더가 캐릭터 폴더인지 확인
        is_character_folder = False
        while True:
            character_folder = input("이 폴더는 캐릭터 폴더입니까? (y/n): ").strip().lower()
            if character_folder in ['y', 'n']:
                is_character_folder = (character_folder == 'y')
                break
            print("'y' 또는 'n'을 입력해주세요.")

        # Get default tag IDs
        default_tag_ids = []
        while True:
            add_tags = input("디폴트 태그를 추가하시겠습니까? (y/n): ").strip().lower()
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

        return user_id, folder_path, default_tag_ids, is_character_folder

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

def get_or_create_character_tag(session, folder_name, user_id):
    """
    폴더 이름으로 태그를 검색하고 없으면 생성합니다.
    
    Args:
        session: 데이터베이스 세션
        folder_name: 검색할 폴더 이름
        user_id: 사용자 ID
        
    Returns:
        ColorCodeTags: 찾거나 생성한 태그 객체의 ID
    """
    try:
        # 소문자로 변환하여 검색
        search_name = folder_name.lower()
        tag = session.query(ColorCodeTags).filter(
            func.lower(ColorCodeTags.tag) == search_name,
            ColorCodeTags.type == 'normal'
        ).first()
        
        if tag:
            print(f"기존 태그를 찾았습니다: {tag.tag} (ID: {tag.id})")
            return tag.id
        else:
            # 태그가 없으면 새로 생성
            new_tag = ColorCodeTags(
                tag=folder_name,  # 원래 대소문자 유지
                color_code='#FFFFFF',
                type='normal',
                user_id=user_id
            )
            session.add(new_tag)
            session.flush()  # ID를 얻기 위해 flush
            print(f"새로운 캐릭터 태그를 생성했습니다: {new_tag.tag} (ID: {new_tag.id})")
            return new_tag.id
            
    except Exception as e:
        session.rollback()
        logging.error(f"캐릭터 태그 생성/조회 중 오류 발생: {str(e)}")
        print(f"오류: {str(e)}")
        return None

# def main():
#     # Configure logging
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(levelname)s - %(message)s'
#     )
    
#     try:
#         # Utils 인스턴스 생성
#         utils = Utills()
        
#         tag_mapping = create_tag_mapping()
        
#         # 매핑 결과 출력
#         print(f"총 {len(tag_mapping)}개의 태그 매핑이 생성되었습니다.")
        
#         # 파일로 저장
#         save_tag_mapping(tag_mapping)

#         # Get user input
#         user_id, folder_path, default_tag_ids = get_user_input()
        
#         # 데이터베이스 연결
#         session, server = utils.get_session()
        
#         try:
#             # 입력값 검증
#             is_valid, error_message = validate_inputs(session, user_id, default_tag_ids)
#             if not is_valid:
#                 print(f"\n오류: {error_message}")
#                 return
                
#             # Initialize processor
#             processor = ImageProcessingSystem(
#                 user_id=user_id,
#                 default_tag_ids=default_tag_ids
#             )
            
#             # Show processing information
#             print("\n처리 정보:")
#             print(f"사용자 ID: {user_id}")
#             print(f"폴더 경로: {folder_path}")
#             print(f"적용될 태그 ID: {default_tag_ids}")
            
#             # Confirm processing
#             confirm = input("\n처리를 시작하시겠습니까? (y/n): ").strip().lower()
#             if confirm != 'y':
#                 print("프로그램을 종료합니다.")
#                 return
            
#             # Process the folder
#             processor.process_folder(folder_path)
#             print("이미지 처리가 완료되었습니다.")
            
#         finally:
#             utils.end_session(session)
            
#     except Exception as e:
#         logging.error(f"처리 중 오류가 발생했습니다: {str(e)}")
#         print("오류가 발생했습니다. 로그를 확인해주세요.")
#     except KeyboardInterrupt:
#         print("\n프로그램이 중단되었습니다.")
#     finally:
#         utils.stop_ssh_tunnel()
def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Utils 인스턴스 생성
        utils = Utills()
        
        tag_mapping = create_tag_mapping()
        
        # 매핑 결과 출력
        print(f"총 {len(tag_mapping)}개의 태그 매핑이 생성되었습니다.")
        
        # 파일로 저장
        save_tag_mapping(tag_mapping)

        # Get user input with character folder check
        user_id, folder_path, default_tag_ids, is_character_folder = get_user_input()
        
        # 데이터베이스 연결
        session, server = utils.get_session()
        
        try:
            # sqlalchemy func 가져오기
            from sqlalchemy import func
            
            # 캐릭터 폴더 처리
            if is_character_folder:
                folder_name = os.path.basename(folder_path)
                print(f"\n폴더 '{folder_name}'을 캐릭터 폴더로 처리합니다.")
                
                # 폴더 이름으로 태그 찾기 또는 생성
                character_tag_id = get_or_create_character_tag(session, folder_name, user_id)
                
                if character_tag_id:
                    # 캐릭터 태그를 디폴트 태그 목록에 추가
                    if character_tag_id not in default_tag_ids:
                        default_tag_ids.append(character_tag_id)
                        print(f"캐릭터 태그(ID: {character_tag_id})를 디폴트 태그 목록에 추가했습니다.")
                    else:
                        print(f"캐릭터 태그(ID: {character_tag_id})는 이미 디폴트 태그 목록에 있습니다.")
                
                # 변경 사항 확정
                session.commit()
            
            # 입력값 검증
            is_valid, error_message = validate_inputs(session, user_id, default_tag_ids)
            if not is_valid:
                print(f"\n오류: {error_message}")
                return
                
            # Initialize processor
            processor = ImageProcessingSystem(
                user_id=user_id,
                default_tag_ids=default_tag_ids
            )
            
            # Show processing information
            print("\n처리 정보:")
            print(f"사용자 ID: {user_id}")
            print(f"폴더 경로: {folder_path}")
            print(f"폴더가 캐릭터 폴더로 처리됨: {'예' if is_character_folder else '아니오'}")
            print(f"적용될 태그 ID: {default_tag_ids}")
            
            # Confirm processing
            confirm = input("\n처리를 시작하시겠습니까? (y/n): ").strip().lower()
            if confirm != 'y':
                print("프로그램을 종료합니다.")
                return
            
            # Process the folder
            processor.process_folder(folder_path)
            print("이미지 처리가 완료되었습니다.")
            
        finally:
            utils.end_session(session)
            
    except Exception as e:
        logging.error(f"처리 중 오류가 발생했습니다: {str(e)}")
        print("오류가 발생했습니다. 로그를 확인해주세요.")
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")
    finally:
        utils.stop_ssh_tunnel()
if __name__ == "__main__":
    main()