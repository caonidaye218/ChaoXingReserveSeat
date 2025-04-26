import os
import requests
import json
import time

class ChaoxingSign:
    def __init__(self, username, password):
        self.session = requests.Session()
        self.username = username
        self.password = password

    def login(self):
        url = "https://passport2.chaoxing.com/fanyalogin"
        data = {
            "fid": -1,
            "uname": self.username,
            "password": self.password,
            "refer": "https://passport2.chaoxing.com/login?fid=-1&refer=https://i.chaoxing.com"
        }
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        res = self.session.post(url, data=data, headers=headers)
        if res.status_code == 200 and ("个人中心" in res.text or "我的学习" in res.text):
            print("[+] 登录成功（跳转后）")
            return True
        else:
            print("[-] 登录失败，请检查用户名或密码")
            return False

    def get_reserve_list(self):
        url = "https://office.chaoxing.com/data/apps/seat/seat/reserve"
        params = {
            "page": 1,
            "size": 6
        }
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        res = self.session.get(url, params=params, headers=headers)
        if res.status_code == 200:
            result = res.json()
            if result.get("data"):
                reserve_list = result["data"].get("reserveList", [])
                return reserve_list
            else:
                print("[-] 没有获取到预约记录")
                return []
        else:
            print("[-] 获取预约记录失败")
            return []

    def sign(self, rid):
        url = "https://office.chaoxing.com/data/apps/seat/seat/sign"
        params = {"id": rid}
        headers = {"User-Agent": "Mozilla/5.0"}
        res = self.session.get(url, params=params, headers=headers)
        if res.status_code == 200:
            result = res.json()
            if result.get("msg") == "success":
                print("[+] 签到成功")
            else:
                print(f"[-] 签到失败，返回信息：{result.get('msg')}")
        else:
            print("[-] 签到请求失败")

    def wait_until(self, target_time="09:40:00"):
        print(f"[+] 等待签到时间 {target_time} 中...")
        while True:
            current_time = time.strftime("%H:%M:%S", time.localtime(time.time() + 8*3600))
            if current_time >= target_time:
                print(f"[+] 到达签到时间 {target_time}，开始签到")
                break
            print(f"当前时间 {current_time}，等待中...")
            time.sleep(10)

    def run(self):
        if not self.login():
            return
        self.wait_until(target_time="09:40:00")
        time.sleep(2)
        reserve_list = self.get_reserve_list()
        if not reserve_list:
            print("[-] 今天没有预约记录，无法签到")
            return
        today = time.strftime("%Y-%m-%d", time.localtime(time.time() + 8*3600))
        for reserve in reserve_list:
            if reserve["startTime"].startswith(today):
                rid = reserve["id"]
                print(f"[+] 找到今天预约的座位，rid={rid}")
                self.sign(rid)
                return
        print("[-] 今天没有找到对应的预约记录")

if __name__ == "__main__":
    USERNAME = os.environ.get("USERNAME", "")
    PASSWORD = os.environ.get("PASSWORD", "")
    if not USERNAME or not PASSWORD:
        print("[-] 请设置环境变量 USERNAME 和 PASSWORD")
        exit(1)
    cxa = ChaoxingSign(USERNAME, PASSWORD)
    cxa.run()
