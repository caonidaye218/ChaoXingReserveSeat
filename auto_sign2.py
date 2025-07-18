import requests
import time
from datetime import datetime, timedelta, timezone

class ChaoxingAutoSign:
    def __init__(self):
        self.username = "18507485528"
        self.password = "Zf040505"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) '
                'AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 '
                'Mobile/14E304 Safari/602.1'
            ),
        })

    def encrypt(self, input_text):
        import base64
        from Crypto.Cipher import AES

        key = "u2oh6Vu^HWe4_AES"
        aeskey = key.encode('utf-8')
        iv = aeskey
        cipher = AES.new(aeskey, AES.MODE_CBC, iv)
        pad = lambda s: s + (AES.block_size - len(s) % AES.block_size) * \
                        chr(AES.block_size - len(s) % AES.block_size)
        encrypted = cipher.encrypt(pad(input_text).encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')

    def login(self) -> bool:
        acc = self.encrypt(self.username)
        pwd = self.encrypt(self.password)

        login_url = "https://passport2.chaoxing.com/fanyalogin"
        login_data = {
            'fid': '-1',
            'uname': acc,
            'password': pwd,
            'refer': 'http%3A%2F%2Foffice.chaoxing.com%2Ffront%2Fthird%2Fapps%2Fseat%2Findex',
            't': 'true',
            'forbidotherlogin': 0,
            'validate': 0,
            'doubleFactorLogin': 0,
            'independentId': 0,
        }
        try:
            resp = self.session.post(login_url, data=login_data, timeout=10)
            resp.raise_for_status()
            # 可根据接口返回进一步校验登录是否成功：
            if '"error"' in resp.text:
                print("[-] 登录失败，用户名或密码错误")
                return False
            # 访问座位系统主页
            self.session.get(
                'https://office.chaoxing.com/front/third/apps/seat/index',
                timeout=10
            )
            print("[+] 登录成功，进入座位系统")
            return True
        except Exception as e:
            print(f"[-] 登录异常: {e}")
            return False

    def get_reserve_list(self):
        # 北京时间
        beijing = datetime.now(timezone.utc) + timedelta(hours=8)
        today = beijing.strftime("%Y-%m-%d")
        url = "https://office.chaoxing.com/data/apps/seat/reservelist"
        params = {'indexId': 0, 'pageSize': 100, 'type': -1}
        try:
            res = self.session.get(url, params=params, timeout=10)
            res.raise_for_status()
            data = res.json().get("data", {}).get("reserveList", [])
            return [item for item in data if item.get("today") == today]
        except Exception as e:
            print(f"[-] 获取预约记录失败: {e}")
            return []

    def sign(self, rid):
        sign_url = f"https://office.chaoxing.com/data/apps/seat/sign?id={rid}"
        try:
            res = self.session.get(sign_url, timeout=10)
            res.raise_for_status()
            js = res.json()
            if js.get("success"):
                print(f"[+] 签到成功！预约ID：{rid}")
            else:
                print(f"[-] 签到失败: {js}")
        except Exception as e:
            print(f"[-] 签到请求异常: {e}")

    def wait_until(self, target_time="08:40:10"):
        print(f"[+] 等待签到时间 {target_time} 中...")
        while True:
            beijing = datetime.now(timezone.utc) + timedelta(hours=8)
            current_time = beijing.strftime("%H:%M:%S")
            if current_time >= target_time:
                print(f"[+] 到达签到时间 {target_time}，开始签到")
                break
            print(f"当前时间 {current_time}，等待中...")
            time.sleep(10)

    def run(self):
        if not self.login():
            return
        self.wait_until("08:40:00")
        time.sleep(2)
        reserves = self.get_reserve_list()
        if not reserves:
            print("[-] 今天没有预约记录，无法签到")
            return
        # 默认取第一条，如有多条，可根据 reserve["startTime"] 等字段筛选
        rid = reserves[0]["id"]
        print(f"[+] 找到预约，ID = {rid}")
        self.sign(rid)

if __name__ == "__main__":
    ChaoxingAutoSign().run()
