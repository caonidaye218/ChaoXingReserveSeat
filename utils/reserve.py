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
    def __init__(self, sleep_time=0.2, max_attempt=50, enable_slider=False, reserve_next_day=False):
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.seat_url = "https://office.chaoxing.com/data/apps/seat/getusedtimes"
        self.token = ""
        self.success_times = 0
        self.fail_dict = []
        self.submit_msg = []
        self.requests = requests.session()
        self.token_pattern = re.compile("token = '(.*?)'")
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

        self.headers = {
            "Pragma": "no-cache",
            "Host": "captcha.chaoxing.com",
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile":"?0",
            "Sec-Ch-Ua-Platform":'"Linux"',
            "Sec-Fetch-Dest":"document",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-Site":"none",
            "Sec-Fetch-User":"?1",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
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

    # login
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
            "refer": "http%3A%2F%2Foffice.chaoxing.com%2F",
            "t": True
        }
        resp = self.requests.post(self.login_url, params=params, verify=False).json()
        if resp.get("status"):
            logging.info(f"User {username} login successfully")
            return True, ""
        else:
            logging.error(f"Login failed: {resp}")
            return False, resp.get("msg2", "未知错误")

    # 获取页面 token
    def _get_page_token(self, url):
        html = self.requests.get(url, verify=False).text
        m = re.search("token: '(.*?)'", html)
        return m.group(1) if m else ""

    # CAPTCHA 核心：先拉取图片和 token，再计算滑块距离，再校验
    def resolve_captcha(self):
        captcha_token, bg, tp = self.get_slide_captcha_data()
        if not captcha_token or not bg or not tp:
            logging.error("Failed to get captcha data; skipping this attempt.")
            return ""

        try:
            x = self.x_distance(bg, tp)
            logging.info(f"Calculated distance: {x}")
        except Exception as e:
            logging.error(f"Distance calc error: {e}")
            return ""

        verify_url = "https://captcha.chaoxing.com/captcha/check/verification/result"
        payload = {
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "token": captcha_token,
            "textClickArr": json.dumps([{"x": x}]),
            "coordinate": json.dumps([]),
            "runEnv": "10",
            "version": "1.1.18"
        }
        resp = self.requests.get(verify_url, params=payload, headers=self.headers, timeout=5)
        data = resp.json()
        logging.info(f"Captcha verify response: {data}")
        if data.get("error") == 0 and data.get("result"):
            return json.loads(data["extraData"])["validate"]
        else:
            logging.error(f"Captcha verification failed: {data}")
            return ""

    # 拉取滑块数据，不再使用 callback 包装
    def get_slide_captcha_data(self):
        url = "https://captcha.chaoxing.com/captcha/get/verification/image"
        timestamp = int(time.time() * 1000)
        cap_key, init_token = generate_captcha_key(timestamp)
        referer = f"https://office.chaoxing.com/front/third/apps/seat/code?id={self.current_roomid}&seatNum={self.current_seat}"
        params = {
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "version": "1.1.18",
            "captchaKey": cap_key,
            "token": init_token
        }
        hdr = dict(self.headers)
        hdr["Referer"] = referer
        resp = self.requests.get(url, params=params, headers=hdr, timeout=5)
        data = resp.json()
        if "imageVerificationVo" not in data:
            logging.error(f"No imageVerificationVo in captcha data: {data}")
            return None, None, None
        vo = data["imageVerificationVo"]
        return data["token"], vo["shadeImage"], vo["cutoutImage"]

    # 计算滑块偏移
    def x_distance(self, bg_url, tp_url):
        import numpy as np
        import cv2

        def cut_slide(buf):
            arr = np.frombuffer(buf, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            part = img[:, :, :3]
            mask = img[:, :, 3]
            mask[mask != 0] = 255
            x, y, w, h = cv2.boundingRect(mask)
            return part[y:y+h, x:x+w]

        hdr = dict(self.headers)
        hdr["Host"] = "captcha-b.chaoxing.com"
        bg = self.requests.get(bg_url, headers=hdr).content
        tp = self.requests.get(tp_url, headers=hdr).content
        bg_img = cv2.imdecode(np.frombuffer(bg, np.uint8), cv2.IMREAD_COLOR)
        tp_img = cut_slide(tp)
        bg_edge = cv2.Canny(bg_img, 100, 200)
        tp_edge = cv2.Canny(tp_img, 100, 200)
        res = cv2.matchTemplate(bg_edge, tp_edge, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        return max_loc[0]

    # 主提交逻辑
    def submit(self, times, roomid, seat_list, action):
        self.current_roomid = roomid
        for seat in seat_list:
            self.current_seat = seat
            attempt = 0
            while attempt < min(self.max_attempt, 50):
                page_token = self._get_page_token(self.url.format(roomid, seat))
                logging.info(f"Page token: {page_token}")
                captcha = self.resolve_captcha() if self.enable_slider else ""
                logging.info(f"Using captcha: {captcha!r}")
                day_offset = 1 if (action or self.reserve_next_day) else 0
                day_str = (datetime.date.today() + datetime.timedelta(days=day_offset)).isoformat()
                params = {
                    "roomId": roomid,
                    "startTime": times[0],
                    "endTime": times[1],
                    "day": day_str,
                    "seatNum": seat,
                    "captcha": captcha,
                    "token": page_token
                }
                params["enc"] = enc(params)
                logging.info(f"Submitting reservation: {params}")
                resp = self.requests.post(self.submit_url, params=params, verify=True).json()
                logging.info(f"Reservation response: {resp}")
                self.submit_msg.append(f"{times[0]}~{times[1]} seat {seat}: {resp}")
                if resp.get("success"):
                    return True
                time.sleep(self.sleep_time)
                attempt += 1
            logging.warning(f"All {attempt} captcha attempts failed for seat {seat}")
        return False

    # 获取 room 列表辅助
    def roomid(self, encode):
        url = f"https://office.chaoxing.com/data/apps/seat/room/list?cpage=1&pageSize=100&deptIdEnc={encode}"
        data = self.requests.get(url).json()
        for i in data["data"]["seatRoomList"]:
            print(f'{i["firstLevelName"]}-{i["secondLevelName"]}-{i["thirdLevelName"]} id={i["id"]}')
