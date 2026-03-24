# -*- coding: utf-8 -*-
import os
import platform

# 1. 渲染性能补丁（解决 Android 12+ 闪退）
if platform.system() == 'Android' or 'ANDROID_ARGUMENT' in os.environ:
    os.environ['KIVY_GRAPHICS'] = 'gles'
    os.environ['RENDER_THREAD'] = '0'
    os.environ['APP_SHORTCUT_RENDER_THREAD'] = '0'

from kivy.utils import platform as kivy_platform

# 2. 核心补丁：强制调用安卓系统 NotoSansCJK 字体
if kivy_platform == 'android':
    import os
    from kivy.core.text import LabelBase
    from kivy.config import Config

    # 安卓系统典型的中文字体存放路径清单
    cjk_fonts = [
        '/system/fonts/NotoSansCJK-Regular.ttc',    # Android 现代系统
        '/system/fonts/NotoSansSC-Regular.otf',     # 部分国产 OS
        '/system/fonts/DroidSansFallback.ttf',      # 老版本 Android
        '/product/fonts/NotoSansCJK-Regular.ttc',   # 部分 Android 11+ 新路径
        '/system/fonts/SourceHanSansCN-Regular.otf'，
        '/system/fonts/OSans-RC-Regular.ttf'​ # 华为等厂商可能使用的路径
    ]
    
    found_font = None
    for f in cjk_fonts:
        if os.path.exists(f):
            found_font = f
            break
    
    if found_font:
        # 注册这个字体为默认中文字体
        LabelBase.register(name='NotoSettings', fn_regular=found_font)
        # 关键：通过 Config 强制 Kivy 全局使用这个字体，否则所有的 Label 都需要手动设 font_name
        Config.set('kivy', 'default_font', ['NotoSettings', found_font])
        
        # 针对安卓 12+ 解决部分组件依然乱码的小窍门
        os.environ['KIVY_FONT_ALIAS'] = f'{{"DroidSans": "{found_font}"}}'

# --- 接下来再导入 App, Label 等组件 ---
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.graphics import Color, RoundedRectangle
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.metrics import dp, sp
import asyncio
import threading

try:
    from bleak import BleakScanner, BleakClient
except ImportError:
    BleakScanner, BleakClient = None, None

class StyledButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0,0,0,0)
        self.color = (1, 1, 1, 1)
        self.font_size = sp(16)
        self.bold = True
        self.btn_color = get_color_from_hex("#2196F3")
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.btn_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10),])

