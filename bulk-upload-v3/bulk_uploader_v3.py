# Standard Library
import os
import sys
import io
import logging
import re
from typing import Tuple, Dict, Any, List
from datetime import datetime

# Third Party Libraries
from PIL import Image, PngImagePlugin
import piexif
import piexif.helper
from tqdm import tqdm
from sshtunnel import SSHTunnelForwarder
from google.cloud import storage
from google.oauth2 import service_account

# Database
from sqlalchemy.orm import Session, scoped_session, sessionmaker

# Local Imports
from models import (
    setup_database_engine,
    Resource,
    User,
    ColorCodeTags,
    SdModel
)


# ------------------------------
#  SSH Connection    
# ------------------------------
class Utills:
    def __init__(self):
        self.server = None

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

    def check_connection(self):
        if self.server is None or not self.server.is_active:
            logging.info("SSH connection is not active. Reconnecting...")
            self.start_ssh_tunnel()

    def stop_ssh_tunnel(self):
        if self.server:
            self.server.stop()
            logging.info("SSH tunnel closed")

    @classmethod
    def upload_to_bucket(blob_name, data, bucket_name):
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
        server = self.start_ssh_tunnel()
        engine = setup_database_engine("nerdy@2024", server.local_bind_port)
        session_factory = sessionmaker(bind=engine)
        session = scoped_session(session_factory)
        return session, server

    def end_session(self,session):
        session.close()
        self.stop_ssh_tunnel()

    def upload_image_to_gcp_bucket(blob_name, data, bucket_name):
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
        resized_images = {height: self.resize_image(original_image, height) for height in heights}
        return original_image, resized_images[128], resized_images[512]

