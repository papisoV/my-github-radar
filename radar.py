import requests
import datetime
import os
import json

# --- 1. 配置区 ---
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
PUSHDEER_KEY = "PDU38939T9Wp8bt11RTZPCi5FkYaV24vJjCzfXu28"
DB_FILE = "pushed_ids.txt"
HISTORY_FILE = "stars_history.json" # 新增：存储上一次扫描的 Star 数

BLACK_LIST = ["awesome", "roadmap", "interview", "collection", "guide", "free-courses"]
GROWTH_THRESHOLD = 100 # 每小时增长阈值

# --- 2. 新增：免费翻译函数 (利用 Google Translate 备用接口) ---
def translate_to_zh(text):
    if not text: return "无描述"
    try:
        # 使用 Google 翻译的简易接口
        base_url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
        res = requests.get(base_url + urllib.parse.quote(text), timeout=5)
        # 结果是嵌套列表，取第一个元素
        return "".join([i[0] for i in res.json()[0]])
    except Exception as e:
        print(f"翻译失败: {e}")
        return text # 失败则返回原文
        

# --- 3. 加载数据 ---
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        pushed_ids = set(line.strip() for line in f if line.strip())
else:
    pushed_ids = set()

if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        try:
            stars_history = json.load(f)
        except:
            stars_history = {}
else:
    stars_history = {}

# --- 3. 抓取逻辑 ---
start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
query = f"created:>{start_date} stars:>500 fork:false"
url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

try:
    response = requests.get(url)
    all_items = response.json().get('items', [])
    if not all_items: exit(0)

    # 精炼并进行双语转换
    qualified_items = []
    for i in all_items:
        if not any(word in (i['full_name']+(i['description'] or "")).lower() for word in BLACK_LIST):
            # 获取翻译后的描述
            desc_en = i['description'] or "No description"
            desc_zh = translate_to_zh(desc_en)
            i['bilingual_desc'] = f"{desc_zh}\n*(原文: {desc_en})*"
            qualified_items.append(i)
    

    # --- 4. 计算增长斜率 ---
    current_stars_map = {}
    explosive_items = [] # 存储爆发式增长的项目

    for item in qualified_items:
        item_id = str(item['id'])
        current_stars = item['stargazers_count']
        current_stars_map[item_id] = current_stars
        
        # 如果上一次记录里有这个项目，计算差值
        if item_id in stars_history:
            delta = current_stars - stars_history[item_id]
            if delta >= GROWTH_THRESHOLD:
                item['hour_growth'] = delta # 动态记录增长数
                explosive_items.append(item)

    # --- 5. 执行推送逻辑 ---
    # 场景 A：发现从未见过的新项目 (New Arrival)
    new_items = [item for item in qualified_items if str(item['id']) not in pushed_ids]
    
    # 场景 B：旧项目突然爆发 (Explosive Growth)
    # 我们优先推送爆发项目，其次是新项目
    push_list = explosive_items + [i for i in new_items if i not in explosive_items]

if push_list and FEISHU_WEBHOOK:
        card_elements = []
        for item in push_list[:5]:
            growth_info = f"\n🔥 **[时速爆发] 近一小时增长: {item.get('hour_growth', 'N/A')} Stars**" if 'hour_growth' in item else ""
            prefix = "🔴【特急预警】" if 'hour_growth' in item else "✨【发现新暗流】"
            
            card_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md", 
                    # 这里使用了我们新生成的 bilingual_desc
                    "content": f"**{prefix}**\n**项目**: [{item['full_name']}]({item['html_url']})\n**总 Stars**: `{item['stargazers_count']}`{growth_info}\n**简介**: {item['bilingual_desc']}"
                }
            })
            card_elements.append({"tag": "hr"})

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "🛰️ 极简暗流监控(斜率版)"},
                    "template": "red" if explosive_items else "orange"
                },
                "elements": card_elements
            }
        }
        requests.post(FEISHU_WEBHOOK, json=payload)

    # --- 6. 数据持久化 ---
    # 记录已推 ID
    for item in new_items:
        pushed_ids.add(str(item['id']))
    with open(DB_FILE, "w") as f:
        for _id in pushed_ids: f.write(f"{_id}\n")
    
    # 记录当前 Star 状态供下次对比
    with open(HISTORY_FILE, "w") as f:
        json.dump(current_stars_map, f)

    # 更新 README (此处省略部分重复的 Markdown 构造逻辑，保持与上版本一致)
md_content = f"# 🌊 GitHub 暗流监控报告 (双语版)\n\n> 更新时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for item in qualified_items[:15]:
        md_content += f"### ⭐ {item['stargazers_count']} | [{item['full_name']}]({item['html_url']})\n"
        md_content += f"- **中文简介**: {translate_to_zh(item['description'])}\n"
        md_content += f"- **Original**: {item['description'] or 'N/A'}\n\n"
    
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    # ... (原有 README 写入逻辑) ...

except Exception as e:
    print(f"运行出错: {e}")
