#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
from typing import List

# GCP and Vertex AI imports
try:
    import vertexai
    from vertexai.vision_models import Image, MultiModalEmbeddingModel
    from google.oauth2 import service_account
except ImportError:
    MultiModalEmbeddingModel = None # Handle missing library

# Local SQLAlchemy models
from models import Resource, VertexAiEmbedDbEmbeddings
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class ResourceEmbeddingHelper:
    """
    리소스 임베딩 생성 및 저장을 담당하는 헬퍼 클래스.
    (SQLAlchemy와 함께 작동하도록 수정됨)
    """
    def __init__(self, resource_id: int, session: Session, project_id: str = "453518888734", region: str = "asia-northeast3"):
        """
        헬퍼 클래스 생성자.
        리소스 ID, SQLAlchemy 세션, GCP 설정을 받고 Vertex AI 모델을 초기화합니다.
        """
        self.resource_id = resource_id
        self.session = session
        self.project_id = project_id
        self.region = region
        self.resource = None
        self.model = None
        self.bucket_name = "wcidfu-bucket"

        if not MultiModalEmbeddingModel:
            logger.error("Vertex AI 라이브러리가 없어 모델을 초기화할 수 없습니다. `pip install google-cloud-aiplatform`를 실행해주세요.")
            return

        try:
            logger.info("Vertex AI 인증 및 초기화 시작...")

            # --- 인증 정보 명시적 로드 ---
            # 현재 스크립트의 디렉토리를 기준으로 인증 파일 경로 설정
            current_script_path = os.path.abspath(__file__)
            base_directory = os.path.dirname(current_script_path)
            credentials_path = os.path.join(base_directory, 'wcidfu-77f802b00777.json')

            if os.path.exists(credentials_path):
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                logger.info(f"서비스 계정 '{credentials.service_account_email}'을 사용하여 인증합니다.")
            else:
                credentials = None
                logger.warning(f"인증 파일 '{credentials_path}'을 찾을 수 없습니다. 기본 인증(ADC)을 시도합니다.")
            # ---------------------------

            vertexai.init(
                project=self.project_id,
                location=self.region,
                credentials=credentials # 명시적으로 인증 정보 전달
            )
            logger.info(f"Vertex AI 초기화 완료 (Project: {self.project_id}, Region: {self.region})")
            
            logger.info("Vertex AI 모델 로딩 중...")
            self.model = MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")
            logger.info("Vertex AI 모델이 성공적으로 초기화되었습니다.")
            
        except Exception as e:
            logger.error(f"Vertex AI 모델 초기화 중 오류 발생: {e}", exc_info=True)

    @staticmethod
    def _convert_http_to_gcs_uri(http_url: str) -> str:
        """
        Signed URL에서 쿼리 파라미터(? 뒷부분)를 제거하고 gs:// URI로 변환합니다.
        """
        base_url = http_url.split('?')[0]
        
        if base_url.startswith("https://storage.googleapis.com/"):
            return base_url.replace("https://storage.googleapis.com/", "gs://")
        
        logger.warning(f"GCS URL 형식이 아니므로 변환 없이 원본 URL을 사용합니다: {base_url}")
        return base_url

    def _get_vertex_embedding(self, image_url: str) -> List[float]:
        """
        [비공개 메서드] 이미지 URL로부터 Vertex AI 임베딩을 추출합니다.
        """
        if not self.model:
            logger.error("Vertex AI 모델이 준비되지 않아 임베딩을 생성할 수 없습니다.")
            return None

        logger.info(f"Vertex AI로 '{image_url}'의 임베딩 생성을 시작합니다.")
        try:
            gcs_uri = self._convert_http_to_gcs_uri(image_url)
            image = Image(gcs_uri=gcs_uri)
            embeddings = self.model.get_embeddings(image=image)
            embedding_values = embeddings.image_embedding
            logger.info(f"임베딩 벡터를 성공적으로 생성했습니다. (차원: {len(embedding_values)})")
            return embedding_values
        except Exception as e:
            logger.error(f"Vertex AI 임베딩 생성 중 예외 발생 (URL: {image_url}): {e}", exc_info=True)
            return None

    def _fetch_resource(self) -> bool:
        """리소스 객체를 데이터베이스에서 가져옵니다. (SQLAlchemy 사용)"""
        try:
            self.resource = self.session.query(Resource).get(self.resource_id)
            if self.resource:
                return True
            else:
                logger.error(f"ID가 {self.resource_id}인 리소스를 찾을 수 없습니다.")
                return False
        except Exception as e:
            logger.error(f"ID {self.resource_id} 리소스 조회 중 DB 오류: {e}", exc_info=True)
            return False

    def _validate_resource(self) -> bool:
        """리소스가 처리에 적합한지 검증합니다."""
        if not self.resource.image:
            logger.warning(f"리소스 ID {self.resource_id}에는 이미지가 없어 처리를 건너뜁니다.")
            return False
        return True

    def _generate_embedding(self) -> List[float]:
        """임베딩 생성 로직을 호출합니다."""
        full_blob_path = f"_media/{self.resource.image}"
        image_url = f"https://storage.googleapis.com/{self.bucket_name}/{full_blob_path}"
        return self._get_vertex_embedding(image_url)

    def _save_embedding(self, embedding_vector: List[float]):
        """생성된 임베딩을 SQLAlchemy를 사용하여 저장합니다."""
        try:
            full_blob_path = f"_media/{self.resource.image}"
            image_url = f"https://storage.googleapis.com/{self.bucket_name}/{full_blob_path}"
            
            # session.merge()는 insert와 update 로직(upsert)을 모두 처리합니다.
            # 기본 키(file_based_uuid)를 확인하여 작업을 결정합니다.
            embedding_to_save = VertexAiEmbedDbEmbeddings(
                file_based_uuid=str(self.resource.uuid),
                embedding=str(embedding_vector),
                original_path=self.resource.image,
                full_url=image_url,
                numeric_id_str=str(self.resource.id)
            )
            self.session.merge(embedding_to_save)
            self.session.commit()
            # 참고: 이 방식으로는 insert/update 여부를 쉽게 알 수 없지만,
            # 결과적으로 데이터는 안전하게 저장됩니다.
            logger.info(f"[DB 저장 완료] UUID {self.resource.uuid}의 임베딩을 저장(생성/업데이트)했습니다.")
        except Exception as e:
            logger.error(f"임베딩 저장 중 DB 오류 발생 (UUID: {self.resource.uuid}): {e}", exc_info=True)
            self.session.rollback()

    def run(self):
        """헬퍼의 메인 실행 메서드. 모든 과정을 순차적으로 실행합니다."""
        logger.info(f"리소스 ID {self.resource_id}에 대한 임베딩 처리 시작...")
        if not self.model:
            logger.error("모델이 없어 처리를 중단합니다.")
            return

        if not self._fetch_resource(): return
        if not self._validate_resource(): return
            
        try:
            embedding = self._generate_embedding()
            if not embedding:
                logger.error(f"리소스 ID {self.resource_id}의 임베딩 생성에 실패했습니다.")
                return
            
            self._save_embedding(embedding)
            logger.info(f"리소스 ID {self.resource_id}에 대한 임베딩 처리 성공적으로 완료.")
        except Exception as e:
            logger.error(f"리소스 ID {self.resource_id} 처리 중 예외 발생: {e}", exc_info=True)