# ------------------------------
#  PromptParser
# ------------------------------
class PromptParser:
    def __init__(self):
        self.tag_mapping = {
            # ... (기존 매핑)
        }
        # Lora 태그를 찾기 위한 정규식 패턴
        self.lora_regex = r'<lora:([^:]+):([0-9.]+)>'

    def _get_or_create_tag(self, session: Session, tag_name: str) -> ColorCodeTags:
        # ... (기존 메서드)
        pass

    def _extract_lora_tags(self, prompt_text: str) -> List[Tuple[str, float]]:
        """
        프롬프트 텍스트에서 모든 Lora 태그와 가중치를 추출합니다.
        
        Args:
            prompt_text (str): 분석할 프롬프트 텍스트
            
        Returns:
            List[Tuple[str, float]]: (모델명, 가중치) 튜플의 리스트
        """
        matches = re.findall(self.lora_regex, prompt_text)
        return [(model, float(weight)) for model, weight in matches]

    def _process_lora_tags(self, session, resource, prompt_text: str) -> int:
        """
        프롬프트 텍스트에서 Lora 태그를 처리하고 리소스에 태그를 추가합니다.
        
        Args:
            resource: 태그가 추가될 리소스 객체
            prompt_text (str): 분석할 프롬프트 텍스트
            
        Returns:
            int: 처리된 Lora 태그의 수
        """
        converted_count = 0
        lora_tags = self._extract_lora_tags(prompt_text)
        
        for model_name, weight in lora_tags:
            # 모델명을 태그 매핑에서 찾아 변환
            if model_name.lower() in self.tag_mapping:
                tag_name = self.tag_mapping[model_name.lower()]
            else:
                # 매핑에 없는 경우 원본 모델명 사용
                tag_name = model_name
            
            # 가중치 정보를 포함한 태그 생성
            # weight_tag_name = f"{tag_name}_{weight:.1f}"
            # converted_tag = self._get_or_create_tag(session, weight_tag_name)
            # resource.tags.add(converted_tag)
            
            # 기본 태그도 추가 (가중치 없는 버전)
            base_tag = self._get_or_create_tag(session, tag_name)
            resource.tags.add(base_tag)
            
            converted_count += 1
        
        return converted_count

    def _process_single_resource(self, resource, prompt_text: str) -> int:
        """
        단일 리소스의 프롬프트를 처리하고 태그를 추가합니다.
        
        Args:
            resource: 태그가 추가될 리소스 객체
            prompt_text (str): 분석할 프롬프트 텍스트
            
        Returns:
            int: 총 처리된 태그의 수
        """
        converted_count = 0
        
        # 기존 태그 매핑 처리
        for search_term, tag_name in self.tag_mapping.items():
            if search_term.lower() in prompt_text.lower():
                converted_tag = self._get_or_create_tag(session, tag_name)
                resource.tags.add(converted_tag)
                converted_count += 1
        
        # Lora 태그 처리
        converted_count += self._process_lora_tags(resource, prompt_text)
        
        return converted_count

    def process_resources(self, resources, prompt_field: str = 'prompt') -> int:
        """
        여러 리소스의 프롬프트를 처리하고 태그를 추가합니다.
        
        Args:
            resources: 처리할 리소스 목록
            prompt_field (str): 프롬프트 텍스트가 있는 필드 이름
            
        Returns:
            int: 총 처리된 태그의 수
        """
        total_converted = 0
        
        for resource in resources:
            prompt_text = getattr(resource, prompt_field, '')
            if prompt_text:
                total_converted += self._process_single_resource(resource, prompt_text)
        
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
            resource.image = self.utils.upload_to_bucket(
                original_blob_name,
                original_buffer.getvalue(),
                "wcidfu-bucket"
            )

            # Upload 128px thumbnail
            thumb_128_blob_name = f"_media/resource_thumbnail/{resource.uuid}_128.png"
            resource.thumbnail_image = self.utils.upload_to_bucket(
                thumb_128_blob_name,
                image_128_buffer.getvalue(),
                "wcidfu-bucket"
            )

            # Upload 512px thumbnail
            thumb_512_blob_name = f"_media/thumbnail_512/{resource.uuid}_512.png"
            resource.thumbnail_image_512 = self.utils.upload_to_bucket(
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
    def __init__(self, user_id: int):
        self.utils = Utills()
        self.png_util = PngUtill()
        self.prompt_parser = PromptParser()
        self.resource_creator = CreateResource()
        self.user_id = user_id

    def add_default_tags(self, resource: Resource, session: Session) -> None:
        """Add default tags to a resource using tag IDs"""
        try:
            for tag_id in self.default_tag_ids:
                tag = session.query(ColorCodeTags).filter_by(id=tag_id).first()
                if tag:
                    resource.tags.add(tag)
                else:
                    logging.warning(f"Tag ID {tag_id} not found in database")
            session.commit()
        except Exception as e:
            logging.error(f"Error adding default tags: {str(e)}")
            session.rollback()
        
    def process_single_image(self, image_path: str, session: Session) -> None:
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
                    self.prompt_parser._process_single_resource(resource, params["Prompt"])

            self.add_default_tags(resource, session)
            
        except Exception as e:
            logging.error(f"Error processing image {image_path}: {str(e)}")
            raise

    def process_folder(self, folder_path: str) -> None:
        """Process all images in a folder"""
        if not os.path.exists(folder_path):
            raise ValueError(f"Folder path does not exist: {folder_path}")
        
        # Get all image files
        image_files = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        ]
        
        if not image_files:
            logging.warning(f"No image files found in {folder_path}")
            return
        
        # Start SSH tunnel and get session
        session, server = self.utils.get_session()
        
        try:
            # Process images with progress bar
            for image_file in tqdm(image_files, desc="Processing images"):
                image_path = os.path.join(folder_path, image_file)
                self.process_single_image(image_path, session)
                
        except Exception as e:
            logging.error(f"Error processing folder: {str(e)}")
            raise
            
        finally:
            # Clean up
            self.utils.end_session(session)
    
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

        # Get default tag IDs
        default_tag_ids = []
        add_tags = input("디폴트 태그를 추가하시겠습니까? (y/n): ").strip().lower()
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

        return user_id, folder_path, default_tag_ids

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

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Utils 인스턴스 생성
        utils = Utills()
        
        # Get user input
        user_id, folder_path, default_tag_ids = get_user_input()
        
        # 데이터베이스 연결
        session, server = utils.get_session()
        
        try:
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

if __name__ == "__main__":
    main()