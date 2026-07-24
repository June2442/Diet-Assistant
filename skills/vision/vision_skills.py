"""
Vision相关Skill示例
用于图片识别、OCR等视觉任务
"""

from typing import Dict, Any, List
import logging
import os

from dotenv import load_dotenv

from skills import BaseSkill

load_dotenv()

logger = logging.getLogger(__name__)


class VisionFoodDetectionSkill(BaseSkill):
    """
    视觉食物识别Skill
    识别图片中的食物名称和基本信息
    """

    def __init__(self):
        super().__init__(name="vision_food_detection", category="vision")
        self.vision_model = None  # OpenAI Vision客户端
        self._init_vision_client()

    def _init_vision_client(self):
        """初始化视觉模型客户端"""
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import AsyncOpenAI
                self.vision_model = AsyncOpenAI(api_key=openai_key)
            except Exception as e:
                logger.warning(f"OpenAI Vision client init failed: {e}")

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行食物识别

        Input context:
            - image_url: 图片URL

        Output:
            - detected_foods: List[{"name": "...", "confidence": 0.9}]
        """
        image_url = context.get("image_url")
        if not image_url:
            return {"error": "No image_url provided"}

        # 使用OpenAI Vision
        if self.vision_model:
            try:
                response = await self.vision_model.chat.completions.create(
                    model=os.getenv("VISION_MODEL", "gpt-4-vision-preview"),
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "识别这张图片中的所有食物。"
                                    "以JSON格式返回：{\"detected_foods\": [{\"name\": \"...\", \"confidence\": 0.9}]}"
                                )
                            },
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }],
                    response_format={"type": "json_object"},
                    max_tokens=300
                )
                import json
                data = json.loads(response.choices[0].message.content)
                detected_foods = data.get("detected_foods", [])
                logger.info(f"Detected {len(detected_foods)} foods in image")
                return {"detected_foods": detected_foods}
            except Exception as e:
                logger.error(f"OpenAI Vision food detection failed: {e}", exc_info=True)

        # 兜底模拟
        detected_foods = [
            {"name": "米饭", "confidence": 0.95},
            {"name": "红烧肉", "confidence": 0.88},
            {"name": "炒青菜", "confidence": 0.92}
        ]
        return {"detected_foods": detected_foods}


class VisionPortionEstimationSkill(BaseSkill):
    """
    视觉份量估算Skill
    估算食物的重量和份量
    """

    def __init__(self):
        super().__init__(name="vision_portion_estimation", category="vision")
        self.vision_model = None
        self._init_vision_client()

    def _init_vision_client(self):
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import AsyncOpenAI
                self.vision_model = AsyncOpenAI(api_key=openai_key)
            except Exception as e:
                logger.warning(f"OpenAI Vision client init failed: {e}")

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        估算食物份量

        Input context:
            - image_url: 图片URL
            - detected_foods: 已识别的食物列表（可选）

        Output:
            - portion_estimates: List[{"food": "...", "weight_g": 150}]
        """
        image_url = context.get("image_url")
        detected_foods = context.get("detected_foods", [])

        if not image_url:
            return {"error": "No image_url provided"}

        # 使用OpenAI Vision估算份量
        if self.vision_model:
            try:
                food_list = ", ".join([f["name"] for f in detected_foods]) or "图片中的食物"
                response = await self.vision_model.chat.completions.create(
                    model=os.getenv("VISION_MODEL", "gpt-4-vision-preview"),
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"估算图片中每种食物的重量（克）。食物：{food_list}。"
                                    "以JSON返回：{\"portion_estimates\": [{\"food\": \"...\", \"weight_g\": 150, \"confidence\": 0.7}]}"
                                )
                            },
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }],
                    response_format={"type": "json_object"},
                    max_tokens=300
                )
                import json
                data = json.loads(response.choices[0].message.content)
                estimates = data.get("portion_estimates", [])
                return {"portion_estimates": estimates}
            except Exception as e:
                logger.error(f"OpenAI Vision portion estimation failed: {e}", exc_info=True)

        # 兜底：默认100g
        portion_estimates = []
        for food in detected_foods:
            portion_estimates.append({
                "food": food["name"],
                "weight_g": 100,
                "confidence": 0.7
            })

        return {"portion_estimates": portion_estimates}


