from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
from hashlib import md5
import random
import time
import urllib.parse

def AES_Encrypt(data):
    """AES加密函数，用于加密用户名和密码"""
    key = b"u2oh6Vu^HWe4_AES"
    iv = b"u2oh6Vu^HWe4_AES"
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    enctext = base64.b64encode(encrypted_data).decode('utf-8')
    return enctext
    
def enc(submit_info):
    """生成与官方算法一致的 enc 签名"""
    params = {k: v for k, v in submit_info.items() if k not in ['enc', 'behaviorAnalysis'] and v != ''}
    sorted_items = sorted(params.items())
    needed = [f"[{key}={value}]" for key, value in sorted_items]
    
    salt = "%sd`~7^/>N4!Q#){''"
    needed.append(f"[{salt}]")
    
    seq = ''.join(needed)
    return md5(seq.encode("utf-8")).hexdigest()

def generate_behavior_analysis():
    """生成高仿真度的用户行为分析数据"""
    timestamp = int(time.time() * 1000)
    
    # 模拟鼠标移动
    mouse_movements = []
    x, y = random.randint(300, 700), random.randint(100, 300)
    t = timestamp - random.randint(20000, 40000)
    for _ in range(random.randint(15, 30)):
        x += random.randint(-30, 30)
        y += random.randint(-20, 20)
        t += random.randint(50, 200)
        mouse_movements.append(f"{max(0, x)},{max(0, y)},{t}")

    # 模拟鼠标点击
    clicks = [f"{random.randint(200, 800)},{random.randint(150, 500)},{timestamp - random.randint(5000, 15000)}"]

    # 模拟页面聚焦
    focus = f"{timestamp - random.randint(10000, 30000)},{timestamp - random.randint(1000, 5000)}"

    behavior_parts = [
        f"moves={'|'.join(mouse_movements)}",
        f"clicks={'|'.join(clicks)}",
        f"focus={focus}",
        f"ts={timestamp}",
        f"r={random.random():.16f}",
        "v=1.0",
    ]
    
    return urllib.parse.quote_plus('&'.join(behavior_parts))
