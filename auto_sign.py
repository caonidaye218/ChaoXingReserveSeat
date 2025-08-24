import json
import time
import logging
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import reserve, get_user_credentials
from datetime import datetime, timedelta

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

    def parse_time_range(self, time_str):
        """解析时间范围字符串，返回开始和结束时间"""
        try:
            # 处理类似 "10:00-14:00" 的格式
            if '-' in time_str:
                start_str, end_str = time_str.split('-')
            elif '~' in time_str:
                start_str, end_str = time_str.split('~')
            else:
                return None, None
                
            start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
            end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
            return start_time, end_time
        except Exception as e:
            logging.error(f"[-] 解析时间范围失败: {time_str}, 错误: {e}")
            return None, None

    def group_continuous_reservations(self, reserves):
        """将连续的时间段预约进行分组"""
        if not reserves:
            return []
        
        # 按时间排序
        sorted_reserves = []
        for reserve_item in reserves:
            time_str = reserve_item.get("timeStr", "")
            start_time, end_time = self.parse_time_range(time_str)
            if start_time and end_time:
                reserve_item["parsed_start"] = start_time
                reserve_item["parsed_end"] = end_time
                sorted_reserves.append(reserve_item)
        
        # 按开始时间排序
        sorted_reserves.sort(key=lambda x: x["parsed_start"])
        
        # 分组连续的时间段
        groups = []
        current_group = []
        
        for reserve_item in sorted_reserves:
            if not current_group:
                current_group.append(reserve_item)
            else:
                # 检查是否与当前组的最后一个预约连续
                last_reserve = current_group[-1]
                if reserve_item["parsed_start"] == last_reserve["parsed_end"]:
                    # 连续的时间段，加入当前组
                    current_group.append(reserve_item)
                else:
                    # 不连续，开始新组
                    if current_group:
                        groups.append(current_group)
                    current_group = [reserve_item]
        
        # 添加最后一组
        if current_group:
            groups.append(current_group)
        
        logging.info(f"[+] 将 {len(reserves)} 条预约记录分组为 {len(groups)} 个连续时间段")
        for i, group in enumerate(groups):
            start_time = group[0]["parsed_start"].strftime("%H:%M")
            end_time = group[-1]["parsed_end"].strftime("%H:%M")
            logging.info(f"    组 {i+1}: {start_time}-{end_time} (包含 {len(group)} 个预约)")
        
        return groups

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

    def smart_sign_reservations(self):
        """智能签到：只签到每个连续时间段的第一个预约"""
        reserves = self.get_reserve_list()
        
        if not reserves:
            logging.warning("[-] 今天没有找到预约记录，无法签到")
            return False
        
        # 将预约按连续时间段分组
        groups = self.group_continuous_reservations(reserves)
        
        if not groups:
            logging.warning("[-] 无法解析预约时间，使用传统方式签到")
            return self.traditional_sign_all(reserves)
        
        success_count = 0
        total_groups = len(groups)
        
        for group_index, group in enumerate(groups):
            group_start = group[0]["parsed_start"].strftime("%H:%M")
            group_end = group[-1]["parsed_end"].strftime("%H:%M")
            logging.info(f"[+] 处理时间段组 {group_index + 1}: {group_start}-{group_end}")
            
            # 只签到每组的第一个预约（最早的时间段）
            first_reserve = group[0]
            rid = first_reserve["id"]
            status = first_reserve.get("status")
            status_str = first_reserve.get("statusStr", "未知")
            time_str = first_reserve.get("timeStr", "")
            
            logging.info(f"[+] 签到时间段 {time_str} (ID={rid})，当前状态：{status_str}")
            
            # 状态检查：1=预约成功待签到，2=履约中，3=已完成等
            if status == 2:
                logging.info(f"[!] 预约 {rid} 状态已为'履约中'，整个时间段可能已经签到，跳过")
                success_count += 1
                
                # 检查组内其他预约的状态
                for other_reserve in group[1:]:
                    other_status_str = other_reserve.get("statusStr", "未知")
                    other_time_str = other_reserve.get("timeStr", "")
                    logging.info(f"    -> 关联时间段 {other_time_str} 状态：{other_status_str}")
                continue
                
            elif status == 3:
                logging.info(f"[!] 预约 {rid} 已完成，跳过整个时间段")
                success_count += 1  
                continue
            
            # 尝试签到第一个时间段
            if self.sign(rid):
                success_count += 1
                logging.info(f"[+] ✅ 时间段组 {group_index + 1} 签到成功！这将覆盖整个 {group_start}-{group_end} 时间段")
                
                # 等待一下，让系统处理
                time.sleep(2)
                
                # 检查组内其他预约的状态更新
                logging.info(f"[+] 检查关联时间段的状态更新...")
                for other_reserve in group[1:]:
                    other_time_str = other_reserve.get("timeStr", "")
                    logging.info(f"    -> 关联时间段 {other_time_str} 应该也已生效")
                    
            else:
                logging.warning(f"[-] 时间段组 {group_index + 1} 签到失败")
            
            time.sleep(1)  # 组间延迟
        
        logging.info(f"[+] 智能签到完成：{success_count}/{total_groups} 个时间段组成功签到")
        return success_count > 0

    def traditional_sign_all(self, reserves):
        """传统方式：逐个签到所有预约（备用方案）"""
        logging.info("[+] 使用传统方式逐个签到...")
        
        success_count = 0
        total_count = len(reserves)
        
        for reserve_item in reserves:
            rid = reserve_item["id"]
            status = reserve_item.get("status")
            status_str = reserve_item.get("statusStr", "未知")
            time_str = reserve_item.get("timeStr", "")
            
            logging.info(f"[+] 处理预约记录 {time_str} (ID={rid})，当前状态：{status_str}")
            
            # 状态检查：1=预约成功待签到，2=履约中，3=已完成等
            if status == 2:
                logging.info(f"[!] 预约 {rid} 状态已为'履约中'，可能已经签到，跳过")
                success_count += 1
                continue
            elif status == 3:
                logging.info(f"[!] 预约 {rid} 已完成，跳过")
                success_count += 1  
                continue
                
            # 尝试签到
            if self.sign(rid):
                success_count += 1
                time.sleep(0.5)  # 签到成功后短暂延迟
            else:
                time.sleep(1)  # 签到失败后稍长延迟
                
        logging.info(f"[+] 传统签到完成：{success_count}/{total_count} 成功")
        return success_count > 0

    def run(self, sign_time="10:00:00", use_smart_mode=True):
        """主运行函数"""
        if not self.login():
            return False
            
        # 等待签到时间
        self.wait_until_sign_time(sign_time)
        
        # 等待2秒确保网络稳定
        time.sleep(2)
        
        # 执行智能签到或传统签到
        if use_smart_mode:
            return self.smart_sign_reservations()
        else:
            reserves = self.get_reserve_list()
            return self.traditional_sign_all(reserves)


