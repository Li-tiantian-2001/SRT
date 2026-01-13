import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from urllib import request


if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    CONFIG_PATH = os.path.join(APP_DIR, "launcher", "config.json")
else:
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

LOG_DIR = os.path.join(APP_DIR, "logs")
SAMPLES_DIR = os.path.join(APP_DIR, "samples")

# ========== 字幕处理常量 ==========
# 字符限制
MAX_CN_CHARS = 20         # 中文单行最大字符
MAX_EN_CHARS = 42         # 英文单行最大字符

# 时长限制
MIN_DURATION = 0.8        # 最小时长(秒)
MAX_DURATION = 4.2        # 最大时长(秒)

# 阅读速度限制（字符/秒）
MAX_CPS_CN = 7.5          # 中文最大阅读速度
MAX_CPS_EN = 17.0         # 英文最大阅读速度

# 时间轴间隙
MIN_GAP = 0.05            # 最小间隙(秒)
MAX_GAP = 0.12            # 最大间隙(秒)


def resolve_path(value, default_value):
    path = value or default_value
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(APP_DIR, path))


def load_config():
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "default_model_dir": "./models",
        "default_output_dir": "./SRT_OUT",
        "default_input_dir": "",
        "media_extensions": [".mp4", ".mov", ".m4a", ".mp3", ".wav"],
        "required_model_files": ["tokens.txt", "model.onnx", "silero_vad.onnx"],
        "required_ffmpeg_files": ["ffmpeg.exe", "ffprobe.exe"],
        "script_rel_path": "./vendor/sherpa-onnx/python-api-examples/generate-subtitles.py",
        "script_args_template": [
            "--tokens",
            "{model_dir}/tokens.txt",
            "--paraformer",
            "{model_dir}/model.onnx",
            "--silero-vad-model",
            "{model_dir}/silero_vad.onnx",
            "--num-threads",
            "4",
            "--decoding-method",
            "greedy_search",
            "{input_media}",
        ],
        "download_sources": {"github": {}, "hf_mirror": {}},
    }


def ensure_dirs():
    for name in ("SRT_OUT", "CACHE", "logs"):
        os.makedirs(os.path.join(APP_DIR, name), exist_ok=True)


def is_media_file(path, exts):
    _, ext = os.path.splitext(path)
    return ext.lower() in exts


def list_media_files(folder, exts):
    files = []
    for root, _, names in os.walk(folder):
        for name in names:
            full = os.path.join(root, name)
            if is_media_file(full, exts):
                files.append(full)
    return files


def strip_punctuation(text):
    """移除所有标点符号（保留空格）"""
    return re.sub(r"[，,。.!！?？；;：:、\"""'''()（）\[\]{}<>《》]+", "", text)


def split_by_punctuation(text):
    """按标点符号分割文本（保留标点用于断句）"""
    # 按句末标点分割
    parts = re.split(r"([。.!！?？；;]+)", text)
    result = []
    current = ""
    for i, part in enumerate(parts):
        if i % 2 == 0:  # 文本部分
            current += part
        else:  # 标点部分
            current += part
            if current.strip():
                result.append(current.strip())
            current = ""
    if current.strip():
        result.append(current.strip())
    return result


def is_chinese_text(text):
    """判断文本是否主要是中文"""
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cjk_count > len(text) / 3


def calculate_char_count(text):
    """计算字符数（中文按字数，英文按字符数）"""
    clean = strip_punctuation(text)
    if is_chinese_text(clean):
        # 中文：计算汉字数量
        return len(re.findall(r"[\u4e00-\u9fff]", clean))
    else:
        # 英文：计算字符数（不含空格）
        return len(clean.replace(" ", ""))


def calculate_reading_speed(text, duration):
    """计算阅读速度（字符/秒）"""
    if duration <= 0:
        return float('inf')
    char_count = calculate_char_count(text)
    return char_count / duration


def get_max_cps(text):
    """获取文本的最大阅读速度限制"""
    return MAX_CPS_CN if is_chinese_text(text) else MAX_CPS_EN


