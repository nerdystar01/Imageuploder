import re
import piexif
import piexif.helper
import json
from PIL import Image

class PNGInfoAPI:
    # def read_info_from_image(self, image: Image.Image):
    #     IGNORED_INFO_KEYS = {
    #         'jfif', 'jfif_version', 'jfif_unit', 'jfif_density', 'dpi', 'exif',
    #         'loop', 'background', 'timestamp', 'duration', 'progressive', 'progression',
    #         'icc_profile', 'chromaticity', 'photoshop',
    #     }

    #     items = (image.info or {}).copy()
    #     print('아이템 출력')
    #     print(items)
    #     geninfo = items.pop('parameters', None)

    #     if "exif" in items:
    #         exif_data = items.pop("exif")
    #         try:
    #             exif = piexif.load(exif_data)
    #         except OSError:
    #             exif = None
    #         exif_comment = (exif or {}).get("Exif", {}).get(piexif.ExifIFD.UserComment, b'')
    #         try:
    #             exif_comment = piexif.helper.UserComment.load(exif_comment)
    #         except ValueError:
    #             exif_comment = exif_comment.decode('utf8', errors="ignore")
        
    #         if exif_comment:
    #             items['exif comment'] = exif_comment
    #             geninfo = exif_comment
        
    #     elif "comment" in items: # for gif
    #         geninfo = items["comment"].decode('utf8', errors="ignore")    

    #     for field in IGNORED_INFO_KEYS:
    #         items.pop(field, None)

    #     if items.get("Software", None) == "NovelAI":
    #         try:
    #             json_info = json.loads(items["Comment"])
    #             geninfo = f"""{items["Description"]}
    # Negative prompt: {json_info["uc"]}
    # Steps: {json_info["steps"]}, CFG scale: {json_info["scale"]}, Seed: {json_info["seed"]}, Size: {image.width}x{image.height}, Clip skip: 2, ENSD: 31337"""
    #         except Exception:
    #             pass
              
    #     return geninfo

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


        if items.get("Software", None) == "NovelAI":
            try:
                json_info = json.loads(items["Comment"])
                geninfo = f"""{items["Description"]}
Negative prompt: {json_info["uc"]}
Steps: {json_info["steps"]}, CFG scale: {json_info["scale"]}, Seed: {json_info["seed"]}, Size: {image.width}x{image.height}, Clip skip: 2, ENSD: 31337"""
            except Exception as e:
                print('NovelAI 정보 처리 중 오류 발생:', e)
        
        print('최종 geninfo:', geninfo)
        print('최종 geninfo type:', type(geninfo))
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
            print('이미지 확실히 들어오나요?')
            print(type(image))
            geninfo = self.read_info_from_image(image)
            if geninfo == None:
                params = None
                
                return geninfo, params
            else:
                params = self.parse_generation_parameters(geninfo)
            return geninfo, params
        except Exception as e:
            print("Error:", str(e))