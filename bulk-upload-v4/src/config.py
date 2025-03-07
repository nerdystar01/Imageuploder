#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
애플리케이션 설정 파일
"""

import os

# 기본 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
ICONS_DIR = os.path.join(ASSETS_DIR, 'icons')
IMAGES_DIR = os.path.join(ASSETS_DIR, 'images')
STYLES_DIR = os.path.join(ASSETS_DIR, 'styles')

# 자격 증명 및 비밀 파일 디렉토리
CREDENTIALS_DIR = os.path.join(BASE_DIR, 'credentials')