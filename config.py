# -*- coding: utf-8 -*-
"""科技前沿日报 —— 配置文件（来源、领域、关键词）。

想增删来源、调整领域或关键词，只需要改这个文件，改完运行一次 update.py 即可生效。

关键词写法：
  * 普通字符串按“包含”匹配；英文/数字词自动加词边界，并兼容复数（chip -> chips）。
  * 全大写且不超过 6 个字符的词（AI、GPU、NASA ...）区分大小写，避免误伤普通单词。
  * 以 "re:" 开头表示原生正则，例如 "re:量子(?!位)"。
"""

# --------------------------------------------------------------------------
# 基本参数
# --------------------------------------------------------------------------
WINDOW_DAYS = 7          # 页面展示最近多少天
RETAIN_DAYS = 10         # 本地数据最多保留多少天
MAX_PER_DAY_CATEGORY = 40    # 每天每个领域最多保留多少条（按重要度取前 N）
MAX_PER_DAY_SOURCE = 14      # 每天每个来源最多保留多少条，防止高产来源刷屏
SUMMARY_WIDTH = 230      # 摘要最大显示宽度（汉字算 2，英文算 1）
FETCH_TIMEOUT = 20       # 单次网络读写超时（秒）
FETCH_DEADLINE = 45      # 单个来源总耗时上限（秒）
FETCH_WORKERS = 16       # 并发抓取线程数
MAX_FEED_BYTES = 8_000_000

# 领域（顺序即页面展示顺序）
CATEGORIES = [
    ("ai", "人工智能"),
    ("chip", "芯片与算力"),
    ("robot", "机器人与智能驾驶"),
    ("space", "航空航天"),
    ("comm", "通信与光电"),
    ("quantum", "量子科技"),
    ("bio", "生命科学与医药"),
    ("energy", "能源与材料"),
    ("science", "基础科学"),
]

# 多个领域得分相同时的取舍顺序：越靠前越优先（AI 几乎无处不在，所以排在后面）
TIE_BREAK = ["quantum", "comm", "robot", "chip", "space", "bio", "energy", "ai", "science"]


# --------------------------------------------------------------------------
# 来源
#   mode="all"    专业来源：全部保留，关键词不明显时归入 default 领域
#   mode="filter" 综合来源：只保留命中前沿关键词的条目
#   weight        来源权重，影响重要度排序
# --------------------------------------------------------------------------
def _s(id, name, url, home, lang="en", weight=1.0, mode="filter", default=None, **extra):
    d = dict(id=id, name=name, url=url, home=home, lang=lang, weight=weight,
             mode=mode, default=default)
    d.update(extra)
    return d


