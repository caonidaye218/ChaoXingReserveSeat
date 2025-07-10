from utils import AES_Encrypt, enc, generate_captcha_key
import json
import requests
import re
import time
import logging
import datetime
from urllib3.exceptions import InsecureRequestWarning

def get_date(day_offset: int = 0):
    today = datetime.datetime.now().date()
    offset_day = today + datetime.timedelta(days=day_offset)
    return offset_day.strftime("%Y-%m-%d")

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=50, enable_slider=False, reserve_next_day=False):
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.requests = requests.session()
        self.headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "Pragma": 'no-cache',
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Linux"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }
        self.login_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) "
                          "AppleWebKit/603.1.3 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "passport2.chaoxing.com"
        }
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    def _get_page_token(self, url):
        response = self.requests.get(url=url, verify=False)
        html = response.content.decode('utf-8', errors='ignore')
        tokens = re.findall(r"token: '(.*?)'", html)
        return tokens[0] if tokens else ""

    def get_login_status(self):
        self.requests.headers = self.login_headers
        self.requests.get(url=self.login_page, verify=False)

    def login(self, username, password):
        username_enc = AES_Encrypt(username)
        password_enc = AES_Encrypt(password)
        params = {
            "fid": -1,
            "uname": username_enc,
            "password": password_enc,
            "refer": "http%3A%2F%2Foffice.chaoxing.com%2Ffront%2Fthird%2Fapps%2Fseat%2Fcode",
            "t": True
        }
        resp = self.requests.post(url=self.login_url, params=params, verify=False)
        result = resp.json()
        if result.get('status'):
            logging.info(f"User {username} login successfully")
            return True, ''
        else:
            logging.error(f"User {username} login failed: {result.get('msg2')}")
            return False, result.get('msg2')

    def roomid(self, encode):
        url = f"https://office.chaoxing.com/data/apps/seat/room/list?cpage=1&pageSize=100&deptIdEnc={encode}"
        data = self.requests.get(url=url).json().get('data', {})
        for room in data.get('seatRoomList', []):
            print(f"{room['firstLevelName']}-{room['secondLevelName']}-{room['thirdLevelName']} id={room['id']}")

    def resolve_captcha(self, roomid, seatid):
        logging.info("Start to resolve captcha token")
        captcha_token, bg, tp = self.get_slide_captcha_data(roomid, seatid)
        if not captcha_token or not bg or not tp:
            logging.error("Failed to get captcha data; skipping this attempt.")
            return ""
        # Use the actual seat code page as referer for captcha check
        referer = self.url.format(roomid, seatid)
        self.headers['Referer'] = referer
        logging.info(f"Captcha small URL: {tp}, big URL: {bg}")
        try:
            x = self.x_distance(bg, tp)
            logging.info(f"Calculated captcha offset: {x}")
        except Exception as e:
            logging.error(f"Error computing x distance: {e}")
            x = 0
        params = {
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "token": captcha_token,
            "textClickArr": json.dumps([{"x": x}]),
            "coordinate": json.dumps([]),
            "runEnv": "10",
            "version": "1.1.18",
            "_": int(time.time() * 1000)
        }
        try:
            resp = self.requests.get(
                'https://captcha.chaoxing.com/captcha/check/verification/result',
                params=params, headers=self.headers, timeout=5
            )
            text = re.sub(r'^\w+\(', '', resp.text)
            text = re.sub(r'\)$', '', text)
            data = json.loads(text)
            logging.info(f"Captcha check response: {data}")
            return json.loads(data.get('extraData', '{}')).get('validate', '')
        except Exception as e:
            logging.error(f"Error during captcha verification: {e}")
            return ""

    def get_slide_captcha_data(self, roomid, seatid):
        url = "https://captcha.chaoxing.com/captcha/get/verification/image"
        timestamp = int(time.time() * 1000)
        captcha_key, token = generate_captcha_key(timestamp)
        referer = self.url.format(roomid, seatid)
        params = {
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "version": "1.1.18",
            "captchaKey": captcha_key,
            "token": token,
            "referer": referer,
            "_": timestamp,
            "d": "a",
            "b": "a"
        }
        try:
            resp = self.requests.get(url, params=params, headers=self.headers, timeout=5)
            # strip callback wrapper
            raw = re.sub(r'^\w+\(', '', resp.text)
            raw = re.sub(r'\)$', '', raw)
            data = json.loads(raw)
            if 'imageVerificationVo' not in data:
                logging.error(f"No imageVerificationVo in captcha data: {data}")
                return None, None, None
            vo = data['imageVerificationVo']
            return data.get('token'), vo.get('shadeImage'), vo.get('cutoutImage')
        except Exception as e:
            logging.error(f"Error fetching captcha data: {e}")
            return None, None, None

    def x_distance(self, bg_url, tp_url):
        import numpy as np
        import cv2
        def crop_slider(slider_bytes):
            arr = np.frombuffer(slider_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            mask = img[:, :, 3]
            mask[mask != 0] = 255
            x, y, w, h = cv2.boundingRect(mask)
            return img[y:y+h, x:x+w, :3]
        # download images
        headers = self.headers.copy()
        headers['Host'] = 'captcha-b.chaoxing.com'
        bg_bytes = self.requests.get(bg_url, headers=headers).content
        tp_bytes = self.requests.get(tp_url, headers=headers).content
        bg_img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
        tp_img = crop_slider(tp_bytes)
        # edge detection
        bg_edge = cv2.Canny(bg_img, 100, 200)
        tp_edge = cv2.Canny(tp_img, 100, 200)
        res = cv2.matchTemplate(bg_edge, tp_edge, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        return max_loc[0]

    def submit(self, times, roomid, seatid, action):
        for seat in seatid:
            attempt = 0
            while attempt < self.max_attempt:
                token = self._get_page_token(self.url.format(roomid, seat))
                logging.info(f"Page token: {token}")
                captcha = self.resolve_captcha(roomid, seat) if self.enable_slider else ""
                logging.info(f"Using captcha: {captcha}")
                success = self.get_submit(
                    self.submit_url, times, token, roomid, seat, captcha, action
                )
                if success:
                    return True
                attempt += 1
                time.sleep(self.sleep_time)
            logging.warning(f"All {self.max_attempt} captcha attempts failed for seat {seat}")
        return False

    def get_submit(self, url, times, token, roomid, seatid, captcha, action=False):
        delta = 1 if (action or self.reserve_next_day) else 0
        day = datetime.date.today() + datetime.timedelta(days=delta)
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
        logging.info(f"Submitting reservation: {params}")
        resp = self.requests.post(url=url, params=params, verify=True)
        result = resp.json()
        logging.info(f"Reservation response: {result}")
        return result.get('success', False)
