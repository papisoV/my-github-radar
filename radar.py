import requests
import datetime
import os
import json
import urllib.parse

# --- 1. 配置区 ---
FEISHU_WEBHOOK = os.getenv('FEISHU_WEBHOOK')
DB_FILE = "pushed_ids.txt"
HISTORY_FILE = "stars_history.json"
# 强烈建议在 GitHub Secrets 中配置 MY_GITHUB_TOKEN
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') 

BLACK_LIST = ["awesome", "roadmap", "interview", "collection", "guide", "free-courses"]
# 知名大厂/机构名单
FAMOUS_ORGS = ["vercel", "openai", "anthropic", "meta", "google", "microsoft", "bytedance", "alibaba", "xai-org", "nvidia", "cloudflare"]
GROWTH_THRESHOLD = 50  # 爆发阈值：50 stars/hr

# --- 2. 核心功能函数 ---

def get_owner_fame(owner_name):
    """识别 Owner 是否是大佬或大厂"""
    if owner_name.lower() in FAMOUS_ORGS:
        return "🏢 大厂官号"
    
    if GITHUB_TOKEN:
        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            # 查询作者最火的项目，判断其实力
            user_url = f"https://api.github.com/users/{owner_name}/repos?sort=stars&per_page=1"
            res = requests.get(user_url, headers=headers, timeout=5).json()
            if isinstance(res, list) and len(res) > 0:
                if res[0]['stargazers_count'] > 10000:
                    return "👑 大佬回归"
        except:
            pass
    return ""

def get_smart_tags(item):
    """根据项目描述自动识别技术标签"""
    name_desc = (item['full_name'] + (item['description'] or "")).lower()
    tags = []
    if item['language']:
        tags.append(f"🏷️{item['language']}")
    
    topics = {
        "🤖 AI/ML": ["llm", "ai", "gpt", "claude", "agent", "rag", "inference", "stable-diffusion"],
        "🌐 Web/Frontend": ["react", "vue", "typescript", "tailwind", "nextjs", "browser"],
        "⚙️ Tooling": ["cli", "workflow", "automation", "scripts"],
        "🦀 Performance": ["rust", "performance", "blazing", "cuda", "cpp"],
        "☁️ DevOps": ["docker", "k8s", "aws", "serverless", "cloudflare"]
    }
    for tag, keywords in topics.items():
        if any(key in name_desc for key in keywords):
            tags.append(tag)
    return " ".join(tags[:3])

def translate_to_zh(text):
    """简单的 Google 翻译接口，用于翻译项目简介"""
    if not text: return "无描述"
    try:
        base_url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q="
        res = requests.get(base_url + urllib.parse.quote(text), timeout=5)
        return "".join([i[0] for i in res.json()[0]])
    except:
        return text

def get_external_insight(full_name, repo_url):
    """
    寻找跨界关联：HN 讨论与 Google 趋势预判
    """
    insight = {"hn_url": None, "tag": "", "score_bonus": 0}
    try:
        # 1. 搜索 Hacker News 关联
        search_str = urllib.parse.quote(full_name)
        hn_api = f"https://hn.algolia.com/api/v1/search?query={search_str}&tags=story"
        res = requests.get(hn_api, timeout=5).json()
        
        if res['nbHits'] > 0:
            top_story = res['hits'][0]
            comment_count = top_story.get('num_comments', 0)
            insight["hn_url"] = f"https://news.ycombinator.com/item?id={top_story['objectID']}"
            
            # 质量判定：有讨论的项目权重更高
            if comment_count > 30:
                insight["tag"] = f"🔥 HN 热议({comment_count})"
                insight["score_bonus"] = 2000 # 极大幅度提升优先级
            else:
                insight["tag"] = "🔍 极客关注"
                insight["score_bonus"] = 500
    except:
        pass
    return insight

# --- 3. 时间与数据加载 ---
# 关键：修正为北京时间 (UTC+8)
now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
now_str = now.strftime('%Y-%m-%d %H:%M:%S')

pushed_ids = set()
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r") as f:
        pushed_ids = set(line.strip() for line in f if line.strip())

stars_history = {}
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        try: stars_history = json.load(f)
        except: stars_history = {}

# --- 4. 抓取与处理 ---
start_date = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
# 增加一个搜索范围，支持抓取最近 1 年内创建的高星项目（成长期项目）
query = f"created:>{start_date} stars:>500 fork:false"
url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"

