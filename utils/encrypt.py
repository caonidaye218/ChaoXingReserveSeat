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
    """生成包含多种行为的、高仿真度的用户行为分析数据"""
    timestamp = int(time.time() * 1000)
    
    # 1. 模拟鼠标移动轨迹 (moves)
    mouse_movements = []
    x, y = random.randint(300, 700), random.randint(100, 300)
    t = timestamp - random.randint(20000, 40000)
    for _ in range(random.randint(25, 45)):
        x += random.randint(-50, 50)
        y += random.randint(-40, 40)
        t += random.randint(40, 200)
        mouse_movements.append(f"{max(0, x)},{max(0, y)},{t}")

    # 2. 模拟鼠标点击 (clicks)
    clicks = []
    for _ in range(random.randint(3, 6)):
        clicks.append(f"{random.randint(100, 900)},{random.randint(100, 600)},{timestamp - random.randint(3000, 35000)}")

    # 3. 模拟页面聚焦时间 (focus)
    focus = f"{timestamp - random.randint(25000, 60000)},{timestamp - random.randint(1000, 5000)}"

    # 4. 模拟页面滚动 (scrolls)
    scrolls = []
    scroll_y = 0
    scroll_t = timestamp - random.randint(15000, 30000)
    for _ in range(random.randint(2, 5)):
        scroll_delta = random.randint(50, 200)
        scroll_y += scroll_delta
        scroll_t += random.randint(1000, 3000)
        scrolls.append(f"0,{scroll_delta},{scroll_t}")

    # 5. 拼接所有行为数据
    behavior_parts = [
        f"moves={'|'.join(mouse_movements)}",
        f"clicks={'|'.join(clicks)}",
        f"scrolls={'|'.join(scrolls)}",
        f"focus={focus}",
        f"ts={timestamp}",
        f"r={random.random():.16f}",
        "v=1.0",
    ]
    
    # 6. URL编码
    return urllib.parse.quote_plus('&'.join(behavior_parts))
