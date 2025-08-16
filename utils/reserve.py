from .encrypt import AES_Encrypt, enc, generate_behavior_analysis
import os
import json
import requests
import re
import time
import logging
import datetime
import random
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=8, enable_slider=False, reserve_next_day=False):
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.seat_select_url = "https://office.chaoxing.com/front/apps/seat/select"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.requests = requests.session()
        
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-G9980 Build/SP1A.210812.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/104.0.5112.97 Mobile Safari/537.36 com.chaoxing.mobile/ChaoXingStudy_3_5.2.2_android_phone_1066_28 (@Kalimdor)_a29ab810366347f49b83b87836d44e58",
            "X-Requested-With": "XMLHttpRequest",
        })

        self.token_pattern = re.compile(r"token\s*=\s*['\"]([^'\"]+)['\"]")
        self.fidenc_pattern = re.compile(r'fidEnc["\']?\s*[:=]\s*["\']([^"\']+)["\']')
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.reserve_next_day = reserve_next_day

    def get_target_date(self, action):
        """确保返回正确的北京时间当天日期"""
        offset_hours = 8 if action else 0
        delta_days = 1 if self.reserve_next_day else 0
        target_time = datetime.datetime.now() + datetime.timedelta(hours=offset_hours, days=delta_days)
        return target_time.strftime("%Y-%m-%d")

    def login(self, username, password):
        try:
            parm = {"fid": -1, "uname": AES_Encrypt(username), "password": AES_Encrypt(password), "refer": "http://office.chaoxing.com/", "t": True}
            r = self.requests.post(self.login_url, data=parm, verify=False, timeout=15)
            obj = r.json()
            if obj.get("status"):
                logging.info(f"用户 {username} 登录成功")
                return True, ""
            logging.error(f"用户 {username} 登录失败: {obj.get('msg2', '未知错误')}")
            return False, obj.get("msg2", "未知错误")
        except Exception as e:
            logging.error(f"登录异常: {e}")
            return False, str(e)

    def _get_page_data(self, roomid, seat_num, day):
        """为每次尝试获取最新的动态 token 和 fidEnc"""
        params = {"id": str(roomid), "day": day, "seatNum": str(seat_num).zfill(3)}
        try:
            resp = self.requests.get(self.seat_select_url, params=params, verify=False, timeout=10)
            html = resp.text
            token_match = self.token_pattern.search(html)
            token = token_match.group(1) if token_match else None
            
            fidenc_match = self.fidenc_pattern.search(html)
            fid_enc = fidenc_match.group(1) if fidenc_match else "92329df6bdb2d3ec" # 提供一个默认值

            if not token:
                logging.warning(f"座位[{seat_num}]未能从页面获取 Token")
            
            return token, fid_enc
        except requests.RequestException as e:
            logging.error(f"获取页面数据失败: {e}")
            return None, None

    def _submit_single_seat(self, times, roomid, seat, action):
        """提交单个座位预约，包含完整的反检测逻辑"""
        day_str = self.get_target_date(action)
        
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"座位[{seat}] 第 {attempt}/{self.max_attempt} 次尝试")
            token, fid_enc = self._get_page_data(roomid, seat, day_str)
            if not token:
                time.sleep(self.sleep_time + random.uniform(0.5, 1.5))
                continue

            parm = {
                "deptIdEnc": "", # 🔥 关键：根据抓包数据，此参数为空
                "roomId": str(roomid), 
                "startTime": str(times[0]), 
                "endTime": str(times[1]),
                "day": day_str, 
                "seatNum": str(seat).zfill(3), 
                "captcha": "", 
                "token": token,
                "behaviorAnalysis": generate_behavior_analysis()
            }
            parm["enc"] = enc(parm)

            # 🔥 关键：构造与抓包数据一致的 Referer
            referer = f"https://office.chaoxing.com/front/apps/seat/select?id={roomid}&day={day_str}&seatNum={seat.zfill(3)}&backLevel=1&fidEnc={fid_enc}"
            submit_headers = self.requests.headers.copy()
            submit_headers['Referer'] = referer

            t