try:
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    response = requests.get(url, headers=headers)
    items = response.json().get('items', [])
    if not items: exit(0)

    current_stars_map = {}
    qualified_items = []
    
    for i in items:
        # 1. 基础黑名单过滤
        if any(word in (i['full_name']+(i['description'] or "")).lower() for word in BLACK_LIST):
            continue

        # 2. 活跃度过滤器：必须在 48 小时内有代码推送 (pushed_at)
        # 排除那些只有 Star 在涨但代码已断更的“僵尸/营销”项目
        pushed_at = datetime.datetime.strptime(i['pushed_at'], '%Y-%m-%dT%H:%M:%SZ') + datetime.timedelta(hours=8)
        if (now - pushed_at).total_seconds() > 48 * 3600:
            continue
            
        item_id = str(i['id'])
        current_stars = i['stargazers_count']
        current_stars_map[item_id] = current_stars
        
        # 3. 计算斜率 (增长时速)
        base_growth = 0
        if item_id in stars_history:
            base_growth = current_stars - stars_history[item_id]
        
        # 4. 识别大佬画像 (核心权重逻辑)
        fame_tag = get_owner_fame(i['owner']['login'])
        
        # 存储原始数据
        i['raw_growth'] = base_growth
        i['hour_growth'] = base_growth 
        i['fame_tag'] = fame_tag
        
        # --- 新增：跨界情报获取 ---
        # 只有当时速爆发(>30)或大佬项目时，才去查 HN，避免浪费请求
        i['hn_info'] = None
        if i['raw_growth'] > 30 or fame_tag:
            i['hn_info'] = get_hn_context(i['full_name'])
            if i['hn_info'] and i['hn_info']['comments'] > 10:
                i['hour_growth'] += 2000 # 深度讨论的项目，权重直接拉满
                i['smart_tags'] += " 🔥极客热议"

        i['smart_tags'] = (f"{fame_tag} " if fame_tag else "") + get_smart_tags(i)
        qualified_items.append(i)

        # 5. 动态权重分配
        # 条件 A：大佬/大厂项目，给予最高优先级提拔
        if fame_tag:
             i['hour_growth'] += 10000 
        # 条件 B：成名大作 (Star > 10k) 且依然在高速增长，给予额外关注度
        elif current_stars > 10000 and base_growth > 30:
             i['hour_growth'] += 500
        
        i['fame_tag'] = fame_tag
        i['smart_tags'] = (f"{fame_tag} " if fame_tag else "") + get_smart_tags(i)
        qualified_items.append(i)

    # 排序：根据权重后的 hour_growth 排序，确保大佬和爆发项目排在 README 最前面
    sorted_items = sorted(qualified_items, key=lambda x: x['hour_growth'], reverse=True)
    
    # 飞书触发器逻辑：
    # 触发条件：时速爆发 (>=50) OR (是大佬项目且时速 > 20)
    explosive_items = [i for i in sorted_items if i['raw_growth'] >= GROWTH_THRESHOLD or (i['fame_tag'] and i['raw_growth'] > 20)]
    
    # 新发现逻辑：从未推送过的项目
    new_items = [i for i in sorted_items if str(i['id']) not in pushed_ids]

    # --- 5. README 构造 ---
    md_content = f"# 🌊 GitHub 技术暗流雷达 (情报员版)\n\n"
    md_content += f"> 🕒 更新: {now_str} (北京时间) | 👑 = 万星作者 | 🏢 = 核心机构\n\n"
    md_content += "| 增长/h | 智能标签 | 项目名称 | 总 Stars | 中文简介 |\n| :--- | :--- | :--- | :--- | :--- |\n"
    
    for i in sorted_items[:15]:
        growth_style = f"**🔥 +{i['raw_growth']}**" if i['raw_growth'] >= GROWTH_THRESHOLD else f"+{i['raw_growth']}"
        desc_zh = translate_to_zh(i['description'])
        md_content += f"| {growth_style} | {i['smart_tags']} | [{i['full_name']}]({i['html_url']}) | {i['stargazers_count']} | {desc_zh} |\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)

    # --- 6. 飞书卡片推送 (智能汇总模式) ---
    # 汇总时间点（北京时间 9 点和 21 点）
    SUMMARY_HOURS = [9, 21]  
    is_summary_time = now.hour in SUMMARY_HOURS

    if is_summary_time:
        push_candidates = sorted_items[:8]
        card_title = "📊 GitHub 技术趋势汇总"
        card_template = "blue"
        status_prefix = "📈 榜单 Top"
    else:
        push_candidates = explosive_items + [i for i in new_items if i not in explosive_items]
        card_title = "🛰️ 顶级技术情报"
        is_fame = push_candidates[0].get('fame_tag') if push_candidates else False
        card_template = "purple" if is_fame else "orange"
        status_prefix = ""

    if push_candidates and FEISHU_WEBHOOK:
        card_elements = []
        limit = 8 if is_summary_time else 5
        
        for idx, i in enumerate(push_candidates[:limit]):
            desc_zh =translate_to_zh(i['description'])
            growth_info = f"\n🚀 **时速: +{i['raw_growth']} stars/hr**" if i['raw_growth'] > 0 else ""

            hn_text = ""
            if i.get('hn_info'):
                hn_text = f"\n🌐 **HN讨论**: [{i['hn_info']['points']}分/{i['hn_info']['comments']}评]({i['hn_info']['url']})"
            
            if is_summary_time:
                status = f"{status_prefix} {idx+1}"
            else:
                status = "🚨 大佬动向" if i['fame_tag'] else ("🔴 特急爆发" if i['raw_growth'] >= GROWTH_THRESHOLD else "✨ 发现新项目")
            
            card_elements.append({
                "tag": "div",
               text": {
                    "tag": "lark_md", 
                    "content": f"**{status}** | {i['smart_tags']}\n**项目**: [{i['full_name']}]({i['html_url']})\n**总 Stars**: `{i['stargazers_count']}`{growth_info}{hn_text}\n**简介**: {desc_zh}"
                }
            })
            card_elements.append({"tag": "hr"})

        requests.post(FEISHU_WEBHOOK, json={
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": card_title}, "template": card_template},
                "elements": card_elements
            }
        })

    # --- 7. 持久化 ---
    for i in new_items: pushed_ids.add(str(i['id']))
    with open(DB_FILE, "w") as f:
        for _id in pushed_ids: f.write(f"{_id}\n")
    with open(HISTORY_FILE, "w") as f:
        json.dump(current_stars_map, f)

except Exception as e:
    print(f"运行出错: {e}")
