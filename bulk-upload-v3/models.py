# Standard Library
from datetime import datetime
import uuid
from typing import List
from urllib.parse import quote_plus



# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, Table, UniqueConstraint, func
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
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id'))
)

resource_tags = Table(
   'resource_tags', 
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('colorcodetagss_id', Integer, ForeignKey('color_code_tags.id'))
)

resource_hidden_users = Table(
   'resource_hidden_users',
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id'))
)

resource_tabbed_users = Table(
   'resource_tabbed_users',
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id'))
)

resource_placeholder = Table(
   'resource_placeholder', 
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id')),
   UniqueConstraint('resource_id', 'user_id', name='unique_resource_placeholder')
)

resource_view_status = Table(
   'resource_view_status',
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id'))
)

# ------------------------------
#  Models
# ------------------------------
class User(Base):
   __tablename__ = 'user'

   id = Column(Integer, primary_key=True)
   email = Column(String, unique=True, nullable=False)
   folder_id = Column(Integer, nullable=True)
   json_file = Column(String, nullable=True)
   nano_id = Column(String(21), unique=True, nullable=True)
   username_2 = Column(String(256), nullable=True)
   nickname = Column(String(256), nullable=True)
   google_email = Column(String, unique=True, nullable=False)
   metamask_wallet_address = Column(String, unique=True, nullable=False)

   # Relationships
   liked_resources = relationship("Resource", secondary=resource_likes, back_populates="likes")
   hidden_resources = relationship("Resource", secondary=resource_hidden_users, back_populates="hidden_by")
   tabbed_resources = relationship("Resource", secondary=resource_tabbed_users, back_populates="tabbed_by")
   color_code_tags = relationship("ColorCodeTags", back_populates="user")
   placeholder_resources = relationship("Resource", secondary=resource_placeholder, back_populates="placeholder_users")
   viewed_resources = relationship("Resource", secondary=resource_view_status, back_populates="view_status")

class ResourceTagV2(Base):
   __tablename__ = 'resource_tag_v2'
   
   id = Column(Integer, primary_key=True)
   resource_id = Column('resource_id', Integer, ForeignKey('resource.id'))
   tag_id = Column('tag_id', Integer, ForeignKey('color_code_tags.id'))
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))

class Resource(Base):
   __tablename__ = 'resource'

   # Primary and Foreign Keys
   id = Column(Integer, primary_key=True)
   user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
   original_resource_id = Column(Integer, nullable=True)
   history_id = Column(Integer, nullable=True)
   category_id = Column(Integer, nullable=True)
   folder_id = Column(Integer, nullable=True)
   reference_resource_id = Column(Integer, nullable=True)

   # Basic Info
   name = Column(String(1000), default="")
   description = Column(Text, default="")
   image = Column(String(200), default="")
   
   # Generation Info
   generation_data = Column(Text, default="")
   model_name = Column(String(200), default="")
   model_hash = Column(String(100), default="")
   sampler = Column(String(100), default="Euler")
   sampler_scheduler = Column(String(100), default="")
   prompt = Column(Text, default="")
   negative_prompt = Column(Text, default="")
   
   # Image Properties
   width = Column(Integer, default=512)
   height = Column(Integer, default=512)
   steps = Column(Integer, default=20)
   cfg_scale = Column(Float, default=7.5)
   seed = Column(Integer, default=-1)
   clip_skip = Column(Integer, default=0)
   
   # High Res Settings
   is_highres = Column(Boolean, default=False)
   hr_upscaler = Column(String(300), default="")
   hr_steps = Column(Integer, default=0)
   hr_denoising_strength = Column(Float, default=0)
   hr_upscale_by = Column(Float, default=1)
   
   # Image to Image Settings
   is_i2i = Column(Boolean, default=False)
   resize_mode = Column(Integer, default=0)
   init_image = Column(String(200), default="")
   i2i_denoising_strength = Column(Float, default=0)
   
   # SD Upscale Settings
   is_sd_upscale = Column(Boolean, default=False)
   sd_tile_overlap = Column(Integer, default=0)
   sd_scale_factor = Column(Integer, default=0)
   sd_upscale = Column(String(4000), default="")
   
   # Additional Properties
   uuid = Column(UUID(as_uuid=True), default=uuid.uuid4)
   thumbnail_image = Column(String(200), default="")
   thumbnail_image_512 = Column(String(300), default="")
   is_variation = Column(Boolean, default=False)
   star_rating = Column(Integer, default=0)
   sd_vae = Column(String(200), default="")
   is_bmab = Column(Boolean, default=False)
   is_display = Column(Boolean, default=True)
   is_empty = Column(Boolean, default=False)
   for_testing = Column(Boolean, default=False)
   generate_opt = Column(String(200), default="Upload")
   count_download = Column(Integer, default=0)
   royalty = Column(Float, default=0.0)
   gpt_vision_score = Column(Integer, nullable=True)

   # Slack
   slack_timestamp = Column(Text, default="")

   # Bitcoin
   block_hash = Column(Text, nullable=True)
    
   tag_ids = Column(ARRAY(Integer, dimensions=1), default=lambda: [], nullable=False)
   count_like = Column(Integer, default=0)

   # Timestamps
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))

    # Relationships
   tags = relationship(
      "ColorCodeTags",
      secondary="resource_tag_v2",
      back_populates="resources",
      overlaps="tag_resources"
   )
   likes = relationship("User", secondary=resource_likes, back_populates="liked_resources")
   hidden_by = relationship("User", secondary=resource_hidden_users, back_populates="hidden_resources")
   tabbed_by = relationship("User", secondary=resource_tabbed_users, back_populates="tabbed_resources")
   user = relationship("User", foreign_keys=[user_id])
   #Add new relationships
   placeholder_users = relationship("User", secondary=resource_placeholder, back_populates="placeholder_resources")
   view_status = relationship("User", secondary=resource_view_status, back_populates="viewed_resources")

class ColorCodeTags(Base):
   __tablename__ = 'color_code_tags'

   id = Column(Integer, primary_key=True)
   color_code = Column(String(7))
   tag = Column(String(4000))
   type = Column(String(10), default='normal')
   user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
   
   # Timestamps
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))

    # Relationships
   resources = relationship(
      "Resource",
      secondary="resource_tag_v2",
      back_populates="tags",
      overlaps="tag_resources"
   )
   user = relationship("User", back_populates="color_code_tags")

   def __repr__(self):
      return f"<ColorCodeTag {self.tag}>"

class SdModel(Base):
   __tablename__ = 'sdmodel'

   id = Column(Integer, primary_key=True)
   title = Column(String(200), nullable=False)
   model_name = Column(String(200), nullable=False)
   hash = Column(String(10), index=True, nullable=False)
   sha256 = Column(String(64), nullable=False)
   thumbnail_image = Column(String(200))
   is_active = Column(Boolean, default=False)
   folder_id = Column(Integer, nullable=True)

class Team(Base):
   __tablename__ = 'team'

   id = Column(Integer, primary_key=True)
   create_user_id = Column(String(255), nullable=False)
   nano_id = Column(String(21), nullable=False)
   
   # Timestamps
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))

def setup_database_engine(password, port):
   db_user = "wcidfu"
   db_host = "127.0.0.1"
   db_name = "wcidfu"
   encoded_password = quote_plus(password)
   engine = create_engine(f'postgresql+psycopg2://{db_user}:{encoded_password}@{db_host}:{port}/{db_name}')
   Base.metadata.create_all(engine)
   return engine