def get_max_chars(text):
    """获取文本的最大字符限制"""
    return MAX_CN_CHARS if is_chinese_text(text) else MAX_EN_CHARS


# ========== 中文断句辅助 ==========
# 常见的句子边界词（在这些词后面断开是安全的）
BREAK_AFTER_WORDS = {
    # 语气词/助词
    "的", "了", "吧", "呢", "啊", "哦", "嘛", "呀", "哈", "吗", "啦", "喽",
    # 标点替代
    "就是", "但是", "所以", "因为", "然后", "而且", "或者", "如果", "那么",
    "不过", "可是", "虽然", "既然", "无论", "不管", "只要", "除非", "即使",
    # 动词/连接
    "可以", "需要", "应该", "必须", "能够", "不能", "不要", "一定", 
    "建议", "推荐", "记住", "注意", "首先", "其次", "最后", "第一", "第二", "第三",
}

# 禁止在这些词中间断开
PROTECTED_WORDS = {
    "网络", "账号", "密码", "邮箱", "手机", "电脑", "浏览器", "服务器",
    "平台", "软件", "工具", "视频", "音频", "文件", "目录", "路径",
    "安全", "隐私", "环境", "设备", "系统", "功能", "内容", "信息",
    "规则", "意识", "言论", "敏感", "高价值", "账户", "登录", "注册",
    "下载", "安装", "配置", "设置", "运行", "使用", "操作", "处理",
    "指纹", "身份", "证明", "验证", "授权", "权限", "风险", "问题",
}


def find_best_break_point(text, target_pos, window=5):
    """
    在目标位置附近寻找最佳断点
    优先在停顿词后断开，避免拆分常见词组
    """
    if target_pos >= len(text):
        return len(text)
    
    # 搜索范围：target_pos 前后 window 个字符
    start = max(0, target_pos - window)
    end = min(len(text), target_pos + window)
    
    best_pos = target_pos
    best_score = -100
    
    for pos in range(start, end + 1):
        if pos == 0 or pos >= len(text):
            continue
        
        score = 0
        
        # 检查是否在保护词中间
        for word in PROTECTED_WORDS:
            word_len = len(word)
            for i in range(max(0, pos - word_len + 1), min(pos + 1, len(text) - word_len + 1)):
                if text[i:i + word_len] == word:
                    # 如果断点在这个词中间，扣分
                    if i < pos < i + word_len:
                        score -= 50
                    break
        
        # 检查前面是否是停顿词（在停顿词后断开加分）
        for word in BREAK_AFTER_WORDS:
            word_len = len(word)
            if pos >= word_len and text[pos - word_len:pos] == word:
                score += 20
                break
        
        # 偏好接近目标位置
        distance = abs(pos - target_pos)
        score -= distance * 2
        
        if score > best_score:
            best_score = score
            best_pos = pos
    
    return best_pos


def smart_split_chinese(text, max_len):
    """智能分割中文文本，避免拆分词语"""
    if not text or len(text) <= max_len:
        return [text] if text else []
    
    lines = []
    remaining = text
    
    while len(remaining) > max_len:
        # 寻找最佳断点
        break_pos = find_best_break_point(remaining, max_len)
        
        # 确保至少切出一些内容，避免死循环
        if break_pos <= 0:
            break_pos = max_len
        
        lines.append(remaining[:break_pos])
        remaining = remaining[break_pos:]
    
    if remaining:
        lines.append(remaining)
    
    return lines


