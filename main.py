import re
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

class NetworkToolApp:
    def __init__(self, root):
        self.root = root
        self.root.title("网络工具集 v3.0")
        self.root.geometry("1000x800")
        self.root.minsize(800, 600)
        
        # 主窗口布局
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # 主容器
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.grid(column=0, row=0, sticky="nsew")
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)  # 输入区
        self.main_frame.rowconfigure(3, weight=1)  # 输出区
        
        # 输入区
        self.input_label = ttk.Label(self.main_frame, text="输入内容（支持交换机配置/抓包数据）：")
        self.input_label.grid(column=0, row=0, sticky="nw", padx=5, pady=2)
        
        self.input_text = scrolledtext.ScrolledText(
            self.main_frame, wrap=tk.WORD, font=('Consolas', 10), undo=True
        )
        self.input_text.grid(column=0, row=1, sticky="nsew", padx=5, pady=(0,5))
        
        # 操作按钮
        self.btn_frame = ttk.Frame(self.main_frame)
        self.btn_frame.grid(column=0, row=2, sticky="ew", pady=10)
        
        self.process_btn = ttk.Button(
            self.btn_frame, text="执行处理", command=self.process_input
        )
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.copy_btn = ttk.Button(
            self.btn_frame, text="复制结果", command=self.copy_result
        )
        self.copy_btn.pack(side=tk.LEFT, padx=5)
        
        # 输出区
        self.output_label = ttk.Label(self.main_frame, text="处理结果：")
        self.output_label.grid(column=0, row=3, sticky="nw", padx=5, pady=2)
        
        self.output_text = scrolledtext.ScrolledText(
            self.main_frame, wrap=tk.WORD, font=('Consolas', 10)
        )
        self.output_text.grid(column=0, row=4, sticky="nsew", padx=5, pady=(0,5))
    
    def process_input(self):
        """主处理逻辑"""
        input_data = self.input_text.get("1.0", tk.END)
        lines = input_data.split('\n')

        # 自动识别输入类型：优先检测配置命令（send_expect日志或admin@PICOS#命令）
        has_config = any(
            'admin@PICOS#' in line or 'send_expect' in line
            for line in lines
        )
        # 抓包数据：-- 后面跟的全是十六进制字节（支持偏移量格式和日志格式）
        has_hex = any(
            re.search(r'--\s+([0-9a-fA-F]{2}\s+)+', line)
            for line in lines
        ) and not has_config

        if has_config:
            result = self._process_config_commands(input_data)
        elif has_hex:
            result = self._process_hex_data(input_data)
        else:
            messagebox.showerror("错误", "无法识别的输入格式！")
            return

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, result)

    
    def _process_config_commands(self, config_text):
        """处理交换机配置命令 - 支持send_expect日志和纯命令行两种格式"""
        commands = []
        seen = set()
        lines = config_text.split('\n')
        
        # 变量名模式：Dut1P2, Dut2P1 等脚本变量
        var_pattern = re.compile(r'\bDut\d+\w*\b', re.IGNORECASE)
        
        # 第一遍：收集send_expect命令和对应的回显命令
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            m = re.search(r'send_expect\s*\{(.+?)\}', line)
            if m:
                cmd_from_log = m.group(1).strip()
                
                # 如果send_expect里有变量名，从后续回显行取实际命令
                if var_pattern.search(cmd_from_log):
                    # 向后找回显行（admin@PICOS# 后跟实际命令）
                    for j in range(i + 1, min(i + 5, len(lines))):
                        echo_line = lines[j].strip()
                        if 'send_expect' in echo_line:
                            break
                        if 'admin@PICOS#' in echo_line:
                            cleaned = re.sub(r'(admin@PICOS#\s*)+', '', echo_line)
                            cleaned = re.sub(r'[\x08]', '', cleaned).strip()
                            if cleaned and not var_pattern.search(cleaned):
                                cmd_from_log = cleaned
                                break
                
                if cmd_from_log and cmd_from_log not in seen:
                    commands.append(cmd_from_log)
                    seen.add(cmd_from_log)
                i += 1
                continue
            
            # 没有send_expect的纯命令行
            if 'admin@PICOS#' in line and 'send_expect' not in config_text:
                cleaned = re.sub(r'(admin@PICOS#\s*)+', '', line)
                cleaned = re.sub(r'[\x08]', '', cleaned).strip()
                if cleaned and cleaned not in seen:
                    commands.append(cleaned)
                    seen.add(cleaned)
            
            i += 1
        
        if not commands:
            return "未找到有效配置命令"
        
        return '\n'.join(commands)
    
    def _process_hex_data(self, input_data):
        """处理抓包十六进制数据"""
        hex_str = ''.join(
            line.split('-- ')[1].replace(' ', '')
            for line in input_data.strip().split('\n')
            if '-- ' in line
        )
        # 格式化输出：每行16字节
        formatted = '\n'.join(
            hex_str[i:i+32] for i in range(0, len(hex_str), 32)
        )
        return formatted.upper()
    
    def copy_result(self):
        """复制结果到剪贴板"""
        result = self.output_text.get("1.0", tk.END).strip()
        if result:
            self.root.clipboard_clear()
            self.root.clipboard_append(result)
            self.root.update()
            messagebox.showinfo("成功", "结果已复制！")
        else:
            messagebox.showwarning("警告", "输出内容为空")

if __name__ == "__main__":
    root = tk.Tk()
    app = NetworkToolApp(root)
    root.mainloop()