SOURCES = [
    # ---------------- 中文 ----------------
    _s("ithome", "IT之家", "https://www.ithome.com/rss/", "https://www.ithome.com/", "zh", 1.0),
    _s("cnbeta", "cnBeta", "https://rss.cnbeta.com.tw/", "https://www.cnbeta.com.tw/", "zh", 1.0),
    _s("solidot", "Solidot", "https://www.solidot.org/index.rss", "https://www.solidot.org/", "zh", 1.3),
    _s("qbitai", "量子位", "https://www.qbitai.com/feed", "https://www.qbitai.com/", "zh", 1.4,
       mode="all", default="ai"),
    _s("leiphone", "雷峰网", "https://www.leiphone.com/feed", "https://www.leiphone.com/", "zh", 1.1),
    _s("kr36", "36氪", "https://www.36kr.com/feed", "https://www.36kr.com/", "zh", 1.0),
    _s("huxiu", "虎嗅", "https://rss.huxiu.com/", "https://www.huxiu.com/", "zh", 0.9),
    _s("tmtpost", "钛媒体", "https://www.tmtpost.com/rss.xml", "https://www.tmtpost.com/", "zh", 1.0),
    _s("ifanr", "爱范儿", "https://www.ifanr.com/feed", "https://www.ifanr.com/", "zh", 0.9),
    _s("geekpark", "极客公园", "https://www.geekpark.net/rss", "https://www.geekpark.net/", "zh", 1.0),
    _s("infoq", "InfoQ", "https://www.infoq.cn/feed", "https://www.infoq.cn/", "zh", 1.0, no_summary=True),
    _s("mydrivers", "快科技", "https://rss.mydrivers.com/rss.aspx?Tid=1", "https://www.mydrivers.com/", "zh", 0.8),
    _s("expreview", "超能网", "https://www.expreview.com/rss.php", "https://www.expreview.com/", "zh", 0.9),
    _s("zhishifenzi", "知识分子", "http://www.zhishifenzi.com/rss", "http://www.zhishifenzi.com/", "zh", 1.4,
       mode="all", default="science"),

    # ---------------- 英文：综合科技 / 科学 ----------------
    _s("mittr", "MIT Technology Review", "https://www.technologyreview.com/feed/",
       "https://www.technologyreview.com/", weight=1.6),
    _s("nature", "Nature", "https://www.nature.com/nature.rss", "https://www.nature.com/",
       weight=1.6, only_url=r"/articles/d41586-"),          # d41586 = 新闻与评论，排除论文条目
    _s("quanta", "Quanta Magazine", "https://api.quantamagazine.org/feed/",
       "https://www.quantamagazine.org/", weight=1.7, mode="all", default="science"),
    _s("ieee", "IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss",
       "https://spectrum.ieee.org/", weight=1.6),
    _s("arstechnica", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index",
       "https://arstechnica.com/", weight=1.4),
    _s("mitnews", "MIT News", "https://news.mit.edu/rss/feed", "https://news.mit.edu/", weight=1.5),
    _s("aps", "APS Physics", "https://feeds.aps.org/rss/recent/physics.xml",
       "https://physics.aps.org/", weight=1.5, mode="all", default="science"),
    _s("sciam", "Scientific American", "https://www.scientificamerican.com/platform/syndication/rss/",
       "https://www.scientificamerican.com/", weight=1.4),
    _s("newscientist", "New Scientist", "https://www.newscientist.com/feed/home/",
       "https://www.newscientist.com/", weight=1.3),
    _s("techcrunch", "TechCrunch", "https://techcrunch.com/feed/", "https://techcrunch.com/", weight=1.1),
    _s("wired", "WIRED", "https://www.wired.com/feed/rss", "https://www.wired.com/", weight=1.0),
    _s("theverge", "The Verge", "https://www.theverge.com/rss/index.xml", "https://www.theverge.com/", weight=1.0),
    _s("hn", "Hacker News", "https://hnrss.org/frontpage", "https://news.ycombinator.com/",
       weight=1.0, no_summary=True),
    _s("sciencedaily", "ScienceDaily", "https://www.sciencedaily.com/rss/top/technology.xml",
       "https://www.sciencedaily.com/", weight=1.0),
    _s("newatlas", "New Atlas", "https://newatlas.com/index.rss", "https://newatlas.com/", weight=0.8),
    _s("interestingeng", "Interesting Engineering", "https://interestingengineering.com/feed",
       "https://interestingengineering.com/", weight=0.8),
    _s("scmp", "SCMP Tech", "https://www.scmp.com/rss/36/feed", "https://www.scmp.com/tech", weight=1.1),

    # ---------------- 英文：人工智能 ----------------
    _s("openai", "OpenAI", "https://openai.com/news/rss.xml", "https://openai.com/news/",
       weight=1.4, mode="all", default="ai"),
    _s("deepmind", "Google DeepMind", "https://deepmind.google/blog/rss.xml",
       "https://deepmind.google/blog/", weight=1.6, mode="all", default="ai"),
    _s("googleai", "Google AI Blog", "https://blog.google/technology/ai/rss/",
       "https://blog.google/technology/ai/", weight=1.3),
    _s("msr", "Microsoft Research", "https://www.microsoft.com/en-us/research/feed/",
       "https://www.microsoft.com/en-us/research/", weight=1.4, mode="all", default="ai"),
    _s("bair", "BAIR Blog", "https://bair.berkeley.edu/blog/feed.xml",
       "https://bair.berkeley.edu/blog/", weight=1.3, mode="all", default="ai"),
    _s("nvidia", "NVIDIA Blog", "https://blogs.nvidia.com/feed/", "https://blogs.nvidia.com/", weight=1.1),
    _s("decoder", "The Decoder", "https://the-decoder.com/feed/", "https://the-decoder.com/",
       weight=1.2, mode="all", default="ai"),
    _s("marktechpost", "MarkTechPost", "https://www.marktechpost.com/feed/",
       "https://www.marktechpost.com/", weight=0.9, mode="all", default="ai"),
    _s("simonw", "Simon Willison", "https://simonwillison.net/atom/everything/",
       "https://simonwillison.net/", weight=1.0),

    # ---------------- 英文：芯片与算力 ----------------
    _s("semieng", "Semiconductor Engineering", "https://semiengineering.com/feed/",
       "https://semiengineering.com/", weight=1.3, mode="all", default="chip"),
    _s("eetimes", "EE Times", "https://www.eetimes.com/feed/", "https://www.eetimes.com/",
       weight=1.3, mode="all", default="chip"),
    _s("semiwiki", "SemiWiki", "https://semiwiki.com/feed/", "https://semiwiki.com/",
       weight=1.0, mode="all", default="chip"),
    _s("digitimes", "DIGITIMES", "https://www.digitimes.com/rss/daily.xml",
       "https://www.digitimes.com/", weight=1.0),
    _s("tomshardware", "Tom's Hardware", "https://www.tomshardware.com/feeds/all",
       "https://www.tomshardware.com/", weight=1.0),

    # ---------------- 英文：航天与空间 ----------------
    _s("spacenews", "SpaceNews", "https://spacenews.com/feed/", "https://spacenews.com/",
       weight=1.5, mode="all", default="space"),
    _s("spaceflightnow", "Spaceflight Now", "https://spaceflightnow.com/feed/",
       "https://spaceflightnow.com/", weight=1.4, mode="all", default="space"),
    _s("nasa", "NASA", "https://www.nasa.gov/feed/", "https://www.nasa.gov/news/",
       weight=1.5, skip_url=r"/image-article/|/image-detail/"),
    _s("viasat", "Via Satellite", "https://www.satellitetoday.com/feed/",
       "https://www.satellitetoday.com/", weight=1.2, mode="all", default="space"),
    _s("spacepolicy", "SpacePolicyOnline", "https://spacepolicyonline.com/feed/",
       "https://spacepolicyonline.com/", weight=1.1, mode="all", default="space"),
    _s("spacecom", "Space.com", "https://www.space.com/feeds/all", "https://www.space.com/",
       weight=1.0, skip_url=r"/entertainment/|/stargazing/|/technology/"),
    _s("universetoday", "Universe Today", "https://www.universetoday.com/feed/",
       "https://www.universetoday.com/", weight=1.1, mode="all", default="science"),
    _s("phys_space", "Phys.org · Space", "https://phys.org/rss-feed/space-news/",
       "https://phys.org/space-news/", weight=1.0, mode="all", default="science"),

    # ---------------- 英文：通信与光电 ----------------
    _s("lightreading", "Light Reading", "https://www.lightreading.com/rss.xml",
       "https://www.lightreading.com/", weight=1.1),
    _s("rcrwireless", "RCR Wireless", "https://www.rcrwireless.com/feed",
       "https://www.rcrwireless.com/", weight=1.0),
    _s("techx_telecom", "Tech Xplore · Telecom", "https://techxplore.com/rss-feed/telecom-news/",
       "https://techxplore.com/telecom-news/", weight=1.0, mode="all", default="comm"),
    _s("phys_optics", "Phys.org · Optics", "https://phys.org/rss-feed/physics-news/optics-photonics/",
       "https://phys.org/physics-news/optics-photonics/", weight=1.0, mode="all", default="comm"),

    # ---------------- 英文：量子 ----------------
    _s("tqi", "The Quantum Insider", "https://thequantuminsider.com/feed/",
       "https://thequantuminsider.com/", weight=1.3, mode="all", default="quantum"),
    _s("qcr", "Quantum Computing Report", "https://quantumcomputingreport.com/feed/",
       "https://quantumcomputingreport.com/", weight=1.2, mode="all", default="quantum"),
    _s("phys_quantum", "Phys.org · Quantum", "https://phys.org/rss-feed/physics-news/quantum-physics/",
       "https://phys.org/physics-news/quantum-physics/", weight=1.0, mode="all", default="science"),

    # ---------------- 英文：生命科学与医药 ----------------
    _s("endpoints", "Endpoints News", "https://endpts.com/feed/", "https://endpts.com/",
       weight=1.2, mode="all", default="bio"),
    _s("biopharmadive", "BioPharma Dive", "https://www.biopharmadive.com/feeds/news/",
       "https://www.biopharmadive.com/", weight=1.1, mode="all", default="bio"),
    _s("statnews", "STAT", "https://www.statnews.com/feed/", "https://www.statnews.com/", weight=1.3),
    _s("phys_bio", "Phys.org · Biotech", "https://phys.org/rss-feed/biology-news/biotechnology/",
       "https://phys.org/biology-news/biotechnology/", weight=1.0, mode="all", default="bio"),

    # ---------------- 英文：能源与材料 ----------------
    _s("wnn", "World Nuclear News", "https://www.world-nuclear-news.org/rss",
       "https://www.world-nuclear-news.org/", weight=1.2, mode="all", default="energy"),
    _s("canary", "Canary Media", "https://www.canarymedia.com/rss.rss",
       "https://www.canarymedia.com/", weight=1.1),
    _s("electrek", "Electrek", "https://electrek.co/feed/", "https://electrek.co/", weight=0.9),
    _s("techx_energy", "Tech Xplore · Energy", "https://techxplore.com/rss-feed/energy-green-tech-news/",
       "https://techxplore.com/energy-green-tech-news/", weight=1.0, mode="all", default="energy"),
    _s("phys_materials", "Phys.org · Materials", "https://phys.org/rss-feed/chemistry-news/materials-science/",
       "https://phys.org/chemistry-news/materials-science/", weight=1.0, mode="all", default="energy"),
    _s("phys_nano", "Phys.org · Nanotech", "https://phys.org/rss-feed/nanotech-news/",
       "https://phys.org/nanotech-news/", weight=1.0, mode="all", default="energy"),

    # ---------------- 英文：机器人 ----------------
    _s("techx_robotics", "Tech Xplore · Robotics", "https://techxplore.com/rss-feed/robotics-news/",
       "https://techxplore.com/robotics-news/", weight=1.0, mode="all", default="robot"),
    _s("robohub", "Robohub", "https://robohub.org/feed/", "https://robohub.org/",
       weight=1.0, mode="all", default="robot"),
]