def execute_single_user_sign(user_config, action=False, sign_time="10:00:00", smart_mode=True):
    """执行单个用户的签到任务"""
    try:
        if "tasks" in user_config:
            # 新格式配置
            username = user_config["username"]
            password = user_config["password"]
        else:
            # 旧格式配置
            username = user_config.get("username")
            password = user_config.get("password")
            
        if not username or not password:
            logging.error("[-] 用户配置中缺少用户名或密码")
            return False
            
        logging.info(f"[+] 开始为用户 {username} 执行签到 (智能模式: {'开启' if smart_mode else '关闭'})")
        
        # 创建签到实例
        signer = ChaoxingAutoSign(username, password)
        
        # 执行签到
        result = signer.run(sign_time, smart_mode)
        
        if result:
            logging.info(f"[+] 用户 {username} 签到完成")
        else:
            logging.warning(f"[-] 用户 {username} 签到失败")
            
        return result
        
    except Exception as e:
        logging.error(f"[-] 用户签到过程异常: {e}")
        return False


def main_sign(users, action=False, sign_time="10:00:00", max_workers=3, smart_mode=True):
    """主签到函数 - 支持多用户并发签到"""
    mode_desc = "智能连续时间段" if smart_mode else "传统逐个"
    logging.info(f"🔔 自动签到系统启动，模式：{mode_desc}，目标签到时间：{sign_time}")
    
    # 如果是GitHub Action模式，需要从环境变量获取凭据
    if action:
        try:
            usernames, passwords = get_user_credentials(action)
            username_list = usernames.split(",")
            password_list = passwords.split(",")
            
            if len(username_list) != len(users):
                logging.error("[-] GitHub Action模式下用户数量不匹配")
                return
                
            # 更新用户配置
            for i, user in enumerate(users):
                if i < len(username_list):
                    if "tasks" in user:
                        user["username"] = username_list[i]
                        user["password"] = password_list[i]
                    else:
                        user["username"] = username_list[i]
                        user["password"] = password_list[i]
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
    
    # 使用线程池并发处理多个用户的签到
    success_count = 0
    with ThreadPoolExecutor(max_workers=min(len(valid_users), max_workers)) as executor:
        future_to_user = {
            executor.submit(execute_single_user_sign, user, action, sign_time, smart_mode): user 
            for user in valid_users
        }
        
        for future in as_completed(future_to_user):
            user = future_to_user[future]
            try:
                result = future.result()
                if result:
                    success_count += 1
            except Exception as e:
                username = user.get("username", "未知用户")
                logging.error(f"[-] 用户 {username} 签到任务异常: {e}")
    
    logging.info(f"🎉 签到任务完成：{success_count}/{len(valid_users)} 用户成功签到")


if __name__ == "__main__":
    # 命令行参数解析
    parser = argparse.ArgumentParser(prog="Chao Xing Auto Sign System - Smart Mode")
    parser.add_argument("-u", "--user", default="config.json", help="用户配置文件路径")
    parser.add_argument("-t", "--time", default="10:00:00", help="签到时间 (HH:MM:SS)")
    parser.add_argument("-w", "--workers", type=int, default=3, help="并发工作线程数")
    parser.add_argument(
        "-a", "--action", action="store_true", 
        help="启用GitHub Action模式"
    )
    parser.add_argument(
        "-m", "--method", default="sign", choices=["sign", "debug"],
        help="运行模式：sign=正常签到，debug=调试模式"
    )
    parser.add_argument(
        "--traditional", action="store_true",
        help="使用传统模式（逐个签到所有预约）而不是智能模式"
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
    
    # 确定签到模式
    smart_mode = not args.traditional
    
    # 执行签到
    if args.method == "sign":
        main_sign(users, args.action, args.time, args.workers, smart_mode)
    elif args.method == "debug":
        # 调试模式：只处理第一个用户，不等待时间
        logging.info("🐛 调试模式启动")
        if users:
            execute_single_user_sign(users[0], args.action, "00:00:00", smart_mode)