class DishwasherControlApp(App):
    def build(self):
        self.title = "洗碗机控制中心"
        Window.clearcolor = (1, 1, 1, 1)
        
        # 初始化异步环境
        self.client = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_async_loop, daemon=True)
        self.thread.start()
        
        # 使用 dp/sp 适配布局，解决错位
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(15))
        
        # --- 标题区 ---
        header = Label(
            text="洗碗机控制中心", 
            font_size=sp(24), 
            bold=True, 
            color=get_color_from_hex("#333333"),
            size_hint_y=None,
            height=dp(60)
        )
        root.add_widget(header)

        # --- 数据展示卡片 ---
        data_card = GridLayout(cols=2, spacing=dp(15), size_hint_y=None, height=dp(180))
        
        def create_data_box(title, color="#2196F3"):
            box = BoxLayout(orientation="vertical", spacing=dp(5))
            lbl_title = Label(text=title, color=get_color_from_hex("#666666"), font_size=sp(14))
            lbl_val = Label(text="--", font_size=sp(28), bold=True, color=get_color_from_hex(color))
            box.add_widget(lbl_title)
            box.add_widget(lbl_val)
            return box, lbl_val

        temp_box, self.temp_label = create_data_box("当前温度")
        water_box, self.water_label = create_data_box("当前水位")
        mode_box, self.mode_data_label = create_data_box("实时模式", "#FF9800")
        gear_box, self.gear_data_label = create_data_box("当前档位", "#FF9800")
        
        for b in [temp_box, water_box, mode_box, gear_box]:
            data_card.add_widget(b)
        root.add_widget(data_card)

        # --- 蓝牙连接控制 ---
        conn_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(15))
        self.btn_connect = StyledButton(text="搜索连接")
        self.btn_connect.bind(on_release=self.show_device_list)
        self.btn_disconnect = StyledButton(text="断开")
        self.btn_disconnect.btn_color = get_color_from_hex("#757575")
        self.btn_disconnect.bind(on_release=lambda x: self.start_async(self.disconnect_device()))
        conn_box.add_widget(self.btn_connect)
        conn_box.add_widget(self.btn_disconnect)
        root.add_widget(conn_box)

        self.status_label = Label(text="请选择设备连接", color=get_color_from_hex("#9E9E9E"), size_hint_y=None, height=dp(30), font_size=sp(14))
        root.add_widget(self.status_label)

        # --- 控制集 ---
        root.add_widget(Label(text="核心控制项", size_hint_y=None, height=dp(30), color=get_color_from_hex("#333333"), bold=True, font_size=sp(16)))
        
        op_grid = GridLayout(cols=2, spacing=dp(12), size_hint_y=None, height=dp(120))
        cmds = [("启动洗涤", b"\x01"), ("强制停止", b"\x02"), ("切换模式", b"\x03"), ("调节档位", b"\x04")]
        for name, hex_val in cmds:
            btn = StyledButton(text=name)
            btn.btn_color = get_color_from_hex("#1976D2")
            btn.bind(on_release=lambda x, c=hex_val, n=name: self.start_async(self.send_command(c, n)))
            op_grid.add_widget(btn)
        root.add_widget(op_grid)

        self.log_label = Label(text="就绪", color=get_color_from_hex("#424242"), size_hint_y=None, height=dp(40), font_size=sp(14))
        root.add_widget(self.log_label)

        # 弹性占位
        root.add_widget(BoxLayout()) 
        return root

    def run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_async(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def on_start(self):
        # 针对 Android 12+ 优化权限请求
        if kivy_platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.BLUETOOTH_SCAN, 
                    Permission.BLUETOOTH_CONNECT, 
                    Permission.ACCESS_FINE_LOCATION
                ])
            except Exception as e: print(f"Permission Error: {e}")

    def show_device_list(self, instance):
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        self.device_list_layout = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.device_list_layout.bind(minimum_height=self.device_list_layout.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.device_list_layout)
        content.add_widget(scroll)
        self.scan_popup = Popup(title="附近蓝牙设备", content=content, size_hint=(0.9, 0.8))
        self.scan_popup.open()
        self.start_async(self.scan_devices())

    async def scan_devices(self):
        if not BleakScanner: return
        try:
            devices = await BleakScanner.discover(timeout=4.0)
            def update_list(dt):
                self.device_list_layout.clear_widgets()
                for d in devices:
                    d_name = d.name if d.name else "未知设备"
                    btn = StyledButton(text=f"{d_name}\n[size=12sp]{d.address}[/size]", markup=True)
                    btn.btn_color = get_color_from_hex("#424242")
                    btn.height = dp(60)
                    btn.size_hint_y = None
                    btn.bind(on_release=lambda x, dev=d: self.start_async(self.connect_to_device(dev)))
                    self.device_list_layout.add_widget(btn)
            Clock.schedule_once(update_list)
        except Exception as e: print(f"Scan Error: {e}")

    async def connect_to_device(self, device):
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", "连接中..."))
        try:
            self.client = BleakClient(device.address)
            await self.client.connect()
            Clock.schedule_once(lambda dt: self.on_connected(device))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", f"连接失败: {str(e)}"))

    def on_connected(self, device):
        if hasattr(self, 'scan_popup'): self.scan_popup.dismiss()
        self.status_label.text = f"已连接: {device.name or '设备'}"
        self.status_label.color = get_color_from_hex("#4CAF50")

    async def disconnect_device(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        Clock.schedule_once(self.on_disconnected)

    def on_disconnected(self, dt):
        self.status_label.text = "设备已断开"
        self.status_label.color = get_color_from_hex("#F44336")

    async def send_command(self, cmd_hex, name):
        Clock.schedule_once(lambda dt: setattr(self.log_label, "text", f"发送指令: {name}"))
        if self.client and self.client.is_connected:
            try:
                # await self.client.write_gatt_char("UUID_HERE", cmd_hex)
                pass
            except Exception: pass

if __name__ == "__main__":
    try:
        DishwasherControlApp().run()
    except Exception as e:
        import traceback
        print(traceback.format_exc())