# --------------------------------------------------------------------------
# 领域关键词：strong = 强信号，weak = 弱信号（需要和其它词一起出现才算数）
# --------------------------------------------------------------------------
KEYWORDS = {
    "ai": {
        "strong": [
            # 中文
            "大模型", "语言模型", "智能体", "多模态", "生成式", "通用人工智能", "人工智能", "超级智能", "神经网络",
            "深度学习", "机器学习", "强化学习", "扩散模型", "开源模型", "推理模型", "世界模型", "基础模型",
            "文生图", "文生视频", "提示词", "深度求索", "通义千问", "通义", "文心", "豆包", "混元", "智谱",
            "月之暗面", "阶跃星辰", "讯飞星火", "商汤", "盘古大模型", "编程助手", "数字人", "词元",
            # 英文 / 产品与机构
            "AIGC", "AGI", "LLM", "large language model", "language model", "re:GPT-?\\d[\\w.]*", "ChatGPT",
            "OpenAI", "Anthropic", "Claude", "Gemini", "DeepMind", "DeepSeek", "Llama", "Mistral", "xAI",
            "Grok", "Copilot", "Hugging Face", "generative AI", "gen AI", "superintelligence", "AI agent",
            "agentic", "multimodal", "neural network", "neural net", "deep learning", "machine learning",
            "reinforcement learning", "diffusion model", "foundation model", "world model", "AI model",
            "chatbot", "artificial intelligence", "AI safety", "Sora", "Midjourney", "Stable Diffusion",
            "Qwen", "Kimi", "MiniMax", "Codex", "vibe coding", "AI coding", "Perplexity", "fine-tuning",
            "open-source model", "open-weight", "text-to-image", "text-to-video", "computer vision",
            "natural language processing", "AlphaFold", "AlphaGo", "PyTorch", "TensorFlow",
            # 带版本号的模型名：Qwen3.8、Claude 5、GLM-5.3 ...
            "re:(?<![A-Za-z])(?:Qwen|Llama|GLM|Kimi|ERNIE|Gemma|DeepSeek|Mistral|Claude|Gemini|Grok)[- ]?\\d[\\w.\\-]*",
        ],
        "weak": ["AI", "re:(?-i:A\\.I\\.)", "模型", "算法", "训练", "推理", "智能", "model", "algorithm",
                 "inference", "benchmark", "prompt", "token", "transformer", "agent"],
    },
    "chip": {
        "strong": [
            "芯片", "半导体", "晶圆", "光刻", "制程", "先进封装", "台积电", "中芯国际", "英伟达", "阿斯麦",
            "海力士", "美光", "寒武纪", "长江存储", "长鑫", "存储芯片", "算力", "智算", "数据中心", "超算",
            "超级计算机", "晶体管", "集成电路", "硅光", "碳化硅", "氮化镓", "龙芯", "昇腾", "光子芯片",
            "semiconductor", "chip", "chipmaker", "wafer", "lithography", "EUV", "TSMC", "Nvidia", "ASML",
            "Micron", "SK Hynix", "foundry", "GPU", "HBM", "DRAM", "NAND", "transistor", "RISC-V",
            "data center", "datacenter", "supercomputer", "exascale", "advanced packaging",
            "silicon photonics", "re:\\b[1-9]nm\\b", "re:\\b1[0-8]A\\b", "process node", "ASIC", "FPGA",
            "EDA", "AI accelerator", "chip design", "integrated circuit", "gallium nitride", "silicon carbide",
            "CoWoS", "interposer", "chiplet", "re:\\bexport[- ]controls?\\b", "TPU",
        ],
        "weak": ["处理器", "显卡", "内存", "存储", "服务器", "封装", "高通", "联发科", "英特尔", "博通", "三星",
                 "CPU", "NPU", "AMD", "Intel", "Qualcomm", "Broadcom", "Samsung", "processor", "memory",
                 "compute", "server", "hardware", "silicon", "fab"],
    },
    "robot": {
        "strong": [
            "机器人", "具身智能", "具身", "机器狗", "机械臂", "灵巧手", "外骨骼", "自动驾驶", "无人驾驶",
            "智能驾驶", "智驾", "辅助驾驶", "无人车", "萝卜快跑", "无人机", "低空经济", "飞行汽车", "宇树",
            "优必选", "智元", "银河通用", "波士顿动力", "擎天柱",
            "robot", "robotic", "robotics", "humanoid", "embodied AI", "embodied intelligence",
            "autonomous vehicle", "self-driving", "driverless", "robotaxi", "Waymo", "Optimus",
            "Boston Dynamics", "Unitree", "drone", "eVTOL", "quadruped", "exoskeleton",
            "autonomous driving", "FSD", "Cybercab", "legged", "manipulator", "teleoperation",
        ],
        "weak": ["自动化", "无人", "automation", "autonomous", "autonomy", "gripper", "actuator"],
    },
    "space": {
        "strong": [
            "航天", "火箭", "卫星", "空间站", "探月", "登月", "嫦娥", "天问", "天宫", "天舟", "月球", "火星",
            "深空", "探测器", "星舰", "星链", "蓝色起源", "商业航天", "遥感", "北斗", "千帆", "朱雀", "蓝箭",
            "小行星", "太空", "宇航员", "航天员", "re:神舟[一二三四五六七八九十\\d]+", "re:长征[一二三四五六七八九十\\d]+",
            "旅行者", "Voyager",
            # 航空
            "首飞", "试飞", "航空发动机", "大飞机", "电动飞机", "超音速", "高超音速", "无人货机", "C919", "C929",
            "supersonic", "hypersonic", "maiden flight", "first flight", "electric aircraft", "scramjet",
            "jet engine",
            "rocket", "satellite", "spacecraft", "SpaceX", "Starship", "Starlink", "Falcon 9", "Falcon Heavy",
            "Blue Origin", "New Glenn", "Rocket Lab", "NASA", "ESA", "JAXA", "ISRO", "CNSA", "Roscosmos",
            "Artemis", "lunar", "Mars", "space station", "ISS", "astronaut", "lander", "rover", "asteroid",
            "spaceflight", "Space Force", "launch vehicle", "LEO", "geostationary", "space debris",
            "deep space", "spaceplane", "Chang'e", "Tiangong", "Shenzhou", "Long March", "Tianwen",
            "Europa Clipper", "Ariane", "smallsat", "cubesat", "space economy", "in orbit", "low Earth orbit",
            "liftoff", "launch pad", "launch site", "launch window", "rocket launch", "space launch",
        ],
        "weak": ["发射", "轨道", "星座", "载人", "着陆", "低轨", "飞机", "航空", "客机", "orbit",
                 "orbital", "moon", "payload", "constellation", "booster", "reusable", "space", "Kuiper",
                 "Vulcan", "aircraft", "aviation", "airplane"],
    },
    "comm": {
        "strong": [
            "卫星互联网", "卫星通信", "激光通信", "星间链路", "星间激光", "光通信", "光纤", "太赫兹", "基站",
            "直连卫星", "手机直连", "光模块", "移动通信", "天地一体", "毫米波", "通感一体", "海底光缆", "海缆",
            "通信技术", "5G-A", "激光器", "光子", "光电子", "光电探测", "光学", "光计算", "超表面", "光频梳",
            "光波导",
            "6G", "5G", "satellite internet", "direct-to-cell", "direct-to-device", "laser communication",
            "optical communication", "lasercom", "laser link", "optical link", "inter-satellite link",
            "intersatellite", "free-space optical", "optical fiber", "fiber optic", "fibre", "hollow-core",
            "terahertz", "telecom", "telecommunication", "broadband", "non-terrestrial network",
            "submarine cable", "undersea cable", "subsea cable", "base station", "Ericsson", "Nokia",
            "optical transceiver", "co-packaged optics", "satcom", "mmWave", "Open RAN", "AI-RAN",
            "photonic", "photonics", "optoelectronic", "metasurface", "waveguide",
            "frequency comb", "optical computing", "fiber laser", "wireless network", "cellular network",
        ],
        "weak": ["运营商", "星地", "频谱", "宽带", "通信", "激光", "光电", "中国移动", "中国电信", "中国联通",
                 "华为", "中兴", "Huawei", "wireless", "Wi-Fi", "antenna", "spectrum", "T-Mobile", "Verizon",
                 "connectivity", "laser", "optical", "optics", "network operator", "carrier"],
    },
    "quantum": {
        "strong": ["re:量子(?!位)", "quantum", "qubit", "IonQ", "Rigetti", "D-Wave", "Quantinuum",
                   "PsiQuantum", "trapped ion", "neutral atom", "post-quantum"],
        "weak": ["纠缠", "叠加态", "entanglement", "superposition", "cryogenic"],
    },
    "bio": {
        "strong": [
            "基因", "细胞", "蛋白质", "疫苗", "新药", "创新药", "药物", "药企", "临床", "抗体", "癌", "肿瘤",
            "阿尔茨海默", "脑机接口", "合成生物", "生物技术", "生物医药", "生物制造", "生物学", "医学", "免疫",
            "测序", "类器官", "神经科学", "脑科学", "神经元", "抗衰老", "衰老", "减肥药", "司美格鲁肽",
            "替尔泊肽", "器官移植", "异种移植", "微生物", "药监局",
            "gene", "genetic", "genome", "genomic", "CRISPR", "gene therapy", "gene editing", "cell therapy",
            "stem cell", "protein", "vaccine", "drug", "clinical trial", "antibody", "antibodies", "cancer",
            "tumor", "Alzheimer", "brain-computer interface", "BCI", "Neuralink", "synthetic biology",
            "biotech", "biotechnology", "pharma", "pharmaceutical", "FDA", "mRNA", "DNA", "RNA",
            "immunotherapy", "CAR-T", "GLP-1", "Ozempic", "Wegovy", "semaglutide", "tirzepatide",
            "organoid", "neuroscience", "longevity", "H5N1", "bird flu", "microbiome", "biology",
            "biologist", "neuron", "therapy", "therapies", "therapeutic", "enzyme", "bacteria", "biomarker",
            "embryo", "xenotransplant", "obesity", "bionic", "implant", "prosthetic",
        ],
        "weak": ["医疗", "病毒", "医保", "诊断", "医院", "患者", "健康", "大脑", "蛋白", "health", "patient",
                 "medical", "medicine", "brain", "disease", "virus", "cell", "clinical"],
    },
    "energy": {
        "strong": [
            "核聚变", "聚变", "核电", "核能", "反应堆", "核燃料", "固态电池", "锂电池", "锂电", "钠离子",
            "动力电池", "储能", "光伏", "钙钛矿", "太阳能", "风电", "氢能", "绿氢", "制氢", "氢燃料", "超导",
            "新材料", "石墨烯", "碳纤维", "催化剂", "纳米材料", "二维材料", "超材料", "电网", "特高压",
            "托卡马克", "人造太阳", "熔盐堆", "光催化", "电催化", "电解水", "热电",
            "nuclear fusion", "fusion energy", "fusion reactor", "fusion power", "fusion plant", "tokamak",
            "stellarator", "nuclear power", "nuclear plant", "nuclear energy", "nuclear reactor",
            "nuclear fuel", "nuclear industry", "water splitting",
            "reactor", "SMR", "battery", "batteries", "solid-state", "lithium",
            "sodium-ion", "energy storage", "solar power", "solar panel", "solar cell", "solar farm",
            "solar energy", "photovoltaic", "perovskite", "wind turbine", "offshore wind", "green hydrogen",
            "hydrogen fuel", "fuel cell", "electrolyzer", "superconductor", "superconducting",
            "superconductivity", "graphene", "carbon capture", "clean energy", "renewable", "geothermal",
            "catalyst", "2D material", "metamaterial", "nanomaterial", "nanoparticle", "materials science",
            "heat pump", "thermoelectric", "alloy", "polymer", "electrolyte", "cathode", "anode",
        ],
        "weak": ["电池", "新能源", "碳中和", "材料", "能源", "发电", "合金", "宁德时代", "energy",
                 "material", "fusion", "solar", "hydrogen", "grid", "power plant", "nuclear", "EV",
                 "electric vehicle"],
    },
    "science": {
        "strong": [
            "物理学", "天文", "宇宙", "黑洞", "引力波", "暗物质", "暗能量", "中子星", "系外行星", "望远镜",
            "韦布", "中国天眼", "对撞机", "希格斯", "中微子", "数学家", "猜想", "定理", "诺贝尔", "诺奖",
            "化学家", "超新星", "星系", "银河系", "脉冲星", "反物质", "夸克", "凝聚态", "拓扑",
            "telescope", "JWST", "James Webb", "Hubble", "Euclid", "Chandra", "Rubin Observatory", "galaxy",
            "galaxies", "black hole", "dark matter", "dark energy", "neutron star", "supernova", "exoplanet",
            "gravitational wave", "cosmic", "cosmology", "astronomer", "astronomy", "astrophysics",
            "astrophysicist", "physicist", "physics", "collider", "CERN", "LHC", "Higgs", "neutrino",
            "mathematician", "mathematics", "theorem", "conjecture", "Nobel", "chemist", "chemistry",
            "dwarf planet", "magnetar", "pulsar", "quasar", "Big Bang", "antimatter", "muon", "quark",
            "condensed matter", "topological", "string theory", "Milky Way",
            "mathematical", "Einstein", "relativity", "gravity", "white dwarf", "solar system", "Saturn",
            "Jupiter", "Uranus", "Neptune", "Pluto", "comet", "meteorite",
        ],
        "weak": ["物理", "数学", "化学", "科学家", "研究人员", "研究发现", "论文", "深海", "极地", "南极",
                 "particle", "math", "planet", "universe", "molecule", "atom", "scientist", "researcher",
                 "study", "Antarctic", "ocean", "photon", "electron"],
    },
}

