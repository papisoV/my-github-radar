import requests
import datetime
# 在脚本开头 import requests
import requests

# 在循环获取到 repo 信息后
push_key = "PDU38939T9Wp8bt11RTZPCi5FkYaV24vJjCzfXu28"
text = f"发现 GitHub 暗流项目: {item['full_name']}"
desp = f"Stars: {item['stargazers_count']}\n简介: {item['description']}\n链接: {item['html_url']}"

# 发送到手机
requests.get(f"https://api2.pushdeer.com/message/push?pushkey={push_key}&text={text}&desp={desp}")

# 核心：计算 30 天前的日期
start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')

# 你的条件：创建时间 < 30天，Star > 500
query = f"created:>{start_date} stars:>500 fork:false"
url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

print(f"--- 🛰️ 正在扫描自 {start_date} 以来诞生的 GitHub 暗流 ---")

try:
    response = requests.get(url)
    items = response.json().get('items', [])
    
    if not items:
        print("暂时没有符合条件的新项目。")
    
    for item in items[:15]:  # 只展示前 15 个最火的
        print(f"🔥 Stars: {item['stargazers_count']} | {item['full_name']}")
        print(f"📝 简介: {item['description']}")
        print(f"🔗 链接: {item['html_url']}\n" + "-"*40)
except Exception as e:
    print(f"查询出错: {e}")
