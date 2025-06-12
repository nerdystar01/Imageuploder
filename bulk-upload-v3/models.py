# Standard Library
from datetime import datetime
import uuid
from typing import List
from urllib.parse import quote_plus

# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, Table, UniqueConstraint, func, text
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

# Project Members Association Table
project_members = Table(
   'project_member',
   Base.metadata,
   Column('id', Integer, primary_key=True),
   Column('project_id', Integer, ForeignKey('project.id')),
   Column('user_id', Integer, ForeignKey('user.id')),
   Column('created_at', DateTime, default=lambda: datetime.now(seoul_tz)),
   Column('updated_at', DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz)),
   UniqueConstraint('project_id', 'user_id', name='unique_project_member')
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
   profile_image = Column(String, nullable=True)
   biography = Column(String(3000), nullable=True)

   # Timestamps
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))

   # Relationships
   liked_resources = relationship("Resource", secondary=resource_likes, back_populates="likes")
   hidden_resources = relationship("Resource", secondary=resource_hidden_users, back_populates="hidden_by")
   tabbed_resources = relationship("Resource", secondary=resource_tabbed_users, back_populates="tabbed_by")
   color_code_tags = relationship("ColorCodeTags", back_populates="user")
   placeholder_resources = relationship("Resource", secondary=resource_placeholder, back_populates="placeholder_users")
   viewed_resources = relationship("Resource", secondary=resource_view_status, back_populates="view_status")
   
   # Project relationships
   owned_projects = relationship("Project", back_populates="owner", foreign_keys="Project.owner_id")
   joined_projects = relationship("Project", secondary=project_members, back_populates="members")

class ResourceTagV2(Base):
   __tablename__ = 'resource_tag_v2'
   
   id = Column(Integer, primary_key=True)
   resource_id = Column('resource_id', Integer, ForeignKey('resource.id'))
   tag_id = Column('tag_id', Integer, ForeignKey('color_code_tags.id'))
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))

class Project(Base):
   __tablename__ = 'project'
   
   id = Column(Integer, primary_key=True)
   name = Column(String(20), nullable=False)
   description = Column(Text, default="")
   thumbnail_image = Column(String(200), nullable=True)
   owner_id = Column(Integer, ForeignKey('user.id'), nullable=False)
   is_public = Column(Boolean, default=False)
   
   # Timestamps
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))
   
   # Relationships
   owner = relationship("User", back_populates="owned_projects", foreign_keys=[owner_id])
   members = relationship("User", secondary=project_members, back_populates="joined_projects")
   resources = relationship("Resource", back_populates="project")
   
   def __repr__(self):
      return f"<Project {self.name}>"

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
   # Add project relationship
   project_id = Column(Integer, ForeignKey('project.id'), nullable=True)

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
   thumbnail_image_192 = Column(String(300), default="")
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
   challenge_points = Column(Integer, default=0, server_default=text('0'), nullable=False)

   # Slack
   slack_timestamp = Column(Text, default="")

   # Bitcoin
   block_hash = Column(Text, nullable=True)
    
   tag_ids = Column(ARRAY(Integer, dimensions=1), default=lambda: [], nullable=False)
   count_like = Column(Integer, default=0)

   # Timestamps
   created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
   updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))
   
   # Comfy
   use_workflow_id = Column(Integer, ForeignKey('comfyui_workflow.id'), nullable=True)

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
   project = relationship("Project", back_populates="resources")
   placeholder_users = relationship("User", secondary=resource_placeholder, back_populates="placeholder_resources")
   view_status = relationship("User", secondary=resource_view_status, back_populates="viewed_resources")
   node_options = relationship("NodeOption", back_populates="node_resource")

   # Properties
   @property
   def is_mint(self):
      """
      block_hash 값이 있으면 True를 반환합니다.
      """
      return self.block_hash is not None and self.block_hash != ""

class ComfyUiWorkflow(Base):
    __tablename__ = 'comfy_ui_workflow'
    
    # Primary and Foreign Keys
    id = Column(Integer, primary_key=True)
    creater_id = Column(Integer, ForeignKey('user.id'), nullable=True)
    
    # Basic Info
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    workflow_file = Column(String(500), nullable=True)  # 파일 경로 저장
    
    # Count
    count_like = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
    updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))
    
    # Relationships
    creater = relationship("User", foreign_keys=[creater_id], back_populates="created_workflows")
    node_options = relationship("NodeOption", back_populates="workflow")
    likes = relationship("User", secondary="workflow_likes", back_populates="liked_workflows")
    users = relationship("User", secondary="workflow_users", back_populates="user_workflows")
    used_in_resources = relationship("Resource", back_populates="use_workflow")


class NodeOption(Base):
    __tablename__ = 'node_option'
    
    # Primary and Foreign Keys
    id = Column(Integer, primary_key=True)
    workflow_id = Column(Integer, ForeignKey('comfy_ui_workflow.id'), nullable=True)
    node_resource_id = Column(Integer, ForeignKey('resource.id'), nullable=True)
    
    # Node Info
    node_number = Column(String(100), nullable=False)
    node_type = Column(String(255), nullable=False)
    node_key_1 = Column(String(3000), nullable=True)
    node_value_1 = Column(String(3000), nullable=True)
    node_key_2 = Column(String(3000), nullable=True)
    node_value_2 = Column(String(3000), nullable=True)
    node_content = Column(String(3000), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(seoul_tz))
    updated_at = Column(DateTime, default=lambda: datetime.now(seoul_tz), onupdate=lambda: datetime.now(seoul_tz))
    
    # Relationships
    workflow = relationship("ComfyUiWorkflow", back_populates="node_options")
    node_resource = relationship("Resource", back_populates="node_options")


# Association Tables
workflow_likes = Table('workflow_likes', Base.metadata,
    Column('workflow_id', Integer, ForeignKey('comfy_ui_workflow.id'), primary_key=True),
    Column('user_id', Integer, ForeignKey('user.id'), primary_key=True)
)

workflow_users = Table('workflow_users', Base.metadata,
    Column('workflow_id', Integer, ForeignKey('comfy_ui_workflow.id'), primary_key=True),
    Column('user_id', Integer, ForeignKey('user.id'), primary_key=True)
)

# ManyToMany를 위한 workflow_node_option 테이블
workflow_node_option = Table('workflow_node_option', Base.metadata,
    Column('workflow_id', Integer, ForeignKey('comfy_ui_workflow.id'), primary_key=True),
    Column('node_option_id', Integer, ForeignKey('node_option.id'), primary_key=True)
)


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