# 提升重要度的词（突破性、首次、发布等）
BOOST = [
    "首次", "首个", "首款", "首台", "首颗", "全球首", "世界首", "国内首", "突破", "重大", "里程碑", "刷新",
    "纪录", "创纪录", "问世", "发布", "开源", "量产", "获批", "成功", "发射", "上线", "诺贝尔",
    "first", "breakthrough", "record", "milestone", "unveil", "unveiled", "announce", "announced",
    "launches", "launched", "release", "released", "open-source", "open-sourced", "approve", "approved",
    "achieve", "achieved", "demonstrate", "demonstrated", "discover", "discovered", "discovery",
    "state-of-the-art", "world's", "introducing", "largest", "fastest",
]

# 标题命中即丢弃：促销、消费电子导购、娱乐、汇总类稿件等与“前沿进展”无关的内容
EXCLUDE_TITLE = [
    # 中文
    "优惠", "促销", "秒杀", "红包", "国补", "到手", "立减", "券后", "首销", "开售", "预售", "开卖", "上架",
    "元起", "售价", "图赏", "壁纸", "京东", "天猫", "拼多多", "双11", "双十一",
    "re:(评测|测评|体验|上手|开箱)\\s*[：:｜|丨]", "re:(评测|测评|开箱|上手)$",
    "福利", "抽奖", "预告", "定档", "票房", "剧集", "综艺", "演唱会", "游戏本", "耳机", "手环", "显示器",
    "路由器", "键盘", "鼠标", "充电宝", "新机", "真机", "渲染图", "配色", "招聘", "早报", "晚报", "周报",
    "日报", "1氪", "今日热点", "扫地", "洗地机", "空调", "冰箱", "洗衣机", "投影", "手游", "网游", "皮肤",
    "优酷", "爱奇艺", "直播带货", "体验官", "一图看懂", "盘点", "极客早知道",
    "re:[；;].*[；;]",          # 一个标题里塞了三件事的“早知道/晚报”类汇总
    # 英文
    "re:\\bdeals?\\b", "re:\\bon sale\\b", "coupon", "discount", "re:% off\\b", "price drop",
    "re:\\bbest .{0,40}\\b(to buy|of 20\\d\\d|for 20\\d\\d|you can buy)", "re:\\breview\\b", "hands-on",
    "re:\\bhow to (watch|get|use|buy|set up|build)\\b", "gift guide", "Black Friday", "Cyber Monday",
    "Prime Day", "giveaway", "sponsored", "webinar", "trailer", "Wordle", "crossword", "podcast",
    "re:\\bepisode \\d+", "re:^opinion\\b", "quiz", "newsletter", "re:^the download\\b", "daily briefing",
    "re:^APOD\\b", "re:\\binvites media\\b", "re:\\bto discuss\\b", "re:\\bsets coverage\\b",
    "re:^last week in\\b", "re:\\btutorial\\b", "re:\\bstep-by-step\\b", "re:\\bcoding (guide|implementation)\\b",
    "re:\\bweekly\\b", "re:\\bthis week in\\b", "re:\\bmorning rounds\\b", "re:^video friday\\b",
    "re:\\bweek in review\\b", "puzzle", "obituary", "re:\\bQ&A\\b", "re:^how I\\b", "in memoriam",
    "Robot Talk", "re:\\bpromo codes?\\b", "re:^show hn\\b", "re:^on this day\\b", "of the month",
    "re:^I Am Artemis\\b", "photo of the day",
]

