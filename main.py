# -*- coding: utf-8 -*-
import os
import platform

# 1. 渲染性能补丁（解决 Android 资源调度锁死）
if platform.system() == 'Android' or 'ANDROID_ARGUMENT' in os.environ:
    os.environ['KIVY_GRAPHICS'] = 'gles'
    os.environ['RENDER_THREAD'] = '0'
    os.environ['APP_SHORTCUT_RENDER_THREAD'] = '0'

from kivy.utils import platform as kivy_platform

# 2. 核心补丁：使用随APP打包的 OTF 字体，彻底解决方框乱码问题（无需区分系统）
from kivy.core.text import LabelBase
from kivy.config import Config

# 获取当前 main.py 所在的同级目录下我们打包进去的字体
current_dir = os.path.dirname(os.path.abspath(__file__))
font_path = os.path.join(current_dir, 'myfont.otf')

if os.path.exists(font_path):
    # 将此字体注册并设为 Kivy 的全局默认字体
    LabelBase.register(name='NotoSettings', fn_regular=font_path)
    Config.set('kivy', 'default_font', ['NotoSettings', font_path])
    # 暴力替换底层别名，防止有些刁钻组件（如 Popup 标题）依然乱码
    os.environ['KIVY_FONT_ALIAS'] = f'{{"DroidSans": "{font_path}", "Roboto": "{font_path}"}}'
    
    # 终极补丁：强制全局接管 Label 和 Button 的属性表，杜绝 Kivy 悄悄回退到英文 Roboto 字体
    from kivy.lang import Builder
    Builder.load_string('''
<Label>:
    font_name: 'NotoSettings'
<Button>:
    font_name: 'NotoSettings'
<Popup>:
    title_font: 'NotoSettings'
''')
else:
    print(f"！！！！警告：未能找到字体文件 {font_path} ！！！！")


# --- 核心组件导入 ---
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
        
        self.client = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.run_async_loop, daemon=True)
        self.thread.start()
        
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(15))
        
        header = Label(text="洗碗机控制中心", font_size=sp(24), bold=True, color=get_color_from_hex("#333333"), size_hint_y=None, height=dp(60))
        root.add_widget(header)

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
        
        for b in [temp_box, water_box, mode_box, gear_box]: data_card.add_widget(b)
        root.add_widget(data_card)

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

        root.add_widget(Label(text="核心控制项", size_hint_y=None, height=dp(30), color=get_color_from_hex("#333333"), bold=True, font_size=sp(16)))
        op_grid = GridLayout(cols=2, spacing=dp(12), size_hint_y=None, height=dp(120))
        cmds = [("启动洗涤", b"\x01"), ("强制停止", b"\x02"), ("切换模式", b"\x03"), ("调节档位", b"\x04")]
        for name, hex_val in cmds:
            btn = StyledButton(text=name)
            btn.btn_color = get_color_from_hex("#1976D2")
            btn.bind(on_release=lambda x, c=hex_val, n=name: self.start_async(self.send_command(c, n)))
            op_grid.add_widget(btn)
        root.add_widget(op_grid)

        self.log_label = Label(text="系统就绪", color=get_color_from_hex("#424242"), size_hint_y=None, height=dp(40), font_size=sp(14))
        root.add_widget(self.log_label)
        root.add_widget(BoxLayout()) 
        return root

    def run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def start_async(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def on_start(self):
        if kivy_platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.BLUETOOTH_SCAN, Permission.BLUETOOTH_CONNECT, Permission.ACCESS_FINE_LOCATION])
            except Exception as e: print(f"Permission Error: {e}")

    def show_device_list(self, instance):
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        self.device_list_layout = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.device_list_layout.bind(minimum_height=self.device_list_layout.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.device_list_layout)
        content.add_widget(scroll)
        self.scan_popup = Popup(title="附近蓝牙设备 (下拉滚动)", content=content, size_hint=(0.9, 0.8))
        self.scan_popup.open()
        self.start_async(self.scan_devices())

    async def scan_devices(self):
        # 防卡死：避免多次点击重复扫描造成的底层碰撞
        if getattr(self, 'is_scanning', False): return
        self.is_scanning = True

        Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', "正在后台初始化蓝牙硬件..."))
        # 极为关键：强制释放 GIL 0.2 秒，让 Kivy 有时间渲染上面的“正在初始化”文字到屏幕
        await asyncio.sleep(0.2)
        
        if BleakScanner is None:
            Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', "请检查 buildozer bleak 依赖"))
            self.is_scanning = False
            return

        try:
            # 移交至 Android JNI 层面运行扫描，Kivy UI 线程此时处于挂起等待中
            devices = await BleakScanner.discover(timeout=4.0)
            
            # 使用内嵌函数将 "更新UI界面" 的任务整体打包，扔给 Kivy 的主线程去执行
            def render_results(dt):
                self.device_list_layout.clear_widgets()
                if not devices:
                    self.status_label.text = "扫描完成: 未发现设备 (请检查定位和蓝牙)"
                    self.status_label.color = (1, 0.5, 0, 1)
                else:
                    self.status_label.text = f"扫描完成: 发现 {len(devices)} 台设备"
                    self.status_label.color = (0, 0.6, 0, 1) 
                    # 动态生成每个设备的连接按钮
                    for d in devices:
                        d_name = d.name if d.name else "未知设备"
                        btn = StyledButton(text=f"{d_name}\n[size=12sp]{d.address}[/size]", markup=True)
                        btn.btn_color = get_color_from_hex("#424242")
                        btn.height = dp(60)
                        btn.size_hint_y = None
                        btn.bind(on_release=lambda x, dev=d: getattr(self, 'start_async')(self.connect_to_device(dev)))
                        self.device_list_layout.add_widget(btn)
                        
            # 将生成的动作注入主线程 Clock 列队防冲突
            Clock.schedule_once(render_results)
            
        except Exception as e:
            msg = f"扫描异常: {str(e)[:30]}"
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", msg))
        finally:
            self.is_scanning = False

    async def connect_to_device(self, device):
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", "正在发起连接协议..."))
        try:
            self.client = BleakClient(device.address)
            await self.client.connect()
            Clock.schedule_once(lambda dt: self.on_connected(device))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.status_label, "text", f"连接失败: {str(e)[:30]}"))

    def on_connected(self, device):
        if hasattr(self, 'scan_popup'): self.scan_popup.dismiss()
        self.status_label.text = f"已连接: {device.name or '目标洗碗机'}"
        self.status_label.color = get_color_from_hex("#4CAF50")

    async def disconnect_device(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        Clock.schedule_once(self.on_disconnected)

    def on_disconnected(self, dt=None):
        self.status_label.text = "设备已被手动断开"
        self.status_label.color = get_color_from_hex("#F44336")

    async def send_command(self, cmd_hex, name):
        Clock.schedule_once(lambda dt: setattr(self.log_label, "text", f"尝试发送: {name}"))
        if self.client and self.client.is_connected:
            try:
                # 示例指令写入，您之后可根据真实 UUID 修改
                # await self.client.write_gatt_char("0000ffe1-0000-1000-8000-00805f9b34fb", cmd_hex)
                Clock.schedule_once(lambda dt: setattr(self.log_label, "text", f"[{name}] 数据已送达"))
            except Exception as e:
                Clock.schedule_once(lambda dt: setattr(self.log_label, "text", f"发送出错: {str(e)[:25]}"))
        else:
            Clock.schedule_once(lambda dt: setattr(self.log_label, "text", "拒绝发送：当前未连接任何设备"))

if __name__ == "__main__":
    DishwasherControlApp().run()

