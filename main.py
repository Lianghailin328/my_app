# -*- coding: utf-8 -*-
import os
import platform

# 关键修复：解决 SDL/Android 互斥锁崩溃问题
if platform.system() == 'Android' or 'ANDROID_ARGUMENT' in os.environ:
    os.environ['KIVY_GRAPHICS'] = 'gles' # 强制使用 GLES
    os.environ['RENDER_THREAD'] = '0'     # 禁用渲染线程，防止 pthread 冲突
    # 下面这行特别针对你看到的 hwuiTask1 崩溃
    os.environ['APP_SHORTCUT_RENDER_THREAD'] = '0'

from kivy.utils import platform

# 1. 窗口设置 (只有在桌面端才设置固定分辨率，安卓端跳过避免初始化报错)
if platform not in ('android', 'ios'):
    from kivy.config import Config
    Config.set("graphics", "width", "360")
    Config.set("graphics", "height", "640")
    Config.set("graphics", "resizable", "0")

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
from kivy.core.text import LabelBase
import asyncio
import threading
# 注意：bleak 在 Android 上可能不兼容，如果依然闪退，请尝试注释掉下一行
try:
    from bleak import BleakScanner, BleakClient
except ImportError:
    BleakScanner, BleakClient = None, None


def register_fonts():
    """不再主动注册自定义字体，直接利用系统默认环境"""
    return True

class StyledButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0,0,0,0)
        self.color = (1, 1, 1, 1)
        self.font_size = "16sp"
        self.bold = True
        self.btn_color = get_color_from_hex("#2196F3")
        # 移除 font_name 显式指定
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.btn_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[15,])