def wrap_text_by_punctuation(text, max_len):
    """按标点和长度换行，优先在逗号等处断开"""
    if not text:
        return []
    
    clean = strip_punctuation(text)
    if len(clean) <= max_len:
        return [clean]
    
    # 先按逗号分割
    segments = re.split(r"[，,、]+", text)
    lines = []
    current = ""
    
    for seg in segments:
        seg_clean = strip_punctuation(seg)
        if not seg_clean:
            continue
        
        if not current:
            current = seg_clean
        elif len(strip_punctuation(current)) + len(seg_clean) <= max_len:
            current = current + seg_clean
        else:
            if current:
                lines.append(strip_punctuation(current))
            current = seg_clean
    
    if current:
        lines.append(strip_punctuation(current))
    
    # 检查是否有超长行，如果有则强制截断
    final_lines = []
    for line in lines:
        if len(line) <= max_len:
            final_lines.append(line)
        else:
            # 强制按长度截断（尽量避免）
            if is_chinese_text(line):
                # 中文使用智能断句，避免拆分词语
                final_lines.extend(smart_split_chinese(line, max_len))
            else:
                # 英文按单词截
                words = line.split()
                curr = []
                curr_len = 0
                for w in words:
                    if curr_len + len(w) + (1 if curr else 0) > max_len:
                        if curr:
                            final_lines.append(" ".join(curr))
                        curr = [w]
                        curr_len = len(w)
                    else:
                        curr.append(w)
                        curr_len += len(w) + (1 if len(curr) > 1 else 0)
                if curr:
                    final_lines.append(" ".join(curr))
    
    return final_lines


def split_subtitle_text(text, max_cn=None, max_en=None):
    """分割字幕文本，按标点断句"""
    if max_cn is None:
        max_cn = MAX_CN_CHARS
    if max_en is None:
        max_en = MAX_EN_CHARS
    
    # 按句末标点分割
    sentences = split_by_punctuation(text)
    lines = []
    
    for sentence in sentences:
        clean = strip_punctuation(sentence)
        if not clean:
            continue
        
        max_len = max_cn if is_chinese_text(clean) else max_en
        
        if len(clean) <= max_len:
            lines.append(clean)
        else:
            # 超长句子按逗号等处断开
            lines.extend(wrap_text_by_punctuation(sentence, max_len))
    
    return [line for line in lines if line]


def clamp_duration(start, end, min_s, max_s):
    duration = max(0.0, end - start)
    if duration < min_s:
        end = start + min_s
    elif duration > max_s:
        end = start + max_s
    return start, end


def parse_timecode(tc):
    # Format: HH:MM:SS,mmm
    hms, ms = tc.split(",")
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def format_timecode(seconds):
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def split_times(start, end, count, min_s, max_s):
    if count <= 0:
        return []
    total = max(0.0, end - start)
    min_total = min_s * count
    max_total = max_s * count
    if total < min_total:
        total = min_total
    elif total > max_total:
        total = max_total
    duration = total / count
    duration = max(min_s, min(max_s, duration))

    times = []
    current = start
    for _ in range(count):
        seg_start = current
        seg_end = seg_start + duration
        times.append((seg_start, seg_end))
        current = seg_end
    return times


