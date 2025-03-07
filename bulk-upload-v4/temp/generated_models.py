#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
자동 생성된 SQLAlchemy 모델 파일

생성 시간: 2025-03-07 17:00:14
이 파일은 자동으로 생성되었으므로 직접 수정하지 마십시오.
"""

# Standard Library
from datetime import datetime
import uuid
from typing import List
from urllib.parse import quote_plus

# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, BigInteger, SmallInteger, String, Float, Boolean, ForeignKey, DateTime, Text, Table, UniqueConstraint, func, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import pytz

# 서울 timezone 설정
seoul_tz = pytz.timezone('Asia/Seoul')
Base = declarative_base()

# ------------------------------
#  Association Tables
# ------------------------------
resource_likes = Table(
   'resource_likes', 
   Base.metadata,
   Column('id', Integer, primary_key=True),
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id')),
   UniqueConstraint('resource_id', 'user_id', name='resource_likes_resource_id_user_id_c4fb10b0_uniq')
)

resource_hidden_users = Table(
   'resource_hidden_users', 
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id')),
)

resource_tabbed_users = Table(
   'resource_tabbed_users', 
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id')),
)

resource_placeholder = Table(
   'resource_placeholder', 
   Base.metadata,
   Column('id', Integer, primary_key=True),
   Column('created_at', DateTime),
   Column('updated_at', DateTime),
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id')),
   UniqueConstraint('user_id', name='resource_placeholder_user_id_key'),
   UniqueConstraint('user_id', 'resource_id', name='resource_placeholder_user_id_resource_id_7c04a2d4_uniq')
)

resource_view_status = Table(
   'resource_view_status', 
   Base.metadata,
   Column('id', Integer, primary_key=True),
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id')),
   UniqueConstraint('resource_id', 'user_id', name='resource_view_status_resource_id_user_id_a00f1460_uniq')
)

resource_tags = Table(
   'resource_tags', 
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('colorcodetagss_id', Integer, ForeignKey('color_code_tags.id')),
)

# ------------------------------
#  Models
# ------------------------------
class User(Base):
   __tablename__ = 'user'

   id = Column(BigInteger, primary_key=True)
   created_at = Column(DateTime, nullable=False)
   updated_at = Column(DateTime, nullable=False)
   password = Column(String(128), nullable=False)
   last_login = Column(DateTime, nullable=True)
   is_superuser = Column(Boolean, nullable=False)
   is_staff = Column(Boolean, nullable=False)
   is_active = Column(Boolean, nullable=False)
   date_joined = Column(DateTime, nullable=False)
   email = Column(String(254), nullable=False)
   folder_id = Column(BigInteger, nullable=True)
   json_file = Column(String(100), nullable=True)
   nano_id = Column(String(21), nullable=True)
   username_2 = Column(String(200), nullable=True)
   google_email = Column(String(254), nullable=True)
   metamask_wallet_address = Column(String(42), nullable=True)
   nickname = Column(String(200), nullable=True)

   # Relationships
   resources = relationship("Resource", secondary=resource_likes, back_populates="users")
   resources = relationship("Resource", secondary=resource_hidden_users, back_populates="users")
   resources = relationship("Resource", secondary=resource_tabbed_users, back_populates="users")
   resources = relationship("Resource", secondary=resource_placeholder, back_populates="users")
   resources = relationship("Resource", secondary=resource_view_status, back_populates="users")

class Resource(Base):
   __tablename__ = 'resource'

   id = Column(BigInteger, primary_key=True)
   created_at = Column(DateTime, nullable=False)
   updated_at = Column(DateTime, nullable=False)
   name = Column(String(1000), nullable=False)
   description = Column(Text, nullable=False)
   sampler = Column(String(100), nullable=False)
   image = Column(String(200), nullable=False)
   prompt = Column(Text, nullable=False)
   negative_prompt = Column(Text, nullable=False)
   width = Column(Integer, nullable=False)
   height = Column(Integer, nullable=False)
   steps = Column(Integer, nullable=False)
   cfg_scale = Column(Float, nullable=False)
   seed = Column(BigInteger, nullable=False)
   is_display = Column(Boolean, nullable=False)
   is_empty = Column(Boolean, nullable=False)
   folder_id = Column(BigInteger, nullable=True)
   history_id = Column(BigInteger, nullable=True)
   original_resource_id = Column(Integer, ForeignKey('resource.id'), nullable=True)
   user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
   generation_data = Column(Text, nullable=False)
   model_hash = Column(String(100), nullable=False)
   model_name = Column(String(200), nullable=False)
   is_highres = Column(Boolean, nullable=False)
   hr_denoising_strength = Column(Float, nullable=False)
   hr_steps = Column(Integer, nullable=False)
   hr_upscale_by = Column(Float, nullable=False)
   hr_upscaler = Column(String(300), nullable=False)
   for_testing = Column(Boolean, nullable=False)
   sd_vae = Column(String(200), nullable=False)
   category_id = Column(BigInteger, nullable=True)
   i2i_denoising_strength = Column(Float, nullable=False)
   init_image = Column(String(200), nullable=True)
   is_bmab = Column(Boolean, nullable=False)
   is_i2i = Column(Boolean, nullable=False)
   resize_mode = Column(SmallInteger, nullable=False)
   is_sd_upscale = Column(Boolean, nullable=False)
   sd_scale_factor = Column(Integer, nullable=False)
   sd_tile_overlap = Column(Integer, nullable=False)
   sd_upscale = Column(String(4000), nullable=False)
   thumbnail_image = Column(String(200), nullable=True)
   uuid = Column(UUID(as_uuid=True), nullable=False)
   is_variation = Column(Boolean, nullable=False)
   generate_opt = Column(String(300), nullable=False)
   sampler_scheduler = Column(String(200), nullable=True)
   thumbnail_image_512 = Column(String(300), nullable=False)
   star_rating = Column(Integer, nullable=False)
   clip_skip = Column(Integer, nullable=True)
   count_download = Column(Integer, nullable=False)
   reference_resource_id = Column(Integer, ForeignKey('resource.id'), nullable=True)
   royalty = Column(Float, nullable=False)
   gpt_vision_score = Column(Integer, nullable=True)
   slack_timestamp = Column(Text, nullable=False)
   binary_number_pattern = Column(String(2048), nullable=True)
   block_hash = Column(String(128), nullable=True)
   tag_ids = Column(ARRAY(Integer), nullable=False)
   count_like = Column(Integer, nullable=False)

   # Relationships
   original_resource = relationship("Resource", foreign_keys=[original_resource_id])
   reference_resource = relationship("Resource", foreign_keys=[reference_resource_id])
   user = relationship("User", foreign_keys=[user_id])
   users = relationship("User", secondary=resource_likes, back_populates="resources")
   users = relationship("User", secondary=resource_hidden_users, back_populates="resources")
   users = relationship("User", secondary=resource_tabbed_users, back_populates="resources")
   users = relationship("User", secondary=resource_placeholder, back_populates="resources")
   users = relationship("User", secondary=resource_view_status, back_populates="resources")
   color_code_tagss = relationship("ColorCodeTags", secondary=resource_tags, back_populates="resources")
   tags = relationship(
      "ColorCodeTags",
      secondary="resource_tag_v2",
      back_populates="resources", overlaps="tag_resources"
   )

class SdModel(Base):
   __tablename__ = 'sd_model'

   id = Column(BigInteger, primary_key=True)
   created_at = Column(DateTime, nullable=False)
   updated_at = Column(DateTime, nullable=False)
   thumbnail_image = Column(String(200), nullable=True)
   title = Column(String(200), nullable=False)
   model_name = Column(String(200), nullable=False)
   hash = Column(String(10), nullable=False)
   sha256 = Column(String(64), nullable=False)
   is_active = Column(Boolean, nullable=False)
   folder_id = Column(BigInteger, nullable=True)


class Team(Base):
   __tablename__ = 'team'

   id = Column(BigInteger, primary_key=True)
   created_at = Column(DateTime, nullable=False)
   updated_at = Column(DateTime, nullable=False)
   name = Column(String(200), nullable=False)
   create_user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
   nano_id = Column(String(21), nullable=True)

   # Relationships
   create_user = relationship("User", foreign_keys=[create_user_id])

class ColorCodeTags(Base):
   __tablename__ = 'color_code_tags'

   id = Column(Integer, primary_key=True)
   color_code = Column(String(7), nullable=True)
   tag = Column(String(4000), nullable=True)
   created_at = Column(DateTime, nullable=True)
   updated_at = Column(DateTime, nullable=True)
   type = Column(String(10), nullable=False)
   user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
   binary_number_mask = Column(String(2048), nullable=True)

   # Relationships
   user = relationship("User", foreign_keys=[user_id])
   resources = relationship("Resource", secondary=resource_tags, back_populates="color_code_tagss")

class ResourceTagV2(Base):
   __tablename__ = 'resource_tag_v2'

   id = Column(BigInteger, primary_key=True)
   created_at = Column(DateTime, nullable=False)
   updated_at = Column(DateTime, nullable=False)
   resource_id = Column(Integer, ForeignKey('resource.id'), nullable=False)
   tag_id = Column(Integer, ForeignKey('color_code_tags.id'), nullable=False)

   # Relationships
   resource = relationship("Resource", foreign_keys=[resource_id])
   tag = relationship("ColorCodeTags", foreign_keys=[tag_id])

def setup_database_engine(password, port):
   db_user = "wcidfu"
   db_host = "127.0.0.1"
   db_name = "wcidfu"
   encoded_password = quote_plus(password)
   engine = create_engine(f'postgresql+psycopg2://{db_user}:{encoded_password}@{db_host}:{port}/{db_name}')
   Base.metadata.create_all(engine)
   return engine

# 생성 완료