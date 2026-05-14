import re
import sys
import os
import struct
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)


COLORS = {
    'bg': '#1e1e2e', 'surface': '#282840', 'surface2': '#313150',
    'accent': '#7c3aed', 'accent_hover': '#6d28d9',
    'text': '#e2e2f0', 'text_dim': '#9090b0', 'border': '#3a3a5c',
    'success': '#22c55e', 'warning': '#f59e0b', 'input_bg': '#1a1a2e',
}

_ANSI_RE = re.compile(r'(\x1b\[[^a-zA-Z]*[a-zA-Z]|\[\?[0-9]+[a-zA-Z]|\x08)')


def clean_ansi(text):
    return _ANSI_RE.sub('', text)


_STEP_PATTERNS = [
    re.compile(r'::::::Step\s+([\d.]+):\s*(.+)'),
    re.compile(r'#Proc\s+--\s+Step\s+([\d.]+)\s*:::\s*(.+)'),
    re.compile(r'#Proc\s+--\s+Step\s*:::\s*(.+)'),
]

_PROMPT_RE = re.compile(r'admin@\S+[#$]')


class ScriptParser:

    @staticmethod
    def parse_steps(text):
        lines = text.split('\n')
        steps = []
        cur_name = None
        cur_lines = []
        pre_step_lines = []
        found_first_step = False
        step_counter = 0

        for line in lines:
            cleaned = clean_ansi(line)
            matched = False
            for pat in _STEP_PATTERNS:
                m = pat.search(cleaned)
                if m:
                    matched = True
                    if not found_first_step:
                        found_first_step = True
                        if pre_step_lines:
                            steps.append(('\u521d\u59cb\u5316 (Step \u4e4b\u524d)', pre_step_lines))
                    if cur_name is not None:
                        steps.append((cur_name, cur_lines))
                    groups = m.groups()
                    if len(groups) == 2:
                        cur_name = f"Step {groups[0]}: {groups[1].strip()}"
                    else:
                        step_counter += 1
                        cur_name = f"Step {step_counter}: {groups[0].strip()}"
                    cur_lines = []
                    break
            if not matched:
                if cur_name is not None:
                    cur_lines.append(line)
                else:
                    pre_step_lines.append(line)

        if cur_name is not None:
            steps.append((cur_name, cur_lines))

        if not steps and pre_step_lines:
            steps.append(('\u5168\u90e8\u5185\u5bb9', pre_step_lines))

        return steps

    @staticmethod
    def extract_commands(lines):
        commands = []
        seen = set()
        skip = ['cat ', 'ps ', 'grep ', 'exit']
        var_pat = re.compile(r'\bDut\d+\w*\b', re.IGNORECASE)
        # 预扫描: 建立 pica,N -> 设备名 映射表
        dut_map = {}
        for idx, ln in enumerate(lines):
            cl = clean_ansi(ln).strip()
            md = re.search(r'#Proc\s+--\s+dut_reconnect\s+(\S+)', cl)
            if md and md.group(1) not in dut_map:
                buf = ''
                for kk in range(idx + 1, min(idx + 15, len(lines))):
                    buf += clean_ansi(lines[kk]) + ' '
                mp = re.search(r'admin@([\w._-]+)', buf)
                if mp:
                    dut_map[md.group(1)] = mp.group(1)
        current_dev = None  # 当前设备名
        # 预扫描: 从所有行中找提示符获取初始设备名
        for ln in lines:
            cl = clean_ansi(ln)
            mp = re.search(r'admin@([\w._-]+)', cl)
            if mp:
                current_dev = mp.group(1)
                break
        i = 0
        while i < len(lines):
            line = clean_ansi(lines[i]).strip()
            if not line:
                i += 1
                continue
            # 从提示符行中跟踪当前设备
            mp = re.search(r'admin@([\w._-]+)', line)
            if mp and 'send_expect' not in line and '#Proc' not in line:
                new_dev = mp.group(1)
                if new_dev != current_dev:
                    current_dev = new_dev
            # 识别设备切换: dut_reconnect pica,N
            m_dut = re.search(r'#Proc\s+--\s+dut_reconnect\s+(\S+)', line)
            if m_dut:
                dev_name = m_dut.group(1)
                search_buf = ''
                for k in range(i + 1, min(i + 10, len(lines))):
                    ck = clean_ansi(lines[k])
                    search_buf += ck + ' '
                    if 'send_expect' in ck:
                        break
                m_prompt = re.search(r'admin@([\w._-]+)', search_buf)
                if m_prompt:
                    dev_name = m_prompt.group(1)
                elif dev_name in dut_map:
                    dev_name = dut_map[dev_name]
                current_dev = dev_name
                tag = f'>>> [{dev_name}] <<<'
                if not commands or commands[-1] != tag:
                    commands.append(tag)
                    seen.clear()
                i += 1
                continue
            # 识别 send_expect {cmd} 格式
            m_cmd = re.search(r'send_expect\s*\{(.+?)\}', line)
            if m_cmd:
                # 如果还没有设备标记，从当前设备插入
                if current_dev and (not commands or not commands[-1].startswith('>>>')):
                    # 检查之前是否已有同设备标记
                    need_tag = True
                    for prev in reversed(commands):
                        if prev.startswith('>>>'):
                            if f'[{current_dev}]' in prev:
                                need_tag = False
                            break
                    if need_tag:
                        tag = f'>>> [{current_dev}] <<<'
                        commands.append(tag)
                        seen.clear()
                cmd = m_cmd.group(1).strip()
                if not cmd:
                    m_commit = re.search(r'send_expect\s+(commit)\s*\{', line)
                    if m_commit:
                        commands.append('commit')
                elif not any(cmd.startswith(p) or cmd == p.strip() for p in skip):
                    echo_cmd = ScriptParser._find_echo_command(lines, i)
                    if echo_cmd:
                        cmd = ScriptParser._fix_line_wrap_spaces(cmd, echo_cmd)
                    if cmd and cmd not in seen:
                        commands.append(cmd)
                        seen.add(cmd)
                i += 1
                continue
            # 识别 send_expect commit (无花括号)
            m_bare = re.search(r'#Proc\s+--\s+send_expect\s+(commit)(?:\s|$)', line)
            if m_bare:
                if current_dev and (not commands or not commands[-1].startswith('>>>')):
                    need_tag = True
                    for prev in reversed(commands):
                        if prev.startswith('>>>'):
                            if f'[{current_dev}]' in prev:
                                need_tag = False
                            break
                    if need_tag:
                        tag = f'>>> [{current_dev}] <<<'
                        commands.append(tag)
                        seen.clear()
                commands.append('commit')
                i += 1
                continue
            i += 1
        return commands

    @staticmethod
    def _find_echo_command(lines, start_idx):
        """从 send_expect 后面的回显行中提取实际执行的命令。
        支持多行回显（OVS终端换行会把命令拆成多行）"""
        collecting = False
        collected_parts = []
        for j in range(start_idx + 1, min(start_idx + 20, len(lines))):
            echo = clean_ansi(lines[j]).strip()
            if 'send_expect' in echo:
                break
            if _PROMPT_RE.search(echo):
                cleaned = _PROMPT_RE.sub('', echo).strip()
                if cleaned:
                    if not collecting:
                        collecting = True
                    collected_parts.append(cleaned)
                elif collecting:
                    break
            elif collecting and echo:
                collected_parts.append(echo)
            elif collecting and not echo:
                continue
        if collected_parts:
            return ' '.join(collected_parts)
        return None

    @staticmethod
    def _fix_line_wrap_spaces(original, echoed):
        orig_words = original.split()
        echo_words = echoed.split()
        var_pat = re.compile(r'\bDut\d+\w*\b', re.IGNORECASE)
        if var_pat.search(original):
            if len(echo_words) > len(orig_words):
                return ScriptParser._merge_split_words(echo_words, orig_words)
            return echoed
        if len(echo_words) > len(orig_words):
            return original
        return echoed if echoed else original

    @staticmethod
    def _merge_split_words(echo_words, orig_words):
        result = []
        ei, oi = 0, 0
        while ei < len(echo_words) and oi < len(orig_words):
            if echo_words[ei] == orig_words[oi]:
                result.append(echo_words[ei])
                ei += 1
                oi += 1
            else:
                merged = echo_words[ei]
                ei += 1
                while ei < len(echo_words) and merged != orig_words[oi]:
                    merged += echo_words[ei]
                    ei += 1
                    if len(merged) > len(orig_words[oi]):
                        break
                result.append(merged)
                oi += 1
        while ei < len(echo_words):
            result.append(echo_words[ei])
            ei += 1
        return ' '.join(result)

    @staticmethod
    def extract_packets(lines):
        packets, cur = [], []
        for line in lines:
            stripped = clean_ansi(line).strip()
            if not stripped:
                continue
            m = re.search(r'#Proc\s+--\s+((?:[0-9a-fA-F]{2}\s+)+[0-9a-fA-F]{2})', stripped)
            if m:
                cur.append(m.group(1).strip())
            else:
                if cur:
                    packets.append(bytes.fromhex(''.join(cur).replace(' ', '')))
                    cur = []
        if cur:
            packets.append(bytes.fromhex(''.join(cur).replace(' ', '')))
        return packets

    @staticmethod
    def packets_to_pcap(packets):
        pcap = struct.pack('<IHHiIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
        ts = int(time.time())
        for pkt in packets:
            n = len(pkt)
            pcap += struct.pack('<IIII', ts, 0, n, n) + pkt
        return pcap


class NetworkToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ConfigCleaner v3.1")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.configure(bg=COLORS['bg'])
        try:
            p = resource_path('network.ico')
            self.root.iconbitmap(default=p)
            self.root.iconbitmap(p)
        except Exception:
            pass
        self.steps = []
        self.step_vars = []
        self.file_path = None
        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('.', background=COLORS['bg'], foreground=COLORS['text'])
        s.configure('TFrame', background=COLORS['bg'])
        s.configure('TLabel', background=COLORS['bg'], foreground=COLORS['text'],
                    font=('Microsoft YaHei UI', 10))
        s.configure('Title.TLabel', font=('Microsoft YaHei UI', 13, 'bold'),
                    foreground=COLORS['accent'])
        s.configure('Dim.TLabel', foreground=COLORS['text_dim'],
                    font=('Microsoft YaHei UI', 9))
        s.configure('Accent.TButton', background=COLORS['accent'],
                    foreground='white', font=('Microsoft YaHei UI', 10, 'bold'),
                    padding=(16, 8))
        s.map('Accent.TButton', background=[('active', COLORS['accent_hover'])])
        s.configure('TButton', background=COLORS['surface2'],
                    foreground=COLORS['text'], font=('Microsoft YaHei UI', 9),
                    padding=(12, 6))
        s.map('TButton', background=[('active', COLORS['border'])])
        s.configure('TCheckbutton', background=COLORS['surface'],
                    foreground=COLORS['text'], font=('Microsoft YaHei UI', 9))
        s.map('TCheckbutton', background=[('active', COLORS['surface2'])])
        s.configure('TRadiobutton', background=COLORS['bg'],
                    foreground=COLORS['text'], font=('Microsoft YaHei UI', 9))
        s.map('TRadiobutton', background=[('active', COLORS['surface'])])
        s.configure('TLabelframe', background=COLORS['surface'],
                    foreground=COLORS['text'], borderwidth=1, relief='solid')
        s.configure('TLabelframe.Label', background=COLORS['surface'],
                    foreground=COLORS['accent'], font=('Microsoft YaHei UI', 10, 'bold'))

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main = ttk.Frame(self.root, padding=12)
        main.grid(sticky='nsew')
        main.columnconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        hdr = ttk.Frame(main)
        hdr.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        hdr.columnconfigure(1, weight=1)
        ttk.Label(hdr, text="\u26a1 ConfigCleaner", style='Title.TLabel').grid(
            row=0, column=0, sticky='w')
        ttk.Label(hdr, text="v3.1  \u00b7  \u62d6\u5165\u811a\u672c\u6587\u4ef6\u6216\u70b9\u51fb\u6253\u5f00",
                  style='Dim.TLabel').grid(row=0, column=1, sticky='w', padx=(10, 0))

        self.drop_frame = tk.Frame(main, bg=COLORS['surface'],
            highlightbackground=COLORS['border'], highlightthickness=2,
            height=70, cursor='hand2')
        self.drop_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        self.drop_frame.grid_propagate(False)
        self.drop_frame.columnconfigure(0, weight=1)
        self.drop_frame.rowconfigure(0, weight=1)
        self.drop_label = tk.Label(self.drop_frame,
            text="\U0001f4c2  \u5c06\u811a\u672c\u6587\u4ef6\u62d6\u5230\u6b64\u5904\uff0c\u6216\u70b9\u51fb\u9009\u62e9\u6587\u4ef6",
            bg=COLORS['surface'], fg=COLORS['text_dim'],
            font=('Microsoft YaHei UI', 11), cursor='hand2')
        self.drop_label.grid(row=0, column=0, sticky='nsew')
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<Drop>>', self._on_file_drop)
        self.drop_label.bind('<Button-1>', lambda e: self._open_file())
        self.drop_frame.bind('<Button-1>', lambda e: self._open_file())

        left = ttk.LabelFrame(main, text=" \U0001f4cb \u6b65\u9aa4\u5217\u8868 ", padding=8)
        left.grid(row=2, column=0, sticky='nsew', padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        sf = ttk.Frame(left)
        sf.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        ttk.Button(sf, text="\u5168\u9009", command=self._select_all).pack(side='left', padx=(0, 4))
        ttk.Button(sf, text="\u53d6\u6d88", command=self._deselect_all).pack(side='left')

        cf = ttk.Frame(left)
        cf.grid(row=1, column=0, sticky='nsew')
        cf.columnconfigure(0, weight=1)
        cf.rowconfigure(0, weight=1)
        self.step_canvas = tk.Canvas(cf, bg=COLORS['surface'], highlightthickness=0, width=260)
        sb = ttk.Scrollbar(cf, orient='vertical', command=self.step_canvas.yview)
        self.step_canvas.configure(yscrollcommand=sb.set)
        self.step_canvas.grid(row=0, column=0, sticky='nsew')
        sb.grid(row=0, column=1, sticky='ns')
        self.step_inner = ttk.Frame(self.step_canvas)
        self.step_canvas.create_window((0, 0), window=self.step_inner, anchor='nw')
        self.step_inner.bind('<Configure>',
            lambda e: self.step_canvas.configure(scrollregion=self.step_canvas.bbox('all')))
        self._bind_mousewheel(self.step_canvas)
        self._bind_mousewheel(self.step_inner)
        self.step_ph = tk.Label(self.step_inner,
            text="\u5bfc\u5165\u6587\u4ef6\u540e\n\u6b64\u5904\u663e\u793a\u6b65\u9aa4",
            bg=COLORS['surface'], fg=COLORS['text_dim'], font=('Microsoft YaHei UI', 10))
        self.step_ph.pack(pady=30)

        right = ttk.Frame(main)
        right.grid(row=2, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ab = ttk.Frame(right)
        ab.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        self.mode_var = tk.StringVar(value='commands')
        for txt, val in [("\U0001f4dd \u63d0\u53d6\u547d\u4ee4", 'commands'),
                         ("\U0001f4e6 \u62a5\u6587\u6587\u672c", 'hex'),
                         ("\U0001f988 \u5bfc\u51fa PCAP", 'pcap')]:
            ttk.Radiobutton(ab, text=txt, variable=self.mode_var, value=val).pack(
                side='left', padx=(0, 12))
        ttk.Button(ab, text="\u25b6 \u6267\u884c", style='Accent.TButton',
                   command=self._execute).pack(side='right', padx=(8, 0))
        ttk.Button(ab, text="\U0001f4cb \u590d\u5236", command=self._copy_result).pack(side='right')

        of = ttk.LabelFrame(right, text=" \U0001f4c4 \u8f93\u51fa\u7ed3\u679c ", padding=6)
        of.grid(row=1, column=0, sticky='nsew')
        of.columnconfigure(0, weight=1)
        of.rowconfigure(0, weight=1)
        self.output_text = scrolledtext.ScrolledText(of, wrap=tk.WORD,
            font=('Consolas', 10), bg=COLORS['input_bg'], fg=COLORS['text'],
            insertbackground=COLORS['text'], selectbackground=COLORS['accent'],
            relief='flat', borderwidth=0, padx=8, pady=8)
        self.output_text.grid(row=0, column=0, sticky='nsew')

        self.status_var = tk.StringVar(value="\u5c31\u7eea")
        tk.Label(main, textvariable=self.status_var, bg=COLORS['bg'],
                 fg=COLORS['text_dim'], font=('Microsoft YaHei UI', 9),
                 anchor='w').grid(row=3, column=0, columnspan=2, sticky='ew', pady=(6, 0))

    def _bind_mousewheel(self, widget):
        widget.bind('<MouseWheel>',
            lambda e: self.step_canvas.yview_scroll(-1 * (e.delta // 120), 'units'))

    def _open_file(self):
        p = filedialog.askopenfilename(title="\u9009\u62e9\u811a\u672c\u6587\u4ef6",
            filetypes=[("\u6587\u672c\u6587\u4ef6", "*.txt"), ("\u6240\u6709\u6587\u4ef6", "*.*")])
        if p:
            self._load_file(p)

    def _on_file_drop(self, event):
        p = event.data.strip('{}')
        if os.path.isfile(p):
            self._load_file(p)

    def _load_file(self, path):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("\u9519\u8bef", f"\u8bfb\u53d6\u6587\u4ef6\u5931\u8d25: {e}")
            return
        self.file_path = path
        fn = os.path.basename(path)
        self.drop_label.config(text=f"\u2705  {fn}", fg=COLORS['success'])
        self.drop_frame.config(highlightbackground=COLORS['success'])
        self.steps = ScriptParser.parse_steps(content)
        self._populate_steps()
        self.status_var.set(f"\u5df2\u52a0\u8f7d: {fn}  \u00b7  \u5171 {len(self.steps)} \u4e2a\u6b65\u9aa4")

    def _populate_steps(self):
        for w in self.step_inner.winfo_children():
            w.destroy()
        self.step_vars = []
        if not self.steps:
            tk.Label(self.step_inner, text="\u672a\u627e\u5230 Step \u6b65\u9aa4",
                bg=COLORS['surface'], fg=COLORS['warning'],
                font=('Microsoft YaHei UI', 10)).pack(pady=30)
            return
        for name, _ in self.steps:
            v = tk.BooleanVar(value=True)
            self.step_vars.append(v)
            cb = tk.Checkbutton(self.step_inner, text=name, variable=v,
                bg=COLORS['surface'], fg=COLORS['text'],
                selectcolor=COLORS['surface2'],
                activebackground=COLORS['surface2'],
                activeforeground=COLORS['text'],
                font=('Microsoft YaHei UI', 9),
                anchor='w', padx=4, pady=2)
            cb.pack(fill='x', padx=2, pady=1)
            self._bind_mousewheel(cb)

    def _select_all(self):
        for v in self.step_vars:
            v.set(True)

    def _deselect_all(self):
        for v in self.step_vars:
            v.set(False)

    def _get_selected_lines(self):
        r = []
        for i, v in enumerate(self.step_vars):
            if v.get():
                r.extend(self.steps[i][1])
        return r

    def _execute(self):
        if not self.steps:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u5148\u5bfc\u5165\u811a\u672c\u6587\u4ef6")
            return
        lines = self._get_selected_lines()
        if not lines:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u6b65\u9aa4")
            return
        mode = self.mode_var.get()
        if mode == 'commands':
            parts = []
            total = 0
            for i, var in enumerate(self.step_vars):
                if var.get():
                    name, step_lines = self.steps[i]
                    cmds = ScriptParser.extract_commands(step_lines)
                    total += len(cmds)
                    sep1 = chr(9552) * 50
                    sep2 = chr(9472) * 50
                    if cmds:
                        parts.append(f"{sep1}\n{name}\n{sep2}\n" + '\n'.join(cmds))
                    else:
                        parts.append(f"{sep1}\n{name}\n{sep2}\n\u65e0")
            result = '\n\n'.join(parts) if parts else "\u6240\u9009\u6b65\u9aa4\u4e2d\u672a\u627e\u5230\u914d\u7f6e\u547d\u4ee4"
            self.status_var.set(f"\u63d0\u53d6\u5230 {total} \u6761\u914d\u7f6e\u547d\u4ee4")
            self.output_text.delete('1.0', tk.END)
            self.output_text.insert(tk.END, result)

        elif mode == 'hex':
            pkts = ScriptParser.extract_packets(lines)
            if pkts:
                parts = []
                for idx, pkt in enumerate(pkts):
                    h = pkt.hex().upper()
                    fmt = '\n'.join(h[j:j+32] for j in range(0, len(h), 32))
                    parts.append(f"\u2500\u2500 \u62a5\u6587 {idx+1} ({len(pkt)} bytes) \u2500\u2500\n{fmt}")
                result = '\n\n'.join(parts)
                self.status_var.set(f"\u63d0\u53d6\u5230 {len(pkts)} \u4e2a\u62a5\u6587")
            else:
                result = "\u6240\u9009\u6b65\u9aa4\u4e2d\u672a\u627e\u5230\u62a5\u6587\u6570\u636e"
                self.status_var.set("\u672a\u627e\u5230\u62a5\u6587")
            self.output_text.delete('1.0', tk.END)
            self.output_text.insert(tk.END, result)

        elif mode == 'pcap':
            pkts = ScriptParser.extract_packets(lines)
            if not pkts:
                messagebox.showwarning("\u63d0\u793a", "\u6240\u9009\u6b65\u9aa4\u4e2d\u672a\u627e\u5230\u62a5\u6587\u6570\u636e")
                return
            sp = filedialog.asksaveasfilename(title="\u4fdd\u5b58 PCAP \u6587\u4ef6",
                defaultextension=".pcap",
                filetypes=[("PCAP \u6587\u4ef6", "*.pcap")],
                initialfile=os.path.splitext(os.path.basename(self.file_path or 'output'))[0] + '.pcap')
            if sp:
                with open(sp, 'wb') as f:
                    f.write(ScriptParser.packets_to_pcap(pkts))
                self.status_var.set(f"\u5df2\u5bfc\u51fa {len(pkts)} \u4e2a\u62a5\u6587\u5230 {os.path.basename(sp)}")
                self.output_text.delete('1.0', tk.END)
                self.output_text.insert(tk.END,
                    f"\u2705 PCAP \u6587\u4ef6\u5df2\u4fdd\u5b58\n\u8def\u5f84: {sp}\n\u62a5\u6587\u6570: {len(pkts)}")

    def _copy_result(self):
        r = self.output_text.get('1.0', tk.END).strip()
        if r:
            self.root.clipboard_clear()
            self.root.clipboard_append(r)
            self.root.update()
            self.status_var.set("\u5df2\u590d\u5236\u5230\u526a\u8d34\u677f")
        else:
            self.status_var.set("\u8f93\u51fa\u4e3a\u7a7a\uff0c\u65e0\u6cd5\u590d\u5236")


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = NetworkToolApp(root)
    root.mainloop()
