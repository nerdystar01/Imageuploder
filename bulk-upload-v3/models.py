from urllib.parse import quote_plus
from datetime import datetime
import uuid
from sqlalchemy import (
    create_engine, 
    Column, 
    Integer, 
    String, 
    Float, 
    Boolean, 
    ForeignKey, 
    DateTime, 
    Text, 
    Table,
    UniqueConstraint,
    Index,
    CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import pytz

seoul_tz = pytz.timezone('Asia/Seoul')
Base = declarative_base()

# Association Tables
resource_likes = Table(
   'resource_likes', 
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id'))
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

resource_view_status = Table(
   'resource_view_status',
   Base.metadata,
   Column('resource_id', Integer, ForeignKey('resource.id')),
   Column('user_id', Integer, ForeignKey('user.id'))
)

class ResourceTagV2(Base):
   __tablename__ = 'resource_tag_v2'
   
   id = Column(Integer, primary_key=True)
   resource_id = Column('resource_id', Integer, ForeignKey('resource.id'))
   tag_id = Column('tag_id', Integer, ForeignKey('color_code_tags.id'))
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))

class ResourcePlaceholder(Base):
   __tablename__ = 'resource_placeholder'
   
   id = Column(Integer, primary_key=True)
   resource_id = Column(Integer, ForeignKey('resource.id'))
   user_id = Column(Integer, ForeignKey('user.id'))
   
   __table_args__ = (
      UniqueConstraint('resource_id', 'user_id', name='unique_resource_placeholder'),
   )

class Resource(Base):
   __tablename__ = 'resource'
   
   # Primary Key
   id = Column(Integer, primary_key=True)
   
   # Foreign Keys with relationships
   user_id = Column(Integer, ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
   user = relationship("User", foreign_keys=[user_id])
   
   original_resource_id = Column(Integer, ForeignKey('resource.id', ondelete='SET NULL'), nullable=True)
   original_resource = relationship("Resource", remote_side=[id], backref="child_set", foreign_keys=[original_resource_id])
   
   reference_resource_id = Column(Integer, ForeignKey('resource.id', ondelete='SET NULL'), nullable=True)
   reference_resource = relationship("Resource", remote_side=[id], backref="referenced_by", foreign_keys=[reference_resource_id])
   
   history_id = Column(Integer, ForeignKey('history.id', ondelete='SET NULL'), nullable=True)
   history = relationship("History")
   
   category_id = Column(Integer, ForeignKey('category.id', ondelete='SET NULL'), nullable=True)
   category = relationship("Category")
   
   folder_id = Column(Integer, ForeignKey('folder.id', ondelete='SET NULL'), nullable=True)
   folder = relationship("Folder")

   # Basic Fields
   name = Column(String(1000), default="")
   description = Column(Text, default="")
   image = Column(String(200), default="")
   
   # Generation Info
   generation_data = Column(Text, default="")
   model_name = Column(String(200), default="")
   model_hash = Column(String(100), default="")
   sampler = Column(String(100), default="Euler")
   sampler_scheduler = Column(String(200), default="", nullable=True)
   prompt = Column(Text, default="")
   negative_prompt = Column(Text, default="")
   
   # Image Properties with Validators
   width = Column(Integer, default=512)
   height = Column(Integer, default=512)
   steps = Column(Integer, default=20)
   cfg_scale = Column(Float, default=7.5)
   seed = Column(Integer, default=-1)
   clip_skip = Column(Integer, nullable=True)
   
   # Validators as CheckConstraints
   __table_args__ = (
      CheckConstraint('width >= 64 AND width <= 2048', name='width_range'),
      CheckConstraint('height >= 64 AND height <= 2048', name='height_range'),
      CheckConstraint('steps >= 1 AND steps <= 40', name='steps_range'),
      CheckConstraint('cfg_scale >= 1 AND cfg_scale <= 30', name='cfg_range'),
      CheckConstraint('seed >= -1 AND seed <= 10000000000', name='seed_range'),
      
      # Indexes
      Index('idx_res_created_desc', created_at.desc()),
      Index('idx_res_created_asc', created_at),
      Index('idx_res_updated_desc', updated_at.desc()),
      Index('idx_res_updated_asc', updated_at),
      Index('idx_res_royalty_updated', royalty.desc(), updated_at.desc(), id.desc()),
      Index('idx_res_rating', star_rating.desc(), id.desc()),
      Index('idx_res_royalty_updated_asc', royalty.desc(), updated_at, id.desc()),
      Index('idx_res_royalty', royalty.desc(), id.desc()),
   )
   
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
   is_display = Column(Boolean, default=True)
   is_empty = Column(Boolean, default=False)
   for_testing = Column(Boolean, default=False)
   sd_vae = Column(String(200), default='')
   is_bmab = Column(Boolean, default=False)
   is_variation = Column(Boolean, default=False)
   star_rating = Column(Integer, default=0)
   count_download = Column(Integer, default=0)
   generate_opt = Column(String(300), default="NONE")
   royalty = Column(Float, default=0.0)
   gpt_vision_score = Column(Integer, nullable=True)
   slack_timestamp = Column(Text, default="")
   
   # UUID and Image Fields
   uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True)
   thumbnail_image = Column(String(200), nullable=True)
   thumbnail_image_512 = Column(String(300), default="")
   
   # Timestamps
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))
   
   # Many-to-Many Relationships
   tags = relationship(
      "ColorCodeTags",
      secondary="resource_tag_v2",
      back_populates="resources"
   )
   likes = relationship(
      "User",
      secondary=resource_likes,
      back_populates="liked_resources"
   )
   hidden_by = relationship(
      "User",
      secondary=resource_hidden_users,
      back_populates="hidden_resources"
   )
   tabbed_by = relationship(
      "User",
      secondary=resource_tabbed_users,
      back_populates="tabbed_resources"
   )
   placeholder = relationship(
      "User",
      secondary="resource_placeholder",
      back_populates="placeholder_resources"
   )
   view_status = relationship(
      "User",
      secondary=resource_view_status,
      back_populates="viewed_resources"
   )

   @property
   def like_count(self):
      return len(self.likes)

