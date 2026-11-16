"""Summary dialog. All network and COM work runs outside Tk's event thread."""
import io
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from .summary import SummaryConfig, SummaryWorker, PROVIDERS, XINGTU_IMAGE_MODELS, model_id


class SummaryPanel:
    def __init__(self, app, worker=None):
        self.app = app
        self.worker = worker or SummaryWorker()
        self.closed = False
        self.settings_path = app.project_dir / "ai_settings.json"
        self.window = tk.Toplevel(app.root)
        self.window.title("当前页 · AI 演示助手")
        height = min(840, max(650, app.root.winfo_screenheight() - 120))
        self.window.geometry(f"760x{height}+30+30")
        self.window.minsize(710, 650)
        self.window.configure(bg="#19212c")
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        config = SummaryConfig()
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            loaded = SummaryConfig(data["provider"], data["model"], data.get("base_url", ""))
            loaded.validate()
            config = loaded
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.provider = tk.StringVar(value=config.provider)
        self.model = tk.StringVar(value=config.model)
        self.base_url = tk.StringVar(value=config.base_url if config.provider == "自定义兼容服务"
                                     else PROVIDERS[config.provider][0].removesuffix("/chat/completions"))
        self.key = tk.StringVar(value=app.ai_keys.get(config.provider, os.getenv("AIRPRESENT_LLM_API_KEY", "")))
        self.previous_provider = config.provider
        body = tk.Frame(self.window, bg="#19212c", padx=18, pady=14)
        body.pack(fill="both", expand=True)
        def label(text):
            tk.Label(body, text=text, bg="#19212c", fg="#edf4fc", anchor="w",
                     font=("Microsoft YaHei UI", 10)).pack(fill="x", pady=(4, 4))
        label("当前页摘要 · 手势控制已暂停")
        label("服务 / Model ID（需支持图片，星图请从模型广场复制 ID）")
        row = tk.Frame(body, bg="#19212c")
        row.pack(fill="x", pady=5)
        choice = ttk.Combobox(row, textvariable=self.provider, values=list(PROVIDERS), state="readonly", width=19)
        choice.pack(side="left", padx=(0, 10))
        choice.bind("<<ComboboxSelected>>", self.change_provider)
        self.model_choice = ttk.Combobox(row, textvariable=self.model, font=("Microsoft YaHei UI", 11),
                                         values=XINGTU_IMAGE_MODELS if config.provider.startswith("星图") else ())
        self.model_choice.pack(side="left", fill="x", expand=True)
        label("Base URL（自定义服务可编辑）")
        self.url_entry = tk.Entry(body, textvariable=self.base_url, font=("Microsoft YaHei UI", 10),
                                  state="normal" if config.provider == "自定义兼容服务" else "readonly")
        self.url_entry.pack(fill="x", pady=(0, 4))
        self.billing = tk.Label(body, text="", bg="#19212c", fg="#f3c47b", anchor="w",
                                font=("Microsoft YaHei UI", 9))
        self.billing.pack(fill="x")
        self.update_billing()
        label("API Key（仅本次运行保留）")
        self.key_entry = tk.Entry(body, textvariable=self.key, show="•", font=("Microsoft YaHei UI", 11))
        self.key_entry.pack(fill="x", pady=(0, 6))
        label("点击生成会将当前页图片发送给所选服务，按其账号规则计费。")
        label("仅导出本页静态内容；动画最终状态可能可见，视频不转写。")
        actions = tk.Frame(body, bg="#19212c")
        actions.pack(fill="x", pady=8)
        self.preview_button = app._button(actions, "预览本页（不联网）", lambda: self.start(True))
        self.preview_button.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.generate_button = app._button(actions, "生成 AI 摘要", self.start, primary=True)
        self.generate_button.pack(side="left", fill="x", expand=True)
        self.status = tk.Label(body, text="先预览页面，或填写密钥后生成摘要。", bg="#19212c", fg="#64e4b8",
                               anchor="w", wraplength=650, justify="left", font=("Microsoft YaHei UI", 10))
        self.status.pack(fill="x", pady=5)
        self.image_label = tk.Label(body, text="当前页预览", bg="#111a24", fg="#92a3b9", height=8)
        self.image_label.pack(fill="x", pady=5)
        self.image_label.bind("<Configure>", self.resize_preview)
        area = tk.Frame(body)
        area.pack(fill="both", expand=True, pady=6)
        scroll = ttk.Scrollbar(area)
        scroll.pack(side="right", fill="y")
        self.text = tk.Text(area, wrap="word", bg="#111a24", fg="#edf4fc", relief="flat", padx=12, pady=10,
                            font=("Microsoft YaHei UI", 11), height=7, yscrollcommand=scroll.set)
        self.text.pack(fill="both", expand=True)
        scroll.config(command=self.text.yview)
        self.text.config(state="disabled")
        bottom = tk.Frame(body, bg="#19212c")
        bottom.pack(fill="x", pady=(8, 0))
        self.copy_button = app._button(bottom, "复制摘要", self.copy, state="disabled")
        self.copy_button.pack(side="left")
        app._button(bottom, "关闭", self.close).pack(side="right")
        self.resume_button = app._button(bottom, "继续演示", lambda: self.close(True), primary=True)
        self.resume_button.pack(side="right", padx=8)
        # Reserve controls first, then give the remaining space to the text area.
        bottom.pack_forget()
        area.pack_forget()
        bottom.pack(side="bottom", fill="x", pady=(8, 0))
        area.pack(fill="both", expand=True, pady=6)
        self.poll_id = self.window.after(40, self.poll)

    def change_provider(self, event=None):
        self.app.ai_keys[self.previous_provider] = self.key.get()
        self.previous_provider = self.provider.get()
        self.model.set(PROVIDERS[self.provider.get()][1])
        self.model_choice.config(values=XINGTU_IMAGE_MODELS if self.provider.get().startswith("星图") else ())
        self.base_url.set(PROVIDERS[self.provider.get()][0].removesuffix("/chat/completions"))
        self.url_entry.config(state="normal" if self.provider.get() == "自定义兼容服务" else "readonly")
        self.update_billing()
        self.key.set(self.app.ai_keys.get(self.provider.get(), ""))

    def update_billing(self):
        text = {"星图 Token Plan": "Token Plan：消耗套餐 Credits，请使用套餐支持的图片模型。",
                "星图 按量付费": "按量入口：从账户余额扣费，不消耗套餐额度。"}
        self.billing.config(text=text.get(self.provider.get(), "密钥必须与所选服务对应。"))

    def start(self, preview=False):
        if self.worker.busy:
            return
        if self.app.page_output.busy:
            self.status.config(text="请等待当前翻页完成后再试。")
            return
        target = self.app.presentation.target
        if target is None:
            self.status.config(text="请先关闭弹窗，连接正在放映的 PPT。")
            return
        canonical_model = model_id(self.provider.get(), self.model.get())
        self.model.set(canonical_model)
        config = SummaryConfig(self.provider.get(), canonical_model,
                               self.base_url.get() if self.provider.get() == "自定义兼容服务" else "")
        try:
            config.validate()
            if not preview and not self.key.get().strip():
                raise ValueError("请先填写所选服务的 API Key。")
            self.settings_path.write_text(json.dumps({"provider": config.provider, "model": config.model,
                                                      "base_url": config.base_url},
                                                     ensure_ascii=False, indent=2), encoding="utf-8")
            self.app.ai_keys[config.provider] = self.key.get()
            self.worker.submit(target, config, self.key.get(), preview)
        except (ValueError, OSError) as exc:
            self.status.config(text=str(exc))
            return
        self.preview_button.config(state="disabled")
        self.generate_button.config(state="disabled")
        self.copy_button.config(state="disabled")
        self.resume_button.config(state="disabled")
        self.status.config(text="正在读取已连接 PPT 的当前页…")
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        self.app._refresh_floating()

    def poll(self):
        if self.closed:
            return
        while (item := self.worker.poll()) is not None:
            kind, value = item
            if kind == "preview":
                metadata, png = value
                self.preview_image = Image.open(io.BytesIO(png)).copy()
                self.resize_preview()
                self.source = f'{metadata["presentation"]} · 第 {metadata["slide"]} 页'
                self.status.config(text=self.source + " · 页面已读取，正在处理…")
            elif kind == "done":
                metadata, text, elapsed, cached = value
                self.text.config(state="normal")
                self.text.delete("1.0", "end")
                self.text.insert("1.0", text)
                self.text.config(state="disabled")
                self.copy_button.config(state="normal" if elapsed else "disabled")
                self.status.config(text=self.source + (" · 仅本地预览" if not elapsed else
                                       f" · {'本次运行缓存' if cached else '生成完成'} · {elapsed:.1f} 秒"))
            elif kind == "error":
                self.status.config(text=value.split("\n", 1)[0])
                self.text.config(state="normal")
                self.text.delete("1.0", "end")
                self.text.insert("1.0", value)
                self.text.config(state="disabled")
            elif kind == "idle":
                for button in (self.preview_button, self.generate_button, self.resume_button):
                    button.config(state="normal")
                self.app._refresh_floating()
        self.poll_id = self.window.after(40, self.poll)

    def resize_preview(self, event=None):
        if hasattr(self, "preview_image"):
            image = self.preview_image.copy()
            image.thumbnail((max(100, self.window.winfo_width() - 40),
                             min(200, max(90, self.window.winfo_height() - 610))))
            self.photo = ImageTk.PhotoImage(image)
            self.image_label.config(image=self.photo, text="", height=0)

    def copy(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(self.source + "\n\n" + self.text.get("1.0", "end-1c"))

    def close(self, resume=False):
        self.closed = True
        self.window.after_cancel(self.poll_id)
        self.worker.cancel()
        self.app.ai_keys[self.provider.get()] = self.key.get()
        self.key.set("")
        self.window.destroy()
        self.app.summary_panel = None
        self.app._refresh_floating()
        if resume and not self.app.closing:
            self.app.toggle_control()
