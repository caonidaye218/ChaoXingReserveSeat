import os 
import logging
from .encrypt import AES_Encrypt, enc, generate_behavior_analysis
from .reserve import reserve

def get_user_credentials(action):
    """从环境变量中获取用户凭证"""
    if not action:
        return None, None
    try:
        usernames = os.environ['USERNAMES']
        passwords = os.environ['PASSWORDS']
        return usernames, passwords
    except KeyError:
        logging.error("未在 Actions Secrets 中找到 USERNAMES 或 PASSWORDS。")
        return None, None
