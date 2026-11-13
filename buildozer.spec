[app]
title = AI Chat
package.name = aichat
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0
requirements = python3,kivy,requests,urllib3,charset-normalizer,idna,certifi,openssl

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = True