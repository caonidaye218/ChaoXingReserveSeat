import requests
import time
import base64
from Crypto.Cipher import AES

class ChaoxingAutoSign:
    def __init__(self):
        # ==================== 已更新为您的账号信息 ====================
        self.username = "18507485528"
        self.password = "Zf040505"
        # ==========================================================
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1',
        })

    def encrypt(self, input_text):
        """对账号密码进行加密"""
        key = "u2oh6Vu^HWe4_AES"
        aeskey = key.encode('utf-8')
        iv = key.encode('utf-8')
        cipher = AES.new(aeskey, AES.MODE_CBC, iv)
        pad = lambda s: s + (AES.block_size - len(s) % AES.block_size) * chr(AES.block_size - len(s) % AES.block_size)
        encrypted = cipher.encrypt(pad(input_text).encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')

    def login(self):
        """登录超星账号"""
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
        # 发送登录请求
        response = self.session.post(login_url, data=login_data)
        # 检查登录是否成功
        if response.json().get("status") == True:
            self.session.get('https://office.chaoxing.com/front/third/apps/seat/index')
            print(f"[+] 账号 {self.username} 登录成功，进入座位系统")
        else:
            print(f"[-] 登录失败，请检查账号密码是否正确。返回信息: {response.text}")
            exit() # 登录失败则退出程序

    def get_reserve_list(self):
        """获取当天的预约记录"""
        today = time.strftime("%Y-%m-%d", time.localtime(time.time() + 8*3600)) # 获取北京时间
        url = "https://office.chaoxing.com/data/apps/seat/reservelist"
        params = {
            'indexId': 0,
            'pageSize': 100,
            'type': -1
        }
        res = self.session.get(url, params=params)
        if res.status_code == 200:
            try:
                data = res.json()["data"]["reserveList"]
                reserve_today = []
                for item in data:
                    if item.get("today", "") == today:
                        reserve_today.append(item)
                return reserve_today
            except Exception as e:
                print(f"[-] 获取预约记录失败: {e}")
                return []
        else:
            print(f"[-] 获取预约请求失败，状态码：{res.status_code}")
            return []

    def sign(self, rid):
        """执行签到操作"""
        sign_url = f"https://office.chaoxing.com/data/apps/seat/sign?id={rid}"
        res = self.session.get(sign_url)
        if res.status_code == 200:
            try:
                if res.json()["success"]:
                    print(f"[+] 签到成功！预约ID：{rid}")
                else:
                    print(f"[-] 签到失败，返回信息：{res.json().get('msg', '未知错误')}")
            except Exception as e:
                print(f"[-] 签到请求异常: {e}")
        else:
            print(f"[-] 签到请求失败，状态码：{res.status_code}")

    def wait_until(self, target_time="10:00:00"):
        """等待直到指定时间"""
        print(f"[+] 等待签到时间 {target_time} 中...")
        while True:
            # 使用北京时间进行比较
            current_time = time.strftime("%H:%M:%S", time.localtime(time.time() + 8*3600))
            if current_time >= target_time:
                print(f"[+] 到达签到时间 {target_time}，准备开始签到")
                break
            # 每分钟打印一次，避免刷屏
            if current_time.endswith("00"):
                 print(f"当前时间 {current_time}，等待中...")
            time.sleep(1) # 每秒检查一次

    def run(self):
        """主运行函数"""
        self.login()
        
        # ==================== 签到时间已确认为 09:40 ====================
        self.wait_until(target_time="10:00:00")
        # ==============================================================

        time.sleep(2) # 等待2秒，确保网络稳定
        reserves = self.get_reserve_list()
        
        if not reserves:
            print("[-] 今天没有找到预约记录，无法签到")
            return
            
        # 默认对找到的第一个预约记录进行签到
        target = reserves[0]
        rid = target["id"]
        print(f"[+] 找到今天的预约记录，ID = {rid}，状态为：{target.get('statusStr', '未知')}")
        
        # 检查是否已经签到
        if target.get("status") == 2:
             print("[!] 注意：该预约记录状态已为“履约中”，可能已经签到。脚本将尝试再次签到。")

        self.sign(rid)

if __name__ == "__main__":
    cxa = ChaoxingAutoSign()
    cxa.run()