class ColorCodeTags(Base):
   __tablename__ = 'color_code_tags'
   
   id = Column(Integer, primary_key=True)
   color_code = Column(String(7))
   tag = Column(String(4000))
   type = Column(String(10), default='normal')
   user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
   
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))
   
   resources = relationship(
      "Resource",
      secondary="resource_tag_v2",
      back_populates="tags"
   )
   user = relationship("User", back_populates="color_code_tags")

class User(Base):
   __tablename__ = 'user'
   
   id = Column(Integer, primary_key=True)
   email = Column(String, unique=True, nullable=False)
   folder_id = Column(Integer, nullable=True)
   json_file = Column(String, nullable=True)
   nano_id = Column(String(21), unique=True, nullable=True)
   
   # Relationships
   liked_resources = relationship("Resource", secondary=resource_likes, back_populates="likes")
   hidden_resources = relationship("Resource", secondary=resource_hidden_users, back_populates="hidden_by")
   tabbed_resources = relationship("Resource", secondary=resource_tabbed_users, back_populates="tabbed_by")
   placeholder_resources = relationship("Resource", secondary="resource_placeholder", back_populates="placeholder")
   viewed_resources = relationship("Resource", secondary=resource_view_status, back_populates="view_status")
   color_code_tags = relationship("ColorCodeTags", back_populates="user")

def setup_database_engine(password, port):
   db_user = "wcidfu"
   db_host = "127.0.0.1"
   db_name = "wcidfu"
   encoded_password = quote_plus(password)
   engine = create_engine(f'postgresql+psycopg2://{db_user}:{encoded_password}@{db_host}:{port}/{db_name}')
   Base.metadata.create_all(engine)
   return engine