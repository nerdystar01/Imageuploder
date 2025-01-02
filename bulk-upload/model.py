from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.dialects.postgresql import UUID, ENUM

import json
import uuid
import zlib
import io
import struct
from datetime import datetime
from google.cloud import storage

# client = storage
# bucket = client.get_bucket('your-bucket-name')
# 데이터베이스 모델 정의
Base = declarative_base()

class Resource(Base):
    __tablename__ = 'resource'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    original_resource_id = Column(Integer, nullable=True)
    history_id = Column(Integer, nullable=True)
    category_id = Column(Integer, nullable=True)
    folder_id = Column(Integer, nullable=True)
    name = Column(String(1000), default="")
    description = Column(Text, default="")
    image = Column(String(200), default="")
    generation_data = Column(Text, default="")
    model_name = Column(String(200), default="")
    model_hash = Column(String(100), default="")
    sampler = Column(String(100), default="Euler")
    sampler_scheduler = Column(String(100), default="")
    prompt = Column(Text, default="")
    negative_prompt = Column(Text, default="")
    width = Column(Integer, default=512)
    height = Column(Integer, default=512)
    steps = Column(Integer, default=20)
    cfg_scale = Column(Float, default=7.5)
    seed = Column(Integer, default=-1)
    is_highres = Column(Boolean, default=False)
    hr_upscaler = Column(String(300), default="")
    hr_steps = Column(Integer, default=0)
    hr_denoising_strength = Column(Float, default=0)
    hr_upscale_by = Column(Float, default=1)
    is_display = Column(Boolean, default=True)
    is_empty = Column(Boolean, default=False)
    for_testing = Column(Boolean, default=False)
    sd_vae = Column(String(200), default="")
    is_bmab = Column(Boolean, default=False)
    is_i2i = Column(Boolean, default=False)
    resize_mode = Column(Integer, default=0)
    init_image = Column(String(200), default="")
    i2i_denoising_strength = Column(Float, default=0)
    is_sd_upscale = Column(Boolean, default=False)
    sd_tile_overlap = Column(Integer, default=0)
    sd_scale_factor = Column(Integer, default=0)
    sd_upscale = Column(String(4000), default="")
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4)
    thumbnail_image = Column(String(200), default="")
    thumbnail_image_512 = Column(String(300), default="")
    is_variation = Column(Boolean, default=False)
    generate_opt = Column(String(200), default="Upload")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class PublicFolder(Base):
    __tablename__ = 'public_folder'
    
    id = Column(Integer, primary_key=True)
    create_user_id = Column(Integer, nullable=True)
    json_file = Column(Text, nullable=True)  # Text type used to store file path
    team_id = Column(Integer, nullable=True)
    status = Column(ENUM('AV', 'UN', name='folderstatus'), default='AV', nullable=False)

class SdModel(Base):
    __tablename__ = 'sdmodel'

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    model_name = Column(String(200), nullable=False)
    hash = Column(String(10), index=True, nullable=False)
    sha256 = Column(String(64), nullable=False)
    thumbnail_image = Column(String(200))  # 이미지 파일 경로를 저장
    is_active = Column(Boolean, default=False)
    folder_id = Column(Integer, nullable=True)
    