def postprocess_srt(path, max_cn=None, max_en=None, min_s=None, max_s=None):
    """后处理 SRT 文件：文本分割、时长控制、阅读速度检查、时间轴校验"""
    if max_cn is None:
        max_cn = MAX_CN_CHARS
    if max_en is None:
        max_en = MAX_EN_CHARS
    if min_s is None:
        min_s = MIN_DURATION
    if max_s is None:
        max_s = MAX_DURATION
    
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read().strip()
    if not raw:
        return

    blocks = raw.split("\n\n")
    raw_subtitles = []  # [(start, end, text), ...]
    
    # 第一轮：解析原始字幕
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        time_line = lines[1]
        text = " ".join(lines[2:]).strip()
        
        if " --> " not in time_line:
            continue
        
        start_tc, end_tc = time_line.split(" --> ")
        start = parse_timecode(start_tc)
        end = parse_timecode(end_tc)
        
        # 清理文本（去标点）
        clean_text = strip_punctuation(text)
        if clean_text:
            raw_subtitles.append([start, end, clean_text])
    
    # 第二轮：合并相邻短句（关键步骤！）
    # 如果两条字幕间隔很小（<200ms）且合并后不超过字符限制，就合并它们
    MERGE_GAP_THRESHOLD = 0.2  # 200ms
    merged_subtitles = []
    
    for start, end, text in raw_subtitles:
        if not merged_subtitles:
            merged_subtitles.append([start, end, text])
            continue
        
        prev_start, prev_end, prev_text = merged_subtitles[-1]
        gap = start - prev_end
        combined_text = prev_text + text
        max_chars = get_max_chars(combined_text)
        
        # 合并条件：间隔小、合并后不超限
        if gap < MERGE_GAP_THRESHOLD and len(combined_text) <= max_chars:
            # 合并
            merged_subtitles[-1] = [prev_start, end, combined_text]
        else:
            merged_subtitles.append([start, end, text])
    
    # 第三轮：智能断句（对合并后仍超长的进行分割）
    subtitles = []
    for start, end, text in merged_subtitles:
        max_chars = get_max_chars(text)
        
        if len(text) <= max_chars:
            subtitles.append([start, end, text])
        else:
            # 需要分割
            new_texts = smart_split_chinese(text, max_chars) if is_chinese_text(text) else [text]
            if not new_texts:
                new_texts = [text]
            
            # 分配时间
            for (seg_start, seg_end), seg_text in zip(
                split_times(start, end, len(new_texts), min_s, max_s),
                new_texts,
            ):
                subtitles.append([seg_start, seg_end, seg_text])
    
    # 第二轮：检查阅读速度，必要时延长时间或拆分
    adjusted_subtitles = []
    for i, (start, end, text) in enumerate(subtitles):
        duration = end - start
        max_cps = get_max_cps(text)
        cps = calculate_reading_speed(text, duration)
        
        if cps > max_cps:
            # 阅读速度超限，计算需要的最小时长
            char_count = calculate_char_count(text)
            needed_duration = char_count / max_cps
            
            # 尝试延长 end（检查与下一条字幕的空隙）
            next_start = subtitles[i + 1][0] if i + 1 < len(subtitles) else float('inf')
            available_end = next_start - MIN_GAP
            
            if start + needed_duration <= available_end:
                # 可以延长
                end = start + needed_duration
            elif start + needed_duration <= next_start:
                # 可以延长但会压缩间隙
                end = min(start + needed_duration, next_start - MIN_GAP)
            
            # 如果仍然超限，保持原样（已尽力）
        
        # 应用时长限制
        start, end = clamp_duration(start, end, min_s, max_s)
        adjusted_subtitles.append([start, end, text])
    
    # 第三轮：修复重叠和间隙
    final_subtitles = fix_overlaps_and_gaps(adjusted_subtitles)
    
    # 输出
    out_blocks = []
    for idx, (start, end, text) in enumerate(final_subtitles, 1):
        time_line = f"{format_timecode(start)} --> {format_timecode(end)}"
        out_blocks.append("\n".join([str(idx), time_line, text]))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(out_blocks))


def fix_overlaps_and_gaps(subtitles):
    """修复字幕时间轴的重叠和间隙问题"""
    if not subtitles:
        return subtitles
    
    result = []
    for i, (start, end, text) in enumerate(subtitles):
        if i == 0:
            result.append([start, end, text])
            continue
        
        prev_end = result[-1][1]
        
        # 检查重叠
        if start < prev_end:
            # 有重叠，调整当前字幕的开始时间或前一条的结束时间
            # 策略：缩短前一条的结束时间，确保有最小间隙
            new_prev_end = start - MIN_GAP
            if new_prev_end > result[-1][0] + MIN_DURATION:
                result[-1][1] = new_prev_end
            else:
                # 无法调整前一条，调整当前开始
                start = prev_end + MIN_GAP
        
        # 检查间隙
        gap = start - result[-1][1]
        if gap < MIN_GAP and gap >= 0:
            # 间隙太小，微调
            start = result[-1][1] + MIN_GAP
        elif gap > MAX_GAP:
            # 间隙太大，可以接受（不强制调整）
            pass
        
        result.append([start, end, text])
    
    return result


class SubtitleMakerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("科技脉冲字幕")
        self.geometry("900x700")
        self.minsize(800, 600)
        
        # 设置图标
        try:
            icon_path = os.path.join(APP_DIR, "assets", "icons", "SRT.png")
            if os.path.exists(icon_path):
                icon_img = tk.PhotoImage(file=icon_path)
                self.iconphoto(False, icon_img)
        except Exception:
            pass

        self.cfg = load_config()
        self.log_queue = queue.Queue()
        self.proc = None
        self.stop_flag = threading.Event()

        ensure_dirs()
        self._configure_style()
        self._build_ui()
        self._start_log_pump()

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')  # 使用 clam 主题作为基础，因为它比较平滑
        except:
            pass
        
        # 苹果风配色
        bg_color = "#FFFFFF"         # 纯白背景
        fg_color = "#333333"         # 深灰字体
        accent_color = "#007AFF"     # 苹果蓝
        light_gray = "#F5F5F7"       # 浅灰背景（用于区分区块）
        
        self.configure(bg=bg_color)
        
        # 配置通用 TFrame, TLabel
        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, foreground=fg_color, font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 24, "bold"), foreground="#1D1D1F")
        style.configure("SubHeader.TLabel", font=("Segoe UI", 12), foreground="#86868b")
        style.configure("Link.TLabel", font=("Segoe UI", 9), foreground=accent_color, cursor="hand2")
        
        # 配置按钮 (模拟圆角和扁平化)
        style.configure(
            "TButton",
            font=("Segoe UI", 10),
            padding=(15, 8),
            background=light_gray,
            foreground=fg_color,
            borderwidth=0,
            focuscolor="none"
        )
        style.map(
            "TButton",
            background=[("active", "#E5E5E5"), ("pressed", "#D1D1D6")],
            foreground=[("active", "#000000")]
        )
        
        # 强调按钮
        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 10, "bold"),
            background=accent_color,
            foreground="white",
            padding=(20, 10)
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#0062CC"), ("pressed", "#004999")],
            foreground=[("active", "white")]
        )
        
        # 输入框
        style.configure("TEntry", padding=5, fieldbackground=light_gray, borderwidth=0)


    def _build_ui(self):
        # 变量初始化
        self.input_file = tk.StringVar()
        self.input_dir = tk.StringVar(value=self.cfg.get("default_input_dir", ""))
        self.model_dir = tk.StringVar(value=self.cfg.get("default_model_dir", "./models"))
        self.output_dir = tk.StringVar(value=self.cfg.get("default_output_dir", "./SRT_OUT"))
        
        # 主容器
        main_container = ttk.Frame(self, padding=20)
        main_container.pack(fill="both", expand=True)
        
        # 1. Header
        self.create_header(main_container)
        
        # 2. Main Content
        content = ttk.Frame(main_container, padding=(0, 20))
        content.pack(fill="x")
        
        # 文件选择区
        grid_opts = {"sticky": "w", "pady": 8}
        
        # 单文件
        ttk.Label(content, text="单文件处理").grid(row=0, column=0, **grid_opts)
        entry_file = ttk.Entry(content, textvariable=self.input_file, width=60)
        entry_file.grid(row=0, column=1, sticky="we", padx=(10, 10))
        ttk.Button(content, text="选择文件", command=self.select_file, style="TButton").grid(row=0, column=2)
        
        # 批量文件夹
        ttk.Label(content, text="批量处理目录").grid(row=1, column=0, **grid_opts)
        entry_dir = ttk.Entry(content, textvariable=self.input_dir, width=60)
        entry_dir.grid(row=1, column=1, sticky="we", padx=(10, 10))
        ttk.Button(content, text="选择目录", command=self.select_input_dir, style="TButton").grid(row=1, column=2)
        
        # 模型目录
        ttk.Label(content, text="模型路径").grid(row=2, column=0, **grid_opts)
        entry_model = ttk.Entry(content, textvariable=self.model_dir, width=60)
        entry_model.grid(row=2, column=1, sticky="we", padx=(10, 10))
        ttk.Button(content, text="选择模型", command=self.select_model_dir, style="TButton").grid(row=2, column=2)
        
        content.columnconfigure(1, weight=1)
        
        # 3. Action Buttons
        actions = ttk.Frame(main_container, padding=(0, 10))
        actions.pack(fill="x")
        
        left_btns = ttk.Frame(actions)
        left_btns.pack(side="left")
        
        ttk.Button(left_btns, text="开始生成", command=self.start_run, style="Accent.TButton", cursor="hand2").pack(side="left", padx=(0, 10))
        ttk.Button(left_btns, text="停止", command=self.cancel_run, style="TButton", cursor="hand2").pack(side="left", padx=(0, 10))
        ttk.Button(left_btns, text="环境自检", command=self.run_self_test, style="TButton", cursor="hand2").pack(side="left")
        
        right_btns = ttk.Frame(actions)
        right_btns.pack(side="right")
        
        ttk.Label(right_btns, text="缺失依赖检查：", font=("Segoe UI", 9), foreground="#86868b").pack(side="left", padx=(0, 5))
        link_style = "Link.TLabel"
        gh_dl = ttk.Label(right_btns, text="GitHub下载", style=link_style)
        gh_dl.pack(side="left", padx=5)
        gh_dl.bind("<Button-1>", lambda e: self.download_missing("github"))
        
        hf_dl = ttk.Label(right_btns, text="HF-Mirror下载", style=link_style)
        hf_dl.pack(side="left", padx=5)
        hf_dl.bind("<Button-1>", lambda e: self.download_missing("hf_mirror"))
        
        manual_dl = ttk.Label(right_btns, text="手动导入", style=link_style)
        manual_dl.pack(side="left", padx=5)
        manual_dl.bind("<Button-1>", lambda e: self.open_model_dir())

        # 4. Log Area
        log_frame = ttk.Frame(main_container)
        log_frame.pack(fill="both", expand=True, pady=(10, 20))
        
        ttk.Label(log_frame, text="运行状态", style="SubHeader.TLabel").pack(anchor="w", pady=(0, 5))
        
        self.log_text = tk.Text(
            log_frame, 
            wrap="word", 
            height=12, 
            font=("Consolas", 9),
            bg="#F5F5F7", 
            relief="flat",
            padx=10,
            pady=10
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        
        # 5. Footer
        self.create_footer(main_container)

    def create_header(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 0))
        
        # 标题
        ttk.Label(header, text="科技脉冲字幕", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header, 
            text="专业级本地语音转字幕工具 · 高效准确", 
            style="SubHeader.TLabel"
        ).pack(anchor="w", pady=(5, 0))
        
        # 分割线
        sep = ttk.Frame(parent, height=1, style="TFrame")
        sep.pack(fill="x", pady=(20, 0))
        # 可以用 canvas 画一条细线模拟分割，或者用 Frame 背景色
        canvas = tk.Canvas(parent, height=1, bg="#E5E5E5", highlightthickness=0)
        canvas.pack(fill="x", pady=(20, 0))

    def create_footer(self, parent):
        footer = ttk.Frame(parent, padding=(0, 10))
        footer.pack(fill="x", side="bottom")
        
        # 社交链接
        links = [
            ("科技脉冲 TECH PULSE (YouTube)", "https://www.youtube.com/@kejimaichong"),
            ("B站主页", "https://space.bilibili.com/3690993412999524"),
            ("TG频道", "https://t.me/kejimaichong"),
        ]
        
        # 右侧 QQ 群
        ttk.Label(footer, text="QQ群: 787661896", font=("Segoe UI", 9), foreground="#86868b").pack(side="right")
        
        # 左侧链接
        for text, url in links:
            lbl = ttk.Label(footer, text=text, style="Link.TLabel")
            lbl.pack(side="left", padx=(0, 20))
            lbl.bind("<Button-1>", lambda e, u=url: self.open_url(u))
            
    def open_url(self, url):
        webbrowser.open(url)

    def log(self, msg):
        self.log_queue.put(msg)

    def _start_log_pump(self):
        def pump():
            try:
                while True:
                    line = self.log_queue.get_nowait()
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", line + "\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
            except queue.Empty:
                pass
            self.after(100, pump)

        pump()

    def select_file(self):
        path = filedialog.askopenfilename(
            title="选择媒体文件",
            filetypes=[("Media Files", "*.mp4 *.mov *.m4a *.mp3 *.wav"), ("All Files", "*.*")]
        )
        if path:
            self.input_file.set(path)

    def select_input_dir(self):
        path = filedialog.askdirectory(title="选择输入文件夹")
        if path:
            self.input_dir.set(path)

    def select_model_dir(self):
        path = filedialog.askdirectory(title="选择模型目录")
        if path:
            self.model_dir.set(path)

    def select_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir.set(path)

    def open_output_dir(self):
        path = resolve_path(self.output_dir.get(), self.cfg.get("default_output_dir"))
        if os.path.isdir(path):
            os.startfile(path)
        else:
            messagebox.showwarning("提示", "输出目录不存在。")

    def open_model_dir(self):
        path = resolve_path(self.model_dir.get(), self.cfg.get("default_model_dir"))
        if os.path.isdir(path):
            os.startfile(path)
        else:
            messagebox.showwarning("提示", "模型目录不存在。")

    def _check_requirements(self):
        missing = []

        model_dir = resolve_path(self.model_dir.get(), self.cfg.get("default_model_dir"))
        for name in self.cfg.get("required_model_files", []):
            if not os.path.isfile(os.path.join(model_dir, name)):
                missing.append(os.path.join(model_dir, name))

        ffmpeg_dir = os.path.join(APP_DIR, "tools", "ffmpeg")
        for name in self.cfg.get("required_ffmpeg_files", []):
            if not os.path.isfile(os.path.join(ffmpeg_dir, name)):
                missing.append(os.path.join(ffmpeg_dir, name))

        script_path = os.path.join(APP_DIR, self.cfg.get("script_rel_path", ""))
        if not os.path.isfile(script_path):
            missing.append(script_path)

        return missing

    def _build_command(self, input_media):
        model_dir = resolve_path(self.model_dir.get(), self.cfg.get("default_model_dir"))
        output_dir = resolve_path(self.output_dir.get(), self.cfg.get("default_output_dir"))
        os.makedirs(output_dir, exist_ok=True)
        
        # [修复] 尝试将路径转换为相对路径，以避免 sherpa-onnx 在中文绝对路径下加载失败
        try:
            cwd = os.getcwd()
            model_dir = os.path.relpath(model_dir, cwd)
            # 统一使用正斜杠，避免转义问题
            model_dir = model_dir.replace(os.sep, "/")
        except Exception:
            pass

        base = os.path.splitext(os.path.basename(input_media))[0]
        output_srt = os.path.join(output_dir, base + ".srt")
        source_srt = os.path.splitext(input_media)[0] + ".srt"

        script_path = os.path.join(APP_DIR, self.cfg.get("script_rel_path", ""))
        args = []
        for item in self.cfg.get("script_args_template", []):
            args.append(
                item.format(
                    model_dir=model_dir,
                    output_srt=output_srt,
                    input_media=input_media,
                )
            )

        cmd = [sys.executable, script_path] + args
        return cmd, output_srt, source_srt

    def _run_script_for_file(self, input_media):
        cmd, output_srt, source_srt = self._build_command(input_media)
        self.log(f"[运行] {input_media}")
        self.log(f"[命令] {' '.join(cmd)}")

        env = os.environ.copy()
        ffmpeg_dir = os.path.join(APP_DIR, "tools", "ffmpeg")
        env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
        env.setdefault("PYTHONIOENCODING", "utf-8")

        log_path = os.path.join(LOG_DIR, "run.log")
        with open(log_path, "a", encoding="utf-8") as log_file:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
            )
            for line in self.proc.stdout:
                line = line.rstrip()
                log_file.write(line + "\n")
                self.log(line)
                if self.stop_flag.is_set():
                    self.proc.terminate()
                    break
            self.proc.wait()

        if self.proc.returncode == 0:
            if os.path.isfile(source_srt):
                postprocess_srt(source_srt)  # 使用常量中的默认参数
                self.log(f"[完成] 生成 {source_srt}")
            else:
                self.log("[失败] 未找到生成的 srt 文件，请检查日志。")
        else:
            self.log("[失败] 生成字幕失败，请检查缺失文件或日志。")

    def start_run(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("提示", "正在运行，请先取消或等待完成。")
            return

        missing = self._check_requirements()
        if missing:
            message = "缺少以下文件：\n" + "\n".join(missing)
            messagebox.showwarning("缺少依赖", message)
            self.log(message)
            return

        input_file = self.input_file.get().strip()
        input_dir = self.input_dir.get().strip()
        exts = self.cfg.get("media_extensions", [])

        files = []
        if input_file:
            if os.path.isfile(input_file) and is_media_file(input_file, exts):
                files = [input_file]
            else:
                messagebox.showwarning("提示", "选择的文件不是支持的媒体格式。")
                return
        elif input_dir:
            if os.path.isdir(input_dir):
                files = list_media_files(input_dir, exts)
                if not files:
                    messagebox.showwarning("提示", "文件夹内没有可用媒体文件。")
                    return
            else:
                messagebox.showwarning("提示", "输入文件夹不存在。")
                return
        else:
            messagebox.showwarning("提示", "请先选择文件或输入文件夹。")
            return

        self.stop_flag.clear()
        thread = threading.Thread(target=self._run_batch, args=(files,), daemon=True)
        thread.start()

    def _run_batch(self, files):
        for media in files:
            if self.stop_flag.is_set():
                break
            self._run_script_for_file(media)
        if self.stop_flag.is_set():
            self.log("[取消] 用户取消运行。")
        else:
            self.log("[完成] 全部任务结束。")

    def cancel_run(self):
        if self.proc and self.proc.poll() is None:
            self.stop_flag.set()
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.log("[取消] 正在停止...")
        else:
            self.log("[提示] 当前没有运行任务。")

    def run_self_test(self):
        sample = os.path.join(SAMPLES_DIR, "sample.wav")
        if not os.path.isfile(sample):
            messagebox.showwarning("提示", "缺少 samples/sample.wav，自检无法运行。")
            return

        self.input_file.set(sample)
        self.input_dir.set("")
        self.start_run()

    def download_missing(self, source):
        missing = self._check_requirements()
        if not missing:
            messagebox.showinfo("提示", "未检测到缺失文件。")
            return

        src_cfg = self.cfg.get("download_sources", {}).get(source, {})
        model_dir = resolve_path(self.model_dir.get(), self.cfg.get("default_model_dir"))
        os.makedirs(model_dir, exist_ok=True)

        to_download = {
            "tokens.txt": src_cfg.get("tokens", ""),
            "model.onnx": src_cfg.get("paraformer", ""),
            "silero_vad.onnx": src_cfg.get("silero_vad", ""),
        }

        self.log(f"[下载] 来源: {source}")
        for filename, url in to_download.items():
            dest = os.path.join(model_dir, filename)
            if os.path.isfile(dest):
                continue
            if not url:
                self.log(f"[跳过] {filename} 未配置下载地址。")
                continue
            try:
                self.log(f"[下载] {filename} <- {url}")
                request.urlretrieve(url, dest)
                self.log(f"[完成] {dest}")
            except Exception as exc:
                self.log(f"[失败] {filename} 下载失败: {exc}")

        messagebox.showinfo("提示", "下载流程结束，请检查日志。")


if __name__ == "__main__":
    app = SubtitleMakerApp()
    app.mainloop()
