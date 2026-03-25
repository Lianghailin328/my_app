[app]

# (str) Title of your application
title = DishwasherApp

# (str) Package name
package.name = dishwasher

# (str) Package domain (needed for android/ios packaging)
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,otf

# (str) Application versioning (method 1)
version = 0.1

# (list) Application requirements
# ⚠️ 这里修改了 jnius 为 pyjnius，并固定了 kivy 版本保证环境稳定
requirements = python3,kivy==2.3.0,bleak,android,pyjnius

# (list) Supported orientations
orientation = portrait

#
# OSX Specific
#
osx.python_version = 3
osx.kivy_version = 1.9.1

#
# Android specific
#
fullscreen = 0

# (list) Permissions
# ⚠️ 包含 Android 11/12+ 蓝牙开发必备的精准定位与 SCAN 权限！
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,INTERNET

# (list) features (adds uses-feature -tags to manifest)
android.features = android.hardware.bluetooth_le

# (int) Target Android API, should be as high as possible.
# ⚠️ 改为 31，作为蓝牙 BLE 支持的最佳稳定版本
android.api = 31

# (int) Minimum API your APK / AAB will support.
android.minapi = 24

# (int) Android NDK API to use. This is the minimum API your app will support, it should usually match android.minapi.
android.ndk_api = 24

# (bool) If True, then automatically accept SDK license
android.accept_sdk_license = True

# (bool) Enable AndroidX support. Enable when 'android.gradle_dependencies'
android.enable_androidx = True

# (list) The Android archs to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
# ⚠️ 这里只保留 64 位的主流架构，可以让你在 Github Actions 的编译时间减半，且极大减少 API 对齐报错
android.archs = arm64-v8a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

#
# Python for android (p4a) specific
#

# Control passing the --use-setup-py vs --ignore-setup-py to p4a
# ⚠️ 关键修改：取消注释并设为 False，这是很多包含 Cython 架构（如 bleak）库编译失败的元凶
p4a.setup_py = False

#
# iOS specific
#
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master
ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.10.0
ios.codesign.allowed = false

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
