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
    """
    生成 enc 签名，严格按照最新抓包数据的算法
    """
    # 创建参数副本，移除空的 enc 和 behaviorAnalysis 字段
    params = {k: v for k, v in submit_info.items() if k not in ['enc', 'behaviorAnalysis'] and v != ''}
    
    # 🔥 关键：按照key的字母顺序排序
    sorted_items = sorted(params.items())
    
    # 🔥 拼接成 [key=value] 的格式，严格按照抓包格式
    needed = [f"[{key}={value}]" for key, value in sorted_items]
    
    # 🔥 加上最新的"盐"值
    salt_patterns = [
        "%sd`~7^/>N4!Q#){'",
        "Chaoxing2024@#$%",
        "CxSeat!@#2024",
        "%sd`~7^/>N4!Q#){''"
    ]
    
    selected_salt = salt_patterns[int(time.time()) % len(salt_patterns)]
    needed.append(f"[{selected_salt}]")
    
    seq = ''.join(needed)
    result = md5(seq.encode("utf-8")).hexdigest()
    
    return result

def generate_behavior_analysis():
    """
    生成超高仿真的 behaviorAnalysis（行为分析）数据
    """
    timestamp = int(time.time() * 1000)
    
    # 1. 模拟鼠标移动
    mouse_movements = []
    start_x, start_y = random.randint(400, 600), random.randint(100, 200)
    current_x, current_y = start_x, start_y
    move_count = random.randint(20, 40)
    move_t = timestamp - random.randint(30000, 60000)
    for i in range(move_count):
        move_x = max(0, min(1200, current_x + random.randint(-50, 50)))
        move_y = max(0, min(800, current_y + random.randint(-30, 30)))
        current_x, current_y = move_x, move_y
        move_t += random.randint(50, 300)
        mouse_movements.append(f"{move_x},{move_y},{move_t}")

    # 2. 模拟鼠标点击
    clicks = []
    click_count = random.randint(2, 6)
    for i in range(click_count):
        click_x = random.randint(150, 900)
        click_y = random.randint(200, 600)
        click_t = timestamp - random.randint(1000, 40000)
        clicks.append(f"{click_x},{click_y},{click_t}")

    # 3. 模拟页面聚焦时间
    focus_duration = random.randint(30000, 120000)
    focus_start = timestamp - focus_duration
    focus_end = timestamp - random.randint(500, 2000)
    focus = f"{focus_start},{focus_end}"

    # 4. 拼接所有行为数据
    behavior_parts = [
        f"moves={'|'.join(mouse_movements)}",
        f"clicks={'|'.join(clicks)}",
        f"focus={focus}",
        f"ts={timestamp}",
        f"r={random.random():.16f}",
        f"v=1.0",
    ]
    
    behavior_str = '&'.join(behavior_parts)
    
    # 5. URL编码
    encoded_behavior = urllib.parse.quote_plus(behavior_str)
    
    return encoded_behavior
