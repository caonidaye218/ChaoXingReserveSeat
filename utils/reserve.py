#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import re
import time
import datetime
import logging
import requests
from utils import AES_Encrypt, enc, generate_captcha_key
from urllib3.exceptions import InsecureRequestWarning


def get_date(day_offset: int = 0):
    today = datetime.datetime.now().date()
    offset_day = today + datetime.timedelta(days=day_offset)
    return offset_day.strftime("%Y-%m-%d")


class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=50, enable_slider=False, reserve_next_day=False):
        # 登录与请求 URL 配置
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.requests = requests.session()
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        
        # HEADERS 设置
        self.headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "Pragma": 'no-cache',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)'
        }
        self.login_headers = {
            "Host": "passport2.chaoxing.com",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X)"
        }
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    def _get_page_token(self, url):
        resp = self.requests.get(url, verify=False)
        html = resp.text
        match = re.search("token: '(.*?)'", html)
        return match.group(1) if match else ''

    def get_login_status(self):
        self.requests.headers = self.login_headers
        self.requests.get(self.login_page, verify=False)

    def login(self, username, password):
        u = AES_Encrypt(username)
        p = AES_Encrypt(password)
        params = {
            'fid': -1,
            'uname': u,
            'password': p,
            'refer': 'http://office.chaoxing.com',
            't': True
        }
        r = self.requests.post(self.login_url, params=params, verify=False)
        obj = r.json()
        if obj.get('status'):
            logging.info(f"User {username} login successfully")
            return True, ''
        else:
            logging.error(f"Login failed: {obj}")
            return False, obj.get('msg2', '')

    def get_slide_captcha_data(self):
        t = int(time.time() * 1000)
        ck, tk = generate_captcha_key(t)
        params = {
            'callback': 'jQuery_cb2',
            'captchaId': '42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1',
            'type': 'slide',
            'captchaKey': ck,
            'token': tk,
            '_': t
        }
        try:
            r = self.requests.get(
                'https://captcha.chaoxing.com/captcha/get/verification/image',
                params=params,
                headers=self.headers,
                timeout=5)
            text = r.text
            start = text.find('{')
            end = text.rfind('}')
            raw = json.loads(text[start:end+1])

            # 多路径查找 imageVerificationVo
            vo = None
            if 'imageVerificationVo' in raw:
                vo = raw['imageVerificationVo']
            elif isinstance(raw.get('data'), dict) and 'imageVerificationVo' in raw['data']:
                vo = raw['data']['imageVerificationVo']
            elif isinstance(raw.get('data'), dict) and isinstance(raw['data'].get('result'), dict) and \
                 'imageVerificationVo' in raw['data']['result']:
                vo = raw['data']['result']['imageVerificationVo']

            if not vo:
                logging.error(f"Unexpected captcha JSON: {raw}")
                raise KeyError('no imageVerificationVo in response')

            shade = vo.get('shadeImage') or vo.get('bg')
            cutout = vo.get('cutoutImage') or vo.get('tp')
            return raw.get('token'), shade, cutout

        except Exception as e:
            logging.error(f"Fetch captcha data error: {e}")
            return None, None, None

    def resolve_captcha(self):
        logging.info("Start captcha resolution")
        for attempt in range(1, 4):
            logging.info(f"Captcha attempt {attempt}/3")
            c_token, bg, tp = self.get_slide_captcha_data()
            if not c_token or not bg or not tp:
                continue
            try:
                x = self.x_distance(bg, tp)
                logging.info(f"Captcha distance: {x}")
            except Exception as e:
                logging.error(f"Distance calc error: {e}")
                continue
            params = {
                'captchaId': '42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1',
                'token': c_token,
                'textClickArr': json.dumps([{'x': x}]),
                '_': int(time.time()*1000)
            }
            try:
                resp = self.requests.get(
                    'https://captcha.chaoxing.com/captcha/check/verification/result',
                    params=params,
                    headers=self.headers,
                    timeout=5)
                txt = resp.text
                txt = txt[txt.find('(')+1:txt.rfind(')')]
                data = json.loads(txt)
                val = json.loads(data.get('extraData','{}')).get('validate','')
                if val:
                    return val
            except Exception as e:
                logging.error(f"Verify captcha error: {e}")
        logging.warning("Captcha failed all retries")
        return ''

    def x_distance(self, bg_url, tp_url):
        import cv2
        import numpy as np
        # 下载图片
        h = self.requests.get(bg_url, headers=self.headers).content
        t = self.requests.get(tp_url, headers=self.headers).content
        bg = cv2.imdecode(np.frombuffer(h, np.uint8), cv2.IMREAD_COLOR)
        # 处理滑块
        arr = np.frombuffer(t, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
        mask = img[:,:,3]
        mask[mask!=0]=255
        x,y,w,hh = cv2.boundingRect(mask)
        tp = img[y:y+hh, x:x+w, :3]
        # 匹配
        bg_edge = cv2.Canny(bg,100,200)
        tp_edge = cv2.Canny(tp,100,200)
        res = cv2.matchTemplate(bg_edge, tp_edge, cv2.TM_CCOEFF_NORMED)
        _,_,_,max_loc = cv2.minMaxLoc(res)
        return max_loc[0]

    def submit(self, times, roomid, seatids, action):
        for seat in seatids:
            suc = False
            while not suc and self.max_attempt>0:
                page_token = self._get_page_token(self.url.format(roomid, seat))
                logging.info(f"Get page token: {page_token}")
                captcha = self.resolve_captcha() if self.enable_slider else ''
                suc = self._do_submit(times, roomid, seat, page_token, captcha, action)
                if suc:
                    return True
                time.sleep(self.sleep_time)
                self.max_attempt -= 1
        return False

    def _do_submit(self, times, roomid, seatid, token, captcha, action):
        delta = 1 if self.reserve_next_day else 0
        day = datetime.date.today() + datetime.timedelta(days=delta + (1 if action else 0))
        params = {
            'roomId': roomid,
            'startTime': times[0],
            'endTime': times[1],
            'day': str(day),
            'seatNum': seatid,
            'captcha': captcha,
            'token': token
        }
        params['enc'] = enc(params)
        r = self.requests.post(self.submit_url, params=params, verify=True)
        res = r.json()
        logging.info(f"submit {times[0]}~{times[1]} seat {seatid}: {res}")
        return res.get('success', False)
