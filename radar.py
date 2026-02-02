import requests
import datetime
import os

# --- 1. 配置区 ---
# 飞书 Webhook 地址从 GitHub Secrets 读取
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')

# --- 2. 抓取逻辑 ---
# 计算 30 天前的日期
start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
# 查询条件：新项目、高 Star、非 Fork
query = f"created:>{start_date} stars:>500 fork:false"
url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

try:
    response = requests.get(url)
    items = response.json().get('items', [])
    
    if not items:
        print("暂时没有符合条件的新项目。")
        # 如果没有新项目，可以退出
        exit(0)

    # --- 3. 构造 Markdown 并写入 README.md ---
    md_content = f"# 🌊 GitHub 暗流监控报告\n\n> 监控标准：创建时间 < 30天 且 Stars > 500\n>\n> 最后更新：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    for item in items[:15]:
        md_content += f"### ⭐ {item['stargazers_count']} | [{item['full_name']}]({item['html_url']})\n"
        md_content += f"- **简介**: {item['description'] or '暂无描述'}\n"
        md_content += f"- **创建时间**: {item['created_at'][:10]}\n\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # --- 4. 构造飞书推送卡片 ---
    if FEISHU_WEBHOOK:
        card_elements = []
        for item in items[:8]:  # 选取前 8 个精选
            card_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**⭐ {item['stargazers_count']}** | [{item['full_name']}]({item['html_url']})\n{item['description'] or '暂无描述'}"
                }
            })
            card_elements.append({"tag": "hr"})

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "🚀 GitHub 暗流实时监控"},
                    "template": "blue"
                },
                "elements": card_elements
            }
        }
        requests.post(FEISHU_WEBHOOK, json=payload)
        print("飞书卡片推送成功！")

except Exception as e:
    print(f"执行出错: {e}")
