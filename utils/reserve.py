from .encrypt import AES_Encrypt, enc
import os
import json
import requests
import re
import time
import logging
import datetime
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed

# 禁用SSL警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=3, enable_slider=False, reserve_next_day=False):
        # 登录接口
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        # 新版座位页面
        self.seat_select_url = "https://office.chaoxing.com/front/apps/seat/select"
        # 预约提交接口
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        # HTTP 会话
        self.requests = requests.session()
        
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })

        self.token_patterns = [
            re.compile(r"token\s*=\s*['\"]([^'\"]+)['\"]"),
            re.compile(r'name="token"\s*content="([^"]+)"'),
        ]
        self.deptIdEnc_patterns = [
            re.compile(r'deptIdEnc["\']?\s*[:=]\s*["\']([^"\']+)["\']'),
        ]

        # 运行配置
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        self.default_fid_enc = os.getenv("FID_ENC", "").strip()

    # === 🔥 关键修改：修复日期问题 ===
    def get_target_date(self, action):
        """
        获取目标预约日期。
        此函数确保无论在何处运行，都返回正确的北京时间当天日期。
        """
        # GitHub Actions 使用 UTC 时间，所以我们需要手动加8小时来得到北京时间
        # reserve_next_day 参数决定是否在今天的基础上再加一天
        offset_hours = 8 if action else 0
        delta_days = 1 if self.reserve_next_day else 0
        
        target_time = datetime.datetime.now() + datetime.timedelta(hours=offset_hours, days=delta_days)
        return target_time.strftime("%Y-%m-%d")

    def _get_page_data(self, roomid, seat_num, day):
        """获取 token 与 deptIdEnc"""
        params = {
            "id": str(roomid),
            "day": day,
            "seatNum": str(seat_num).zfill(3),
        }
        try:
            resp = self.requests.get(self.seat_select_url, params=params, verify=False, timeout=15)
            resp.raise_for_status()
            html = resp.text
            token, deptIdEnc = self._extract_token_dept(html)
            return token, deptIdEnc
        except requests.RequestException as e:
            logging.error(f"获取页面数据失败: {e}")
            return None, None

    def _extract_token_dept(self, html: str):
        token, deptIdEnc = None, None
        for p in self.token_patterns:
            m = p.search(html)
            if m: token = m.group(1); break
        for p in self.deptIdEnc_patterns:
            m = p.search(html)
            if m: deptIdEnc = m.group(1); break
        return token, deptIdEnc

    def login(self, username, password):
        try:
            parm = {
                "fid": -1, "uname": AES_Encrypt(username), "password": AES_Encrypt(password),
                "refer": "http%3A%2F%2Foffice.chaoxing.com%2F", "t": True
            }
            r = self.requests.post(self.login_url, data=parm, verify=False, timeout=15)
            r.raise_for_status()
            obj = r.json()
            if obj.get("status", False):
                logging.info(f"用户 {username} 登录成功")
                return True, ""
            return False, obj.get("msg2", "未知登录错误")
        except Exception as e:
            logging.error(f"登录请求异常: {e}")
            return False, str(e)

    def _submit_single_seat(self, times, roomid, seat, action):
        """提交单个座位预约"""
        day_str = self.get_target_date(action)
        
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"座位[{seat}] 第 {attempt}/{self.max_attempt} 次尝试")
            token, deptIdEnc = self._get_page_data(roomid, seat, day_str)
            if not token:
                time.sleep(self.sleep_time)
                continue

            parm = {
                "roomId": str(roomid), "startTime": str(times[0]), "endTime": str(times[1]),
                "day": day_str, "seatNum": str(seat).zfill(3), "captcha": "", "token": token
            }
            parm["enc"] = enc(parm)

            try:
                resp = self.requests.post(self.submit_url, data=parm, verify=False, timeout=15)
                resp.raise_for_status()
                result = resp.json()
                msg = result.get("msg", "")
                logging.info(f"座位[{seat}] 响应: {msg}")
                if result.get("success", False):
                    return True
                if "已被预约" in msg or "不可预约" in msg:
                    return False
            except Exception as e:
                logging.error(f"座位[{seat}] 提交时异常: {e}")
            
            time.sleep(self.sleep_time)
        return False

    def submit(self, times, roomid, seatid_list, action):
        """
        入口函数，使用并行方式尝试预约多个座位。
        """
        if not isinstance(seatid_list, list):
            seatid_list = [seatid_list]

        logging.info(f"开始并行预约，备选座位: {seatid_list}")

        # 使用线程池并行执行
        with ThreadPoolExecutor(max_workers=min(len(seatid_list), 5)) as executor:
            future_to_seat = {
                executor.submit(self._submit_single_seat, times, roomid, seat, action): seat 
                for seat in seatid_list
            }
            
            for future in as_completed(future_to_seat):
                seat = future_to_seat[future]
                try:
                    if future.result():
                        logging.info(f"已抢到座位[{seat}]，停止其他尝试")
                        return True
                except Exception as e:
                    logging.error(f"处理座位[{seat}]时异常: {e}")

        logging.error("所有备选座位均预约失败")
        return False
