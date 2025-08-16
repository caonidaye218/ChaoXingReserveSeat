from .encrypt import AES_Encrypt, enc, generate_behavior_analysis
import os
import json
import requests
import re
import time
import logging
import datetime
import pytz
import random
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed

# 禁用SSL警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=3, enable_slider=False, reserve_next_day=False):
        # 接口URL
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.seat_select_url = "https://office.chaoxing.com/front/apps/seat/select"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.captcha_conf_url = "https://captcha.chaoxing.com/captcha/get/conf"
        self.captcha_image_url = "https://captcha.chaoxing.com/captcha/get/verification/image"
        self.captcha_check_url = "https://captcha.chaoxing.com/captcha/check/verification/result"

        # 主HTTP会话
        self.requests = requests.session()
        
        # 🔥 关键：更新为模拟真实浏览器的请求头
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        })

        # 正则表达式
        self.token_pattern = re.compile(r"token\s*=\s*['\"]([^'\"]+)['\"]")
        self.deptIdEnc_pattern = re.compile(r'deptIdEnc["\']?\s*[:=]\s*["\']([^"\']+)["\']')

        # 运行配置
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        self.beijing_tz = pytz.timezone('Asia/Shanghai')
        self.default_fid_enc = os.getenv("FID_ENC", "").strip()

    def get_target_date(self):
        """根据配置获取目标预约日期"""
        now = datetime.datetime.now(self.beijing_tz)
        delta_days = 1 if self.reserve_next_day else 0
        return (now + datetime.timedelta(days=delta_days)).strftime("%Y-%m-%d")

    def login(self, username, password):
        """用户登录"""
        try:
            parm = {
                "fid": -1,
                "uname": AES_Encrypt(username),
                "password": AES_Encrypt(password),
                "refer": "http%3A%2F%2Foffice.chaoxing.com%2F",
                "t": True
            }
            headers = self.requests.headers.copy()
            headers.update({
                "Host": "passport2.chaoxing.com",
                "Origin": "https://passport2.chaoxing.com",
                "Referer": "https://passport2.chaoxing.com/login"
            })
            r = self.requests.post(self.login_url, data=parm, headers=headers, verify=False, timeout=15)
            r.raise_for_status()
            obj = r.json()
            if obj.get("status", False):
                return (True, "")
            return (False, obj.get("msg2", "未知登录错误"))
        except Exception as e:
            logging.error(f"登录请求异常: {e}")
            return (False, str(e))

    def _get_page_data(self, roomid, seat_num, day):
        """获取预约页面的 token 和 deptIdEnc"""
        try:
            params = {
                "id": str(roomid),
                "day": day,
                "seatNum": str(seat_num).zfill(3),
            }
            headers = self.requests.headers.copy()
            headers.update({
                "Host": "office.chaoxing.com",
                "Referer": "https://office.chaoxing.com/"
            })
            resp = self.requests.get(self.seat_select_url, params=params, headers=headers, verify=False, timeout=15)
            resp.raise_for_status()
            html = resp.text
            
            token_match = self.token_pattern.search(html)
            token = token_match.group(1) if token_match else None
            
            dept_match = self.deptIdEnc_pattern.search(html)
            deptIdEnc = dept_match.group(1) if dept_match else self.default_fid_enc

            if token:
                logging.info(f"✅ 成功获取页面 Token: {token[:16]}...")
                return token, deptIdEnc
            return None, None
        except Exception as e:
            logging.warning(f"获取页面数据失败: {e}")
            return None, None

    def _get_captcha_validate(self):
        """获取一个模拟的验证码 validate 值"""
        if not self.enable_slider:
            return ""
        # 这是一个简化的模拟，返回一个看起来合法的格式
        timestamp = int(time.time() * 1000)
        random_part = random.randint(1000000000, 9999999999)
        return f"validate_{timestamp}_{random_part}"

    def _submit_single_seat(self, times, roomid, seat, action):
        """
        重构的单座位提交逻辑，每次都尝试获取新数据
        """
        day_str = self.get_target_date()
        
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"🎯 座位[{seat}] 第 {attempt}/{self.max_attempt} 次尝试")
            
            try:
                # 1. 获取页面数据
                token, deptIdEnc = self._get_page_data(roomid, seat, day_str)
                if not token:
                    logging.warning("获取Token失败，跳过本次尝试")
                    time.sleep(1)
                    continue

                # 2. 获取验证码
                captcha_validate = self._get_captcha_validate()
                
                # 3. 构建提交参数
                parm = {
                    "roomId": str(roomid),
                    "startTime": str(times[0]),
                    "endTime": str(times[1]),
                    "day": day_str,
                    "seatNum": str(seat).zfill(3),
                    "captcha": captcha_validate,
                    "token": token,
                    "deptIdEnc": deptIdEnc,
                    "behaviorAnalysis": generate_behavior_analysis(),
                    "enc": ""
                }
                parm["enc"] = enc(parm)
                
                # 4. 设置提交请求头
                submit_headers = self.requests.headers.copy()
                submit_headers.update({
                    "Host": "office.chaoxing.com",
                    "Origin": "https://office.chaoxing.com",
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": f"{self.seat_select_url}?id={roomid}&day={day_str}&seatNum={parm['seatNum']}",
                })
                
                # 5. 提交请求
                resp = self.requests.post(self.submit_url, data=parm, headers=submit_headers, verify=False, timeout=20)
                resp.raise_for_status()

                # 6. 解析响应
                result = resp.json()
                msg = result.get("msg", "")
                logging.info(f"📝 座位[{seat}] 服务器响应: {msg}")

                if result.get("success", False):
                    logging.info(f"🎉 座位[{seat}] 预约成功！")
                    return True
                
                # 7. 智能错误处理
                if "人数过多" in msg or "系统繁忙" in msg:
                    logging.warning(f"⏰ 遇到高峰，随机等待后重试...")
                    time.sleep(random.uniform(self.sleep_time, self.sleep_time + 2))
                elif "已被预约" in msg or "不可预约" in msg:
                    logging.error(f"❌ 座位[{seat}] 明确失败，不再尝试: {msg}")
                    return False # 这是确定性失败，直接返回
                else:
                    time.sleep(self.sleep_time)

            except Exception as e:
                logging.error(f"🌐 座位[{seat}] 请求异常: {e}")
                time.sleep(random.uniform(1, 3))

        logging.error(f"💥 座位[{seat}] 在 {self.max_attempt} 次尝试后仍然失败")
        return False

    def submit(self, times, roomid, seatid, action):
        """并发提交多个座位号"""
        seatid_list = seatid if isinstance(seatid, list) else [seatid]
        
        logging.info(f"🎯 开始并发预约，目标座位: {seatid_list}")
        
        # 使用线程池并发尝试所有候选座位
        with ThreadPoolExecutor(max_workers=min(len(seatid_list), 3)) as executor:
            future_to_seat = {
                executor.submit(self._submit_single_seat, times, roomid, seat, action): seat 
                for seat in seatid_list
            }
            
            for future in as_completed(future_to_seat):
                try:
                    if future.result():
                        # 一旦有一个成功，就认为整个任务成功
                        return True
                except Exception as e:
                    seat = future_to_seat[future]
                    logging.error(f"💥 处理座位[{seat}]时发生线程异常: {e}")

        logging.error("😞 所有候选座位均预约失败")
        return False
