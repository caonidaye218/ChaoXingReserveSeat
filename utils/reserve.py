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
        
        # 使用从真实手机APP提取的请求头
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-G9980 Build/SP1A.210812.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/104.0.5112.97 Mobile Safari/537.36 com.chaoxing.mobile/ChaoXingStudy_3_5.2.2_android_phone_1066_28 (@Kalimdor)_a29ab810366347f49b83b87836d44e58",
            "X-Requested-With": "XMLHttpRequest",
        })

        self.token_pattern = re.compile(r"token\s*=\s*['\"]([^'\"]+)['\"]")
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

    def _get_page_token(self, roomid, seat_num, day):
        """为每次尝试获取最新的动态 token"""
        params = {"id": str(roomid), "day": day, "seatNum": str(seat_num).zfill(3)}
        try:
            resp = self.requests.get(self.seat_select_url, params=params, verify=False, timeout=10)
            match = self.token_pattern.search(resp.text)
            if match:
                return match.group(1)
            logging.warning(f"座位[{seat_num}]未能从页面获取 Token")
            return None
        except requests.RequestException as e:
            logging.error(f"获取 Token 失败: {e}")
            return None

    def _submit_single_seat(self, times, roomid, seat, action):
        """提交单个座位预约，包含完整的反检测逻辑"""
        day_str = self.get_target_date(action)
        
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"座位[{seat}] 第 {attempt}/{self.max_attempt} 次尝试")
            token = self._get_page_token(roomid, seat, day_str)
            if not token:
                time.sleep(self.sleep_time + random.uniform(0.5, 1.5)) # 获取失败则增加等待时间
                continue

            parm = {
                "roomId": str(roomid), "startTime": str(times[0]), "endTime": str(times[1]),
                "day": day_str, "seatNum": str(seat).zfill(3), "captcha": "", "token": token,
                "behaviorAnalysis": generate_behavior_analysis() # 每次都生成新的行为数据
            }
            parm["enc"] = enc(parm)

            try:
                resp = self.requests.post(self.submit_url, data=parm, verify=False, timeout=10)
                result = resp.json()
                msg = result.get("msg", "")
                logging.info(f"座位[{seat}] 响应: {msg}")

                if result.get("success"):
                    return True
                
                # 智能重试逻辑
                if "人数过多" in msg or "请5分钟后" in msg:
                    wait = random.uniform(1, 3)
                    logging.warning(f"遇到“人数过多”，随机等待 {wait:.1f} 秒后重试...")
                    time.sleep(wait)
                elif "已被预约" in msg or "不可预约" in msg:
                    logging.error(f"座位[{seat}]明确失败，放弃该座位。")
                    return False # 明确失败，无需重试
                else:
                    time.sleep(self.sleep_time) # 其他错误，常规等待
            except Exception as e:
                logging.error(f"座位[{seat}] 提交时异常: {e}")
                time.sleep(self.sleep_time + random.uniform(0.5, 1.5))
                
        return False

    def submit(self, times, roomid, seatid_list, action):
        """安全并行抢座入口"""
        if not isinstance(seatid_list, list):
            seatid_list = [seatid_list]

        logging.info(f"开始并行预约，备选座位: {seatid_list}")

        with ThreadPoolExecutor(max_workers=min(len(seatid_list), 5)) as executor:
            future_to_seat = {
                executor.submit(self._submit_single_seat, times, roomid, seat, action): seat 
                for seat in seatid_list
            }
            for future in as_completed(future_to_seat):
                if future.result():
                    logging.info(f"已抢到座位[{future_to_seat[future]}]，停止其他并行尝试")
                    # 取消其他还在运行的任务
                    for f in future_to_seat:
                        if not f.done():
                            f.cancel()
                    return True
        
        logging.error(f"时间段 {times} 的所有备选座位均预约失败")
        return False
