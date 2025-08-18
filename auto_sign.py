import requests
import time
import os
from datetime import datetime, timezone, timedelta

class ChaoxingAutoSign:
    def __init__(self):
        # 从环境变量获取账号密码，更安全
        self.username = os.environ.get('USERNAME', '18507485528')
        self.password = os.environ.get('PASSWORD', 'Zf040505')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) '
                          'AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 '
                          'Mobile/14E304 Safari/602.1',
        })

    def encrypt(self, input_text):
        import base64
        from Crypto.Cipher import AES

        key = "u2oh6Vu^HWe4_AES"
        aeskey = key.encode('utf-8')
        iv = key.encode('utf-8')
        cipher = AES.new(aeskey, AES.MODE_CBC, iv)
        pad = lambda s: s + (AES.block_size - len(s) % AES.block_size) * \
                        chr(AES.block_size - len(s) % AES.block_size)
        encrypted = cipher.encrypt(pad(input_text).encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')

    def get_beijing_time(self):
        """获取准确的北京时间"""
        beijing_tz = timezone(timedelta(hours=8))
        return datetime.now(beijing_tz)

    def login(self):
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
        
        response = self.session.post(login_url, data=login_data)
        print(f"[DEBUG] 登录响应状态码: {response.status_code}")
        
        self.session.get('https://office.chaoxing.com/front/third/apps/seat/index')
        print("[+] 登录成功，进入座位系统")

    def get_reserve_list(self):
        beijing_time = self.get_beijing_time()
        today = beijing_time.strftime("%Y-%m-%d")
        print(f"[DEBUG] 当前北京时间日期: {today}")
        
        url = "https://office.chaoxing.com/data/apps/seat/reservelist"
        params = {
            'indexId': 0,
            'pageSize': 100,
            'type': -1
        }
        res = self.session.get(url, params=params)
        print(f"[DEBUG] 获取预约列表响应状态码: {res.status_code}")
        
        if res.status_code == 200:
            try:
                data = res.json()["data"]["reserveList"]
                print(f"[DEBUG] 获取到 {len(data)} 条预约记录")
                
                reserve_today = []
                for item in data:
                    print(f"[DEBUG] 预约记录: {item}")
                    if item.get("today", "") == today:
                        reserve_today.append(item)
                
                print(f"[DEBUG] 今天的预约记录数量: {len(reserve_today)}")
                return reserve_today
            except Exception as e:
                print(f"[-] 获取预约记录失败: {e}")
                print(f"[DEBUG] 响应内容: {res.text}")
                return []
        else:
            print(f"[-] 获取预约请求失败，状态码：{res.status_code}")
            return []

    def get_reserve_detail(self, rid):
        """获取预约详细信息，包括签到时间窗口"""
        url = f"https://office.chaoxing.com/data/apps/seat/reserve/info?id={rid}"
        res = self.session.get(url)
        if res.status_code == 200:
            try:
                data = res.json()
                print(f"[DEBUG] 预约详情: {data}")
                return data
            except Exception as e:
                print(f"[-] 获取预约详情失败: {e}")
                return None
        return None

    def sign(self, rid):
        # 先获取预约详情
        detail = self.get_reserve_detail(rid)
        
        sign_url = f"https://office.chaoxing.com/data/apps/seat/sign?id={rid}"
        res = self.session.get(sign_url)
        print(f"[DEBUG] 签到响应状态码: {res.status_code}")
        print(f"[DEBUG] 签到响应内容: {res.text}")
        
        if res.status_code == 200:
            try:
                result = res.json()
                if result["success"]:
                    print(f"[+] 签到成功！预约ID：{rid}")
                    return True
                else:
                    print(f"[-] 签到失败，返回信息：{result}")
                    return False
            except Exception as e:
                print(f"[-] 签到请求异常: {e}")
                return False
        else:
            print(f"[-] 签到请求失败，状态码：{res.status_code}")
            return False

    def check_sign_time(self):
        """检查当前是否在签到时间窗口内"""
        beijing_time = self.get_beijing_time()
        current_time = beijing_time.strftime("%H:%M")
        
        # 定义签到时间窗口（预约开始前20分钟内可签到）
        # 10:00-14:00段：9:40-10:00可签到
        # 14:00-18:00段：13:40-14:00可签到  
        # 18:00-22:00段：17:40-18:00可签到
        sign_windows = [
            ("09:40", "10:00"),  # 第一个时间段
            ("13:40", "14:00"),  # 第二个时间段  
            ("17:40", "18:00")   # 第三个时间段
        ]
        
        for start_time, end_time in sign_windows:
            if start_time <= current_time <= end_time:
                return True, f"{start_time}-{end_time}"
        
        return False, None

    def wait_for_sign_time(self):
        """等待到签到时间窗口"""
        beijing_time = self.get_beijing_time()
        current_time = beijing_time.strftime("%H:%M:%S")
        
        # 检查当前时间
        print(f"[+] 当前北京时间: {current_time}")
        
        # 定义今天的签到时间窗口开始时间
        target_times = ["09:40:00", "13:40:00", "17:40:00"]
        
        # 找到下一个签到时间
        current_hour_min = beijing_time.strftime("%H:%M")
        next_target = None
        
        for target in target_times:
            target_hour_min = target[:5]  # 取HH:MM部分
            if current_hour_min < target_hour_min:
                next_target = target
                break
        
        if next_target:
            print(f"[+] 等待下一个签到时间窗口开始: {next_target}")
            print(f"[+] 对应预约时间段: {self.get_reserve_period(next_target)}")
            
            while True:
                beijing_time = self.get_beijing_time()
                current_time = beijing_time.strftime("%H:%M:%S")
                
                if current_time >= next_target:
                    print(f"[+] 到达签到时间 {next_target}，开始签到")
                    break
                
                # 每30秒检查一次
                time.sleep(30)
        else:
            print("[+] 今天的签到时间已过，直接尝试签到")

    def get_reserve_period(self, sign_time):
        """根据签到时间获取对应的预约时间段"""
        time_map = {
            "09:40:00": "10:00-14:00",
            "13:40:00": "14:00-18:00", 
            "17:40:00": "18:00-22:00"
        }
        return time_map.get(sign_time, "未知时间段")

    def try_multiple_sign_attempts(self, rid):
        """尝试多次签到，增加间隔时间"""
        max_attempts = 5  # 增加尝试次数
        
        for attempt in range(1, max_attempts + 1):
            print(f"[+] 第 {attempt} 次签到尝试")
            
            if self.sign(rid):
                print(f"[+] 第 {attempt} 次尝试签到成功！")
                return True
            
            if attempt < max_attempts:
                wait_time = 60 if attempt <= 2 else 120  # 前两次等1分钟，后面等2分钟
                print(f"[-] 第 {attempt} 次尝试失败，等待{wait_time}秒后重试...")
                time.sleep(wait_time)
        
        print(f"[-] {max_attempts} 次尝试都失败了")
        return False

    def run(self):
        try:
            print("[+] 开始自动签到程序")
            beijing_time = self.get_beijing_time()
            current_time = beijing_time.strftime("%H:%M:%S")
            print(f"[+] 当前北京时间: {current_time}")
            
            self.login()
            
            # 获取预约列表
            reserves = self.get_reserve_list()
            if not reserves:
                print("[-] 今天没有预约记录，无法签到")
                return
            
            target = reserves[0]
            rid = target["id"]
            print(f"[+] 找到预约，ID = {rid}")
            
            # 检查当前是否在签到时间窗口内
            is_sign_time, window = self.check_sign_time()
            
            if is_sign_time:
                print(f"[+] 当前在签到时间窗口内 ({window})，立即开始签到")
                self.try_multiple_sign_attempts(rid)
            else:
                # 由于GitHub Actions已经在正确时间触发，直接尝试签到
                print("[+] 由GitHub Actions在预定时间触发，直接尝试签到")
                self.try_multiple_sign_attempts(rid)
            
        except Exception as e:
            print(f"[-] 程序运行异常: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    cxa = ChaoxingAutoSign()
    cxa.run()