# feed 自带的栏目标签命中即丢弃（整词匹配，不分大小写）
EXCLUDE_CATEGORY = [
    "Press Release", "Press Releases", "Sponsored", "Sponsored Content", "Sponsored Post",
    "Partner Content", "Advertorial", "Podcast", "Podcasts", "Deals", "Deal", "Coupons",
    "Space Minds Podcast",
]

# 摘要清洗：去掉来源套话、“阅读全文”等尾巴
SUMMARY_STRIP = [
    r"^IT之家\s*\d+\s*月\s*\d+\s*日消息[，,]\s*",
    r"^快科技\s*\d+\s*月\s*\d+\s*日(消息|讯)[，,]\s*",
    r"^本文来自微信公众号[:：][^。]{0,160}?(题图|头图)[^。 ]{0,40}\s*",
    r"\s*(阅读全文|查看全文|点击查看原文\s*>?|查看原文)\s*$",
    r"\s*#欢迎关注爱范儿.*$",
    r"\s*The post .{0,300}?(appeared first on|first appeared on).{0,120}$",
    r"\s*(Read more|Read More|Continue reading|Read the full story)\s*(»|→|\.{3}|…)?\s*$",
    r"\s*\[(…|\.\.\.)\]\s*$",
    r"^(?:(?:Insider Brief|PRESS RELEASE)\s*(?:—|–|-|:)?\s*)+",
    r"^Author\(s\):\s*",
]
