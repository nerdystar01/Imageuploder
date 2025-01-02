import json
import zlib
import io
import os
import struct
from PIL import PngImagePlugin
from google.cloud import storage
from model import Resource, SdModel

def upload_to_bucket(blob_name, data, bucket_name):
    current_script_path = os.path.abspath(__file__)
    base_directory = os.path.dirname(current_script_path)
    
    credentials_path = os.path.join(base_directory, 'wcidfu-77f802b00777.json')
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data)
    clean_blob_name = blob_name.replace("_media/", "")

    return clean_blob_name
# geninfo, params 향후 추가
def create_new_resource(session, user_id, original_image, thumbnail_image, thumbnail_image_512, geninfo, params):
    pnginfo = PngImagePlugin.PngInfo()
    generation_data = geninfo
    pnginfo.add_text("parameters", json.dumps(geninfo))

    try:
        new_resource = Resource(user_id=user_id)
        session.add(new_resource)
        session.commit()

        # JSON 청크 데이터 생성
        chunk_data_json = json.dumps({
            "my_uuid": str(new_resource.uuid),
            "id": str(new_resource.id),
            "created_at": str(new_resource.created_at),
            "controlnet_uuid": ""
        })
        chunk_data = chunk_data_json.encode('utf-8')
        chunk_type = b'nsSt'
        crc = zlib.crc32(chunk_type + chunk_data)
        custom_chunk = struct.pack('>I', len(chunk_data)) + chunk_type + chunk_data + struct.pack('>I', crc)
        
        # 원본 이미지에 사용자 정의 청크 삽입
        original_image_buffer = io.BytesIO()
        original_image.save(original_image_buffer, format="PNG", pnginfo= pnginfo)
        original_image_data = original_image_buffer.getvalue()
        iend_index = original_image_data.rfind(b'IEND')
        modified_img_data = original_image_data[:iend_index-4] + custom_chunk + original_image_data[iend_index-4:]

        # 수정된 이미지 데이터를 버킷에 업로드
        modified_blob_name = f"_media/resource/{str(new_resource.uuid)}.png"
        original_image_url = upload_to_bucket(modified_blob_name, modified_img_data, "wcidfu-bucket")
        
        new_resource.image = original_image_url  # 이미지 URL을 리소스 객체에 저장
        session.commit()
        
        # 썸네일 이미지 처리
        thumbnail_image_buffer = io.BytesIO()
        thumbnail_image.save(thumbnail_image_buffer, format="PNG")
        thumbnail_size = max(thumbnail_image.size)
        thumbnail_blob_name = f"_media/resource_thumbnail/{str(new_resource.uuid)}_{'128' if thumbnail_size < 1024 else '512'}.png"
        thumbnail_image_url = upload_to_bucket(thumbnail_blob_name, thumbnail_image_buffer.getvalue(), "wcidfu-bucket")
        
        new_resource.thumbnail_image = thumbnail_image_url  # 썸네일 URL을 리소스 객체에 저장

        # 썸네일 이미지 처리
        thumbnail_image_512_buffer = io.BytesIO()
        thumbnail_image_512.save(thumbnail_image_512_buffer, format="PNG")
        thumbnail_image_512_size = max(thumbnail_image_512.size)
        thumbnail_image_512_blob_name = f"_media/thumbnail_512/{str(new_resource.uuid)}_512.png"
        thumbnail_image_512_url = upload_to_bucket(thumbnail_image_512_blob_name, thumbnail_image_512_buffer.getvalue(), "wcidfu-bucket")
        
        new_resource.thumbnail_image_512 = thumbnail_image_512_url  # 썸네일 URL을 리소스 객체에 저장

        session.commit()
        
        image_path = new_resource.image
        thumbnail_path = new_resource.thumbnail_image
        thumbnail_image_512_path = new_resource.thumbnail_image_512
        resource_uuid = str(new_resource.uuid)

        if geninfo == None and params == None:
            return image_path, thumbnail_path, thumbnail_image_512_path, resource_uuid

        else:    
            if generation_data:
                new_resource.generation_data = generation_data
                session.commit()
            else:
                pass
            
            if "Prompt" in params:
                new_resource.prompt = params["Prompt"]
                session.commit()
            else:
                pass

            if "Negative prompt" in params:
                new_resource.negative_prompt = params["Negative prompt"]
                session.commit()
            else:
                pass

            if "Steps" in params:
                new_resource.steps = params["Steps"]
                session.commit()
            else:
                pass

            if "Sampler" in params:
                new_resource.sampler = params["Sampler"]
                session.commit()
            else:
                pass

            if "CFG scale" in params:
                new_resource.cfg_scale = params["CFG scale"]
                session.commit()
            else:
                pass

            if "Seed" in params:
                new_resource.seed = params["Seed"]
                session.commit()
            else:
                pass

            if "Size" in params:
                size_list = [int(n) for n in params["Size"].split('x')]
                new_resource.height = size_list[0]
                new_resource.width = size_list[1]
                session.commit()
            else:
                pass

            if "Model hash" in params:
                sd_model = session.query(SdModel).filter_by(hash=params["Model hash"]).first()
                if sd_model:
                    new_resource.model_hash = sd_model.hash
                    new_resource.model_name = sd_model.model_name
                else:
                    new_resource.model_hash = params["Model hash"]
                    new_resource.model_name = params["Model"]
            else:
                pass

            if "VAE" in params:
                new_resource.sd_vae = params["VAE"]
                session.commit()
            else:
                pass

            if "Denoising strength" in params:
                new_resource.is_highres = True
                new_resource.hr_denoising_strength = params["Denoising strength"]
                session.commit()

                if "Hires upscale" in params:
                    new_resource.hr_upscale_by = params["Hires upscale"]
                    session.commit()
                if "Hires upscaler" in params:
                    new_resource.hr_upscaler = params["Hires upscaler"]
                    session.commit()
            else:
                pass
        session.commit()
        return image_path, thumbnail_path, thumbnail_image_512_path, resource_uuid
    except Exception as e:
        session.rollback()  # 에러 발생 시 롤백
        raise e
    finally:
        session.close()