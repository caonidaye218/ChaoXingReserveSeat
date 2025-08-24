import json
import time
import logging
import os
import argparse
from utils import reserve, get_user_credentials

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

class ChaoxingAutoSign:
    def __init__(self, username, password, sleep_time=0.1, max_attempt=3):
        self.username = username
        self.password = password
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        
        # 复用现有的 reserve 类来处理登录和会话管理
        self.reserve_client = reserve(
            sleep_time=self.sleep_time,
            max_attempt=self.max_attempt,
            enable_slider=True,
            reserve_next_day=False,  # 签到当天的预约
        )

    def login(self):
        """登录超星账号"""
        try:
            self.reserve_client.get_login_status()
            login_result = self.reserve_client.login(self.username, self.password)
            
            if login_result[0]:
                self.reserve_client.requests.headers.update({"Host": "office.chaoxing.com"})
                logging.info(f"[+] 账号 {self.username} 登录成功")
                return True
            else:
                logging.error(f"[-] 账号 {self.username} 登录失败: {login_result[1]}")
                return False
        except Exception as e:
            logging.error(f"[-] 登录异常: {e}")
            return False

    def get_reserve_list(self):
        """获取当天的预约记录"""
        try:
            # 使用北京时间
            today = time.strftime("%Y-%m-%d", time.localtime(time.time() + 8*3600))
            url = "https://office.chaoxing.com/data/apps/seat/reservelist"
            params = {
                'indexId': 0,
                'pageSize': 100,
                'type': -1
            }
            
            res = self.reserve_client.requests.get(url, params=params)
            if res.status_code == 200:
                data = res.json().get("data", {}).get("reserveList", [])
                reserve_today = []
                
                for item in data:
                    # 检查是否为今天的预约
                    if item.get("today", "") == today:
                        reserve_today.append(item)
                
                logging.info(f"[+] 找到 {len(reserve_today)} 条今天的预约记录")
                return reserve_today
            else:
                logging.error(f"[-] 获取预约请求失败，状态码：{res.status_code}")
                return []
                
        except Exception as e:
            logging.error(f"[-] 获取预约记录失败: {e}")
            return []

    def sign(self, rid):
        """执行签到操作"""
        try:
            sign_url = f"https://office.chaoxing.com/data/apps/seat/sign?id={rid}"
            res = self.reserve_client.requests.get(sign_url)
            
            if res.status_code == 200:
                response_data = res.json()
                if response_data.get("success"):
                    logging.info(f"[+] 签到成功！预约ID：{rid}")
                    return True
                else:
                    error_msg = response_data.get('msg', '未知错误')
                    logging.warning(f"[-] 签到失败，返回信息：{error_msg}")
                    return False
            else:
                logging.error(f"[-] 签到请求失败，状态码：{res.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"[-] 签到请求异常: {e}")
            return False

    def wait_until_sign_time(self, target_time="10:00:00"):
        """等待直到指定签到时间"""
        logging.info(f"[+] 等待签到时间 {target_time} 中...")
        
        while True:
            # 使用北京时间进行比较
            current_time = time.strftime("%H:%M:%S", time.localtime(time.time() + 8*3600))
            
            if current_time >= target_time:
                logging.info(f"[+] 到达签到时间 {target_time}，准备开始签到")
                break
                
            # 每30秒打印一次状态，避免刷屏
            if int(current_time.split(':')[2]) % 30 == 0:
                logging.info(f"当前时间 {current_time}，等待签到时间 {target_time}")
                
            time.sleep(1)  # 每秒检查一次

    def simple_sign_first_reservation(self):
        """简单签到：只签到第一个找到的预约（适用于10-22整段预约）"""
        reserves = self.get_reserve_list()
        
        if not reserves:
            logging.warning("[-] 今天没有找到预约记录，无法签到")
            return False
        
        # 只签到第一个预约记录
        first_reserve = reserves[0]
        rid = first_reserve["id"]
        status = first_reserve.get("status")
        status_str = first_reserve.get("statusStr", "未知")
        time_str = first_reserve.get("timeStr", "")
        
        logging.info(f"[+] 准备签到预约记录 {time_str} (ID={rid})，当前状态：{status_str}")
        
        # 状态检查：1=预约成功待签到，2=履约中，3=已完成等
        if status == 2:
            logging.info(f"[!] 预约 {rid} 状态已为'履约中'，可能已经签到")
            return True
        elif status == 3:
            logging.info(f"[!] 预约 {rid} 已完成")
            return True
        
        # 尝试签到
        if self.sign(rid):
            logging.info(f"[+] ✅ 签到成功！预约时间段：{time_str}")
            return True
        else:
            logging.warning(f"[-] 签到失败")
            return False

    def run(self, sign_time="10:00:00"):
        """主运行函数"""
        if not self.login():
            return False
            
        # 等待签到时间
        self.wait_until_sign_time(sign_time)
        
        # 等待2秒确保网络稳定
        time.sleep(2)
        
        # 执行简单签到
        return self.simple_sign_first_reservation()


def main_sign(users, action=False, sign_time="10:00:00"):
    """主签到函数"""
    logging.info(f"🔔 自动签到系统启动，目标签到时间：{sign_time}")
    
    # 如果是GitHub Action模式，需要从环境变量获取凭据
    if action:
        try:
            usernames, passwords = get_user_credentials(action)
            if usernames and passwords:
                username_list = usernames.split(",") if usernames else []
                password_list = passwords.split(",") if passwords else []
                
                if len(username_list) != len(users) or len(password_list) != len(users):
                    logging.error("[-] GitHub Action模式下用户数量不匹配")
                    return
                    
                # 更新用户配置
                for i, user in enumerate(users):
                    if i < len(username_list):
                        user["username"] = username_list[i]
                        user["password"] = password_list[i]
            else:
                logging.error("[-] 环境变量 USERNAME 或 PASSWORD 未配置")
                return
        except Exception as e:
            logging.error(f"[-] 获取GitHub Action凭据失败: {e}")
            return
    
    # 检查当前是否有用户需要签到
    valid_users = []
    current_dayofweek = time.strftime("%A", time.localtime(time.time() + 8*3600))
    
    for user in users:
        if "tasks" in user:
            # 新格式：检查是否有今天的任务
            has_today_task = any(
                current_dayofweek in task.get("daysofweek", [])
                for task in user["tasks"]
            )
            if has_today_task:
                valid_users.append(user)
        else:
            # 旧格式：检查daysofweek
            if current_dayofweek in user.get("daysofweek", []):
                valid_users.append(user)
    
    if not valid_users:
        logging.info("[-] 今天没有用户需要签到")
        return
    
    logging.info(f"[+] 找到 {len(valid_users)} 个用户需要签到")
    
    # 逐个处理用户签到
    success_count = 0
    for user in valid_users:
        try:
            username = user.get("username")
            password = user.get("password")
            
            if not username or not password:
                logging.error("[-] 用户配置中缺少用户名或密码")
                continue
                
            logging.info(f"[+] 开始为用户 {username} 执行签到")
            
            # 创建签到实例
            signer = ChaoxingAutoSign(username, password)
            
            # 执行签到
            result = signer.run(sign_time)
            
            if result:
                logging.info(f"[+] 用户 {username} 签到完成")
                success_count += 1
            else:
                logging.warning(f"[-] 用户 {username} 签到失败")
                
        except Exception as e:
            logging.error(f"[-] 用户签到过程异常: {e}")
    
    logging.info(f"🎉 签到任务完成：{success_count}/{len(valid_users)} 用户成功签到")


if __name__ == "__main__":
    # 命令行参数解析
    parser = argparse.ArgumentParser(prog="Chao Xing Auto Sign System - Simple Mode")
    parser.add_argument("-u", "--user", default="config.json", help="用户配置文件路径")
    parser.add_argument("-t", "--time", default="10:00:00", help="签到时间 (HH:MM:SS)")
    parser.add_argument(
        "-a", "--action", action="store_true", 
        help="启用GitHub Action模式"
    )
    parser.add_argument(
        "-m", "--method", default="sign", choices=["sign", "debug"],
        help="运行模式：sign=正常签到，debug=调试模式"
    )
    
    args = parser.parse_args()
    
    # 读取配置文件
    try:
        config_path = os.path.join(os.path.dirname(__file__), args.user)
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            users = config_data.get("reserve", [])
    except Exception as e:
        logging.error(f"[-] 读取配置文件失败: {e}")
        exit(1)
    
    if not users:
        logging.error("[-] 配置文件中没有找到用户信息")
        exit(1)
    
    # 执行签到
    if args.method == "sign":
        main_sign(users, args.action, args.time)
    elif args.method == "debug":
        # 调试模式：只处理第一个用户，不等待时间
        logging.info("🐛 调试模式启动")
        if users:
            user = users[0]
            if args.action:
                try:
                    usernames, passwords = get_user_credentials(args.action)
                    if usernames and passwords:
                        user["username"] = usernames.split(",")[0]
                        user["password"] = passwords.split(",")[0]
                except:
                    pass
            signer = ChaoxingAutoSign(user.get("username"), user.get("password"))
            signer.run("00:00:00")