class DishwasherControlApp(App):
    def build(self):
        self.title = "洗碗机控制客户端"
        Window.clearcolor = (1, 1, 1, 1)  # 将背景颜色设置为白色 (R, G, B, A)
        
        # 1. 初始化异步环境
        try:
            self.client = None
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(target=self.run_async_loop, daemon=True)
            self.thread.start()
        except Exception as e:
            print(f"Async Init Error: {e}")
        
        # 2. 构建 UI (增加 try 指导定位)
        try:
            root = BoxLayout(orientation="vertical", padding=[20, 10, 20, 10], spacing=10)
            
            # --- 2. 标题区 ---
            self.header_area = BoxLayout(size_hint_y=None, height=60) 
            header = Label(text="洗碗机控制客户端", font_size="22sp", bold=True, color=get_color_from_hex("#333333"))
            self.header_area.add_widget(header)
            root.add_widget(self.header_area)

            # --- 3. 数据展示区 ---
            self.data_area = GridLayout(cols=2, spacing=10, size_hint_y=None, height=140)
            
            # 温度
            temp_box = BoxLayout(orientation="vertical")
            temp_box.add_widget(Label(text="当前温度", color=get_color_from_hex("#666666"), font_size="13sp"))
            self.temp_label = Label(text="-- \u00b0C", font_size="26sp", bold=True, color=get_color_from_hex("#2196F3"))
            temp_box.add_widget(self.temp_label)
            
            # 水位
            water_box = BoxLayout(orientation="vertical")
            water_box.add_widget(Label(text="当前水位", color=get_color_from_hex("#666666"), font_size="13sp"))
            self.water_label = Label(text="-- %", font_size="26sp", bold=True, color=get_color_from_hex("#2196F3"))
            water_box.add_widget(self.water_label)

            # 模式
            mode_data_box = BoxLayout(orientation="vertical")
            mode_data_box.add_widget(Label(text="实时模式", color=get_color_from_hex("#666666"), font_size="13sp"))
            self.mode_data_label = Label(text="--", font_size="26sp", bold=True, color=get_color_from_hex("#FF9800"))
            mode_data_box.add_widget(self.mode_data_label)

            # 档位
            gear_data_box = BoxLayout(orientation="vertical")
            gear_data_box.add_widget(Label(text="当前档位", color=get_color_from_hex("#666666"), font_size="13sp"))
            self.gear_data_label = Label(text="--", font_size="26sp", bold=True, color=get_color_from_hex("#FF9800"))
            gear_data_box.add_widget(self.gear_data_label)
            
            self.data_area.add_widget(temp_box)
            self.data_area.add_widget(water_box)
            self.data_area.add_widget(mode_data_box)
            self.data_area.add_widget(gear_data_box)
            root.add_widget(self.data_area)

            # --- 4. 蓝牙连接区 ---
            self.conn_area = BoxLayout(size_hint_y=None, height=45, spacing=15)
            self.btn_connect = StyledButton(text="搜索蓝牙")
            self.btn_connect.bind(on_release=self.show_device_list)
            self.btn_disconnect = StyledButton(text="断开连接")
            self.btn_disconnect.btn_color = get_color_from_hex("#757575")
            self.btn_disconnect.bind(on_release=lambda x: self.start_async(self.disconnect_device()))
            self.conn_area.add_widget(self.btn_connect)
            self.conn_area.add_widget(self.btn_disconnect)
            root.add_widget(self.conn_area)

            self.status_label = Label(text="Ready to connect", color=get_color_from_hex("#9E9E9E"), size_hint_y=None, height=20, font_size="12sp")
            root.add_widget(self.status_label)

            # --- 5. 指令控制区 ---
            self.op_area = BoxLayout(orientation="vertical", spacing=8, size_hint_y=None, height=160)
            op_title = Label(text="控制器操作集", size_hint_y=None, height=25, color=get_color_from_hex("#333333"), bold=True)
            self.op_area.add_widget(op_title)
            
            op_grid = GridLayout(cols=2, spacing=10)
            cmds = [("开启洗碗", b"\x01"), ("关闭洗碗", b"\x02"), ("切换模式", b"\x03"), ("切换档位", b"\x04")]
            for name, hex_val in cmds:
                btn = StyledButton(text=name)
                btn.btn_color = get_color_from_hex("#1976D2")
                btn.bind(on_release=lambda x, c=hex_val, n=name: self.start_async(self.send_command(c, n)))
                op_grid.add_widget(btn)
            
            self.op_area.add_widget(op_grid)
            root.add_widget(self.op_area)

            self.log_label = Label(text="已就绪", color=get_color_from_hex("#424242"), size_hint_y=None, height=35)
            root.add_widget(self.log_label)

            root.add_widget(BoxLayout()) 
            return root
        except Exception as e:
            print(f"UI Build Error: {e}")
            return Label(text=f"Startup Error: {e}")

    def run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_async(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def show_device_list(self, instance):
        content = BoxLayout(orientation="vertical", padding=10, spacing=10)
        self.device_list_layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.device_list_layout.bind(minimum_height=self.device_list_layout.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.device_list_layout)
        content.add_widget(scroll)
        self.scan_popup = Popup(title="选择蓝牙设备", content=content, size_hint=(0.9, 0.8))
        self.scan_popup.open()
        self.start_async(self.scan_devices())

    def on_start(self):
        """在程序启动后请求权限，避免在 build 阶段阻塞或报错"""
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                def permission_callback(permissions, results):
                    print(f"Permissions results: {results}")

                request_permissions([
                    Permission.BLUETOOTH_SCAN, 
                    Permission.BLUETOOTH_CONNECT, 
                    Permission.ACCESS_FINE_LOCATION,
                    Permission.ACCESS_COARSE_LOCATION,
                    Permission.INTERNET
                ], permission_callback)
            except Exception as e:
                print(f"Android Permission Error: {e}")

    async def scan_devices(self):
        if not BleakScanner:
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", "错误: 蓝牙库(bleak)未安装或不支持此系统"))
            return
        try:
            devices = await BleakScanner.discover(timeout=5.0)
            def update_list(dt):
                self.device_list_layout.clear_widgets()
                for d in devices:
                    d_name = d.name if d.name else "Unknown"
                    btn = StyledButton(text=f"{d_name} ({d.address})")
                    btn.btn_color = get_color_from_hex("#424242")
                    btn.height = 50
                    btn.size_hint_y = None
                    btn.bind(on_release=lambda x, dev=d: self.start_async(self.connect_to_device(dev)))
                    self.device_list_layout.add_widget(btn)
            Clock.schedule_once(update_list)
        except Exception as e: print(f"Scan Error: {e}")

    async def connect_to_device(self, device):
        d_name = device.name if device.name else "Unknown"
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", f"正在连接: {d_name}..."))
        try:
            self.client = BleakClient(device.address)
            await self.client.connect()
            Clock.schedule_once(lambda dt: self.on_connected(device))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", f"连接失败: {str(e)}"))

    def on_connected(self, device):
        self.scan_popup.dismiss()
        name = device.name if device.name else "Device"
        self.status_label.text = f"已连接: {name}"
        self.status_label.color = get_color_from_hex("#4CAF50")

    async def disconnect_device(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        Clock.schedule_once(self.on_disconnected)

    def on_disconnected(self, dt):
        self.status_label.text = "Ready to connect"
        self.status_label.color = get_color_from_hex("#757575")
        self.temp_label.text = "-- \u00b0C"
        self.water_label.text = "-- %"
        self.mode_data_label.text = "--"
        self.gear_data_label.text = "--"

    async def send_command(self, cmd_hex, name):
        Clock.schedule_once(lambda dt: setattr(self.log_label, "text", f"执行: {name}"))
        if self.client and self.client.is_connected:
            try:
                # await self.client.write_gatt_char("UUID_HERE", cmd_hex)
                print(f"Bluetooth Send: {cmd_hex.hex()}")
            except Exception as e: print(f"Error: {e}")
        else:
            print(f"Simulate Send: {name} -> {cmd_hex.hex()}")

    def update_ui_data(self, data_str):
        try:
            raw = data_str.strip().replace("\t", "").replace("\n", "")
            temp, water, mode, gear = raw.split(",")
            self.temp_label.text = f"{float(temp):.1f} \u00b0C"
            self.water_label.text = f"{float(water):.0f} %"
            self.mode_data_label.text = str(int(mode))
            self.gear_data_label.text = str(int(gear))
        except: pass

if __name__ == "__main__":
    import asyncio
    import traceback
    
    # 强制开启控制台日志
    import os
    os.environ['KIVY_LOG_MODE'] = 'PYTHON'

    app = DishwasherControlApp()
    
    async def main_loop():
        try:
            # 使用 async_run 让 Kivy 运行在异步循环中
            await app.async_run()
        except Exception:
            # 万一崩溃，把堆栈信息打印到 adb logcat
            print("--- CRITICAL APP CRASH ---")
            print(traceback.format_exc())
        finally:
            # 确保退出时清理
            if hasattr(app, 'ble_client') and app.ble_client:
                await app.ble_client.disconnect()

    # 启动异步主循环
    try:
        asyncio.run(main_loop())
    except Exception as e:
        print(f"MAIN LOOP FAILED: {e}")
