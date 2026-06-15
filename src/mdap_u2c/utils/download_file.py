from io import BytesIO

import requests
from PIL import Image

from mdap_u2c.config.http_config import get_http_timeout, get_ssl_verify


def get_image_by_url(url):
    # 根据图片url 获取图片对象
    response = requests.get(url, verify=get_ssl_verify(), timeout=get_http_timeout())
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))
    return image
