from utils import AES_Encrypt, enc, generate_captcha_key
import json
import requests
import re
import time
import logging
import datetime
from urllib3.exceptions import InsecureRequestWarning

def get_date(day_offset: int=0):
    today = datetime.datetime.now().date()
    offset_day = today + datetime.timedelta(days=day_offset)
    return offset_day.strftime("%Y-%m-%d")

class reserve:
    def __init__(self,
                 sleep_time=0.2,
                 max_attempt=50,
                 enable_slider=False,
                 reserve_next_day=False,
                 max_captcha_retry=3):
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.token_pattern = re.compile("token = '(.*?)'")
        self.headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        self.login_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X)",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "passport2.chaoxing.com"
        }

        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        self.max_captcha_retry = max_captcha_retry

        self.requests = requests.session()
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    def _get_page_token(self, url):
        r = self.requests.get(url, verify=False)
        m = self.token_pattern.search(r.text)
        return m.group(1) if m else ""

    def get_login_status(self):
        self.requests.headers = self.login_headers
        self.requests.get(self.login_page, verify=False)

    def login(self, username, password):
        u = AES_Encrypt(username)
        p = AES_Encrypt(password)
        params = {
            "fid": -1,
            "uname": u,
            "password": p,
            "refer": "http%3A%2F%2Foffice.chaoxing.com",
            "t": True
        }
        resp = self.requests.post(self.login_url, params=params, verify=False)
        obj = resp.json()
        if obj.get('status'):
            logging.info(f"User {username} login successfully")
            return True, ""
        else:
            logging.error(f"Login failed: {obj.get('msg2')}")
            return False, obj.get('msg2', '')

    def resolve_captcha(self):
        """
        最多尝试 self.max_captcha_retry 次拉取并计算滑块验证码。
        """
        for attempt in range(1, self.max_captcha_retry + 1):
            logging.info(f"Captcha attempt {attempt}/{self.max_captcha_retry}")
            token, bg, tp = self.get_slide_captcha_data()
            if not token or not bg or not tp:
                continue
            try:
                x = self.x_distance(bg, tp)
            except Exception as e:
                logging.error(f"Distance calc error: {e}")
                continue

            params = {
                "callback": "jQuery_cb",
                "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
                "type": "slide",
                "token": token,
                "textClickArr": json.dumps([{"x": x}]),
                "_": int(time.time() * 1000)
            }
            try:
                r = self.requests.get(
                    "https://captcha.chaoxing.com/captcha/check/verification/result",
                    params=params, headers=self.headers, timeout=5)
                data = json.loads(
                    r.text.strip("jQuery_cb(").rstrip(")"))
                validate = json.loads(
                    data.get("extraData", "{}")).get("validate", "")
                if validate:
                    logging.info("Captcha solved")
                    return validate
            except Exception as e:
                logging.error(f"Captcha verify error: {e}")
        logging.warning("Captcha failed all retries")
        return ""

    def get_slide_captcha_data(self):
        t = int(time.time() * 1000)
        key, token = generate_captcha_key(t)
        params = {
            "callback": "jQuery_cb2",
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "captchaKey": key,
            "token": token,
            "_": t
        }
        try:
            r = self.requests.get(
                "https://captcha.chaoxing.com/captcha/get/verification/image",
                params=params,
                headers=self.headers,
                timeout=5)
            data = json.loads(r.text.strip("jQuery_cb2(").rstrip(")"))
            img = data["imageVerificationVo"]
            return data["token"], img["shadeImage"], img["cutoutImage"]
        except Exception as e:
            logging.error(f"Fetch captcha data error: {e}")
            return None, None, None

    def x_distance(self, bg_url, tp_url):
        import numpy as np
        import cv2
        # 下载图片
        hdr = {"Referer": "https://office.chaoxing.com/"}
        bg = self.requests.get(bg_url, headers=hdr).content
        tp = self.requests.get(tp_url, headers=hdr).content

        # 对 tp 做裁剪
        arr = np.frombuffer(tp, np.uint8)
        slide = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
        mask = slide[:, :, 3]
        mask[mask != 0] = 255
        x, y, w, h = cv2.boundingRect(mask)
        tp_img = slide[y:y+h, x:x+w, :3]

        bg_img = cv2.imdecode(np.frombuffer(bg, np.uint8), cv2.IMREAD_COLOR)
        bg_edge = cv2.Canny(bg_img, 100, 200)
        tp_edge = cv2.Canny(tp_img, 100, 200)
        res = cv2.matchTemplate(
            cv2.cvtColor(bg_edge, cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(tp_edge, cv2.COLOR_GRAY2BGR),
            cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        return max_loc[0]

    def submit(self, times, roomid, seat_list, action):
        """
        times: ['09:00','13:00']
        seat_list: ['054','056',...]
        """
        for seat in seat_list:
            attempts = self.max_attempt
            while attempts > 0:
                token = self._get_page_token(self.url.format(roomid, seat))
                captcha = self.resolve_captcha() if self.enable_slider else ""
                success, msg = self.get_submit(
                    self.submit_url, times, token,
                    roomid, seat, captcha, action)
                if success:
                    return True
                # 座位被占用，跳过本时段
                if "已被占用" in msg:
                    logging.info(f"Seat {seat} {times} occupied, skipping.")
                    break
                attempts -= 1
                time.sleep(self.sleep_time)
            # 本座位所有重试完成，继续下一个座位
        return False

    def get_submit(self, url, times, token, roomid, seatid, captcha, action):
        delta = 1 if self.reserve_next_day else 0
        day = datetime.date.today() + datetime.timedelta(days=delta)
        if action:
            day += datetime.timedelta(days=1)
        params = {
            "roomId": roomid,
            "startTime": times[0],
            "endTime": times[1],
            "day": str(day),
            "seatNum": seatid,
            "captcha": captcha,
            "token": token
        }
        params["enc"] = enc(params)
        resp = self.requests.post(url, params=params, verify=True)
        obj = resp.json()
        logging.info(f"submit {times[0]}~{times[1]} seat {seatid}: {obj}")
        return obj.get("success", False), obj.get("msg", "")

# Usage 示例：
# rsv = reserve(enable_slider=True, max_attempt=30)
# rsv.login("账号", "密码")
# rsv.submit(['09:00','13:00'], roomid=6913, seat_list=['054','056'], action=False)