class OCRMenuParserSkill(BaseSkill):
    """
    OCR菜单解析Skill
    从图片中提取菜单文字信息
    """

    def __init__(self):
        super().__init__(name="ocr_menu_parser", category="vision")
        self.ocr_engine = None  # OCR引擎
        self.vision_model = None
        self._init_ocr()

    def _init_ocr(self):
        """初始化OCR引擎"""
        provider = os.getenv("OCR_PROVIDER", "openai").lower()

        if provider == "paddleocr":
            try:
                from paddleocr import PaddleOCR
                self.ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch')
                logger.info("PaddleOCR initialized")
            except Exception as e:
                logger.warning(f"PaddleOCR init failed: {e}")
        elif provider == "openai":
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                try:
                    from openai import AsyncOpenAI
                    self.vision_model = AsyncOpenAI(api_key=openai_key)
                except Exception as e:
                    logger.warning(f"OpenAI OCR init failed: {e}")

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析菜单文字

        Input context:
            - image_url: 图片URL

        Output:
            - menu_text: 提取的文字
            - parsed_dishes: List[{"name": "...", "price": 28}]
        """
        image_url = context.get("image_url")
        if not image_url:
            return {"error": "No image_url provided"}

        # OpenAI Vision OCR
        if self.vision_model:
            try:
                response = await self.vision_model.chat.completions.create(
                    model=os.getenv("VISION_MODEL", "gpt-4-vision-preview"),
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "提取图片中的菜单文字，识别菜品名称和价格。"
                                    "以JSON返回：{\"menu_text\": \"...\", \"parsed_dishes\": [{\"name\": \"...\", \"price\": 28, \"description\": \"\"}]}"
                                )
                            },
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ]
                    }],
                    response_format={"type": "json_object"},
                    max_tokens=500
                )
                import json
                data = json.loads(response.choices[0].message.content)
                return {
                    "menu_text": data.get("menu_text", ""),
                    "parsed_dishes": data.get("parsed_dishes", [])
                }
            except Exception as e:
                logger.error(f"OpenAI OCR failed: {e}", exc_info=True)

        # PaddleOCR本地识别
        if self.ocr_engine:
            try:
                import tempfile
                import urllib.request
                # 下载图片到临时文件
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    urllib.request.urlretrieve(image_url, tmp.name)
                    result = self.ocr_engine.ocr(tmp.name, cls=True)

                texts = []
                for line in result[0]:
                    if line:
                        texts.append(line[1][0])

                menu_text = "\n".join(texts)
                # 简单解析菜品和价格
                parsed_dishes = self._parse_menu_text(menu_text)
                return {"menu_text": menu_text, "parsed_dishes": parsed_dishes}
            except Exception as e:
                logger.error(f"PaddleOCR failed: {e}", exc_info=True)

        # 兜底模拟
        parsed_dishes = [
            {"name": "清蒸鱼", "price": 38, "description": "鲈鱼"},
            {"name": "宫保鸡丁", "price": 28},
            {"name": "麻婆豆腐", "price": 18}
        ]

        return {
            "menu_text": "清蒸鱼 38元\n宫保鸡丁 28元\n麻婆豆腐 18元",
            "parsed_dishes": parsed_dishes
        }

    def _parse_menu_text(self, text: str) -> List[Dict[str, Any]]:
        """从OCR文本中解析菜品和价格"""
        import re
        dishes = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 匹配价格
            price_match = re.search(r'(\d+(?:\.\d+)?)\s*[元块]?', line)
            price = float(price_match.group(1)) if price_match else None
            name = re.sub(r'\d+(?:\.\d+)?\s*[元块]?', '', line).strip()
            if name:
                dishes.append({"name": name, "price": price})
        return dishes
