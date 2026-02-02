import requests
import datetime
import os
import json
import urllib.parse

# --- 1. 配置区 ---
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
PUSHDEER_KEY = "PDU38939T9Wp8bt11RTZPCi5FkYaV24vJjCzfXu28"
DB_FILE = "pushed_ids.txt"
HISTORY_FILE = "stars_history.json"

BLACK_LIST = ["awesome", "roadmap", "interview", "collection", "guide", "free-courses"]
GROWTH_THRESHOLD = 50 

# --- 2. 增强功能：智能标签识别 ---
def get_smart_tags(item):
    """根据项目信息自动识别标签"""
    name_desc = (item['full_name'] + (item['description'] or "")).lower()
    tags = []
    
    # 语言标签
    if item['language']:
        tags.append(f"🏷️{item['language']}")
    
    # 技术领域识别
    topics = {
        "🤖 AI/ML": ["llm", "ai", "gpt", "claude", "agent", "stable-diffusion", "inference"],
        "🌐 Web/Frontend": ["react", "vue", "typescript", "tailwild", "nextjs", "browser"],
        "⚙️ Tooling": ["cli", "workflow", "automation", "scripts"],
        "🦀 Rust/Performance": ["rust", "performance", "blazing"],
        "📱 Mobile": ["ios", "android", "flutter", "react-native"],
        "☁️ Cloud/DevOps": ["docker", "k8s", "aws", "serverless", "deploy"]
    }
    
    for tag, keywords in topics.items():
        if any(key in name_desc for key in keywords):
            tags.append(tag)
            
    return " ".join(tags[:3]) # 最多展示3个标签

# --- 3. 翻译函数 ---
def translate_to_zh(text):
    if not text: return "无描述"
    try:
        base_url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
        res = requests.get(base_url + urllib.parse.quote(text), timeout=5)
        return "".join([i[0] for i in res.json()[0]])
    except:
        return text

# --- 4. 数据加载 ---
pushed_ids = set()
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        pushed_ids = set(line.strip() for line in f if line.strip())

stars_history = {}
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        try: stars_history = json.load(f)
        except: stars_history = {}

# --- 5. 抓取与计算 ---
start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
query = f"created:>{start_date} stars:>500 fork:false"
url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

try:
    response = requests.get(url)
    items = response.json().get('items', [])
    if not items: exit(0)

    current_stars_map = {}
    qualified_items = []
    
    for i in items:
        if any(word in (i['full_name']+(i['description'] or "")).lower() for word in BLACK_LIST):
            continue
            
        item_id = str(i['id'])
        current_stars = i['stargazers_count']
        current_stars_map[item_id] = current_stars
        
        # 计算时速
        i['hour_growth'] = 0
        if item_id in stars_history:
            i['hour_growth'] = current_stars - stars_history[item_id]
        
        # 注入智能标签
        i['smart_tags'] = get_smart_tags(i)
        qualified_items.append(i)

    # 排序：时速优先
    sorted_items = sorted(qualified_items, key=lambda x: (x['hour_growth'], x['stargazers_count']), reverse=True)
    explosive_items = [i for i in sorted_items if i['hour_growth'] >= GROWTH_THRESHOLD]
    new_items = [i for i in sorted_items if str(i['id']) not in pushed_ids]

    # --- 6. README 仪表盘构造 ---
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    md_content = f"# 🌊 GitHub 技术暗流雷达 (智能标签版)\n\n"
    md_content += f"> 🕒 更新: {now_str} | 🔥 爆发阈值: +{GROWTH_THRESHOLD} stars/hr\n\n"
    
    md_content += "## 🚀 每小时热度爆发榜\n"
    md_content += "| 增长/h | 智能标签 | 项目名称 | 总 Stars | 中文简介 |\n| :--- | :--- | :--- | :--- | :--- |\n"
    for i in sorted_items[:15]:
        growth_style = f"**🔥 +{i['hour_growth']}**" if i['hour_growth'] >= GROWTH_THRESHOLD else f"+{i['hour_growth']}"
        desc_zh = translate_to_zh(i['description'])
        md_content += f"| {growth_style} | {i['smart_tags']} | [{i['full_name']}]({i['html_url']}) | {i['stargazers_count']} | {desc_zh} |\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # --- 7. 飞书卡片推送 ---
    push_list = explosive_items + [i for i in new_items if i not in explosive_items]
    if push_list and FEISHU_WEBHOOK:
        card_elements = []
        for i in push_list[:5]:
            desc_zh = translate_to_zh(i['description'])
            growth_info = f"\n🚀 **时速: +{i['hour_growth']} stars/hr**" if i['hour_growth'] > 0 else ""
            status = "🔴 特急爆发" if i['hour_growth'] >= GROWTH_THRESHOLD else "✨ 发现新项目"
            
            card_elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"**{status}** | {i['smart_tags']}\n**项目**: [{i['full_name']}]({i['html_url']})\n**总 Stars**: `{i['stargazers_count']}`{growth_info}\n**简介**: {desc_zh}"}
            })
            card_elements.append({"tag": "hr"})

        requests.post(FEISHU_WEBHOOK, json={
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": "🛰️ 暗流情报: 智能分类版"}, "template": "red" if explosive_items else "orange"},
                "elements": card_elements
            }
        })

    # --- 8. 持久化 ---
    for i in new_items: pushed_ids.add(str(i['id']))
    with open(DB_FILE, "w") as f:
        for _id in pushed_ids: f.write(f"{_id}\n")
    with open(HISTORY_FILE, "w") as f:
        json.dump(current_stars_map, f)

except Exception as e:
    print(f"运行出错: {e}")
