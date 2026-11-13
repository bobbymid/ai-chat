import os
import json
import threading
import requests

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.modalview import ModalView
from kivy.uix.spinner import Spinner
from kivy.uix.behaviors import ButtonBehavior
from kivy.storage.jsonstore import JsonStore
from kivy.utils import platform

# ================== НАСТРОЙКИ ==================
API_KEY = "ВАШ_КЛЮЧ_OPENROUTER"   # <-- вставь сюда
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4o-mini"      # можно поменять на любую модель OpenRouter

if platform == "android":
    from android.permissions import request_permissions, Permission
    request_permissions([Permission.INTERNET])
    STORE_PATH = os.path.join(App.get_running_app().user_data_dir if App.get_running_app() else ".", "chats.json")
else:
    STORE_PATH = "chats.json"
# ===============================================


class ChatBubble(BoxLayout):
    """Сообщение в чате."""
    def __init__(self, text, is_user, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.padding = dp(8)
        self.spacing = dp(6)

        bubble = Label(
            text=text,
            markup=True,
            size_hint=(1, None),
            text_size=(Window.width * 0.75, None),
            halign="left",
            valign="top",
            padding=(dp(10), dp(10)),
            color=(1, 1, 1, 1),
        )

        # Автоподбор высоты
        bubble.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        bubble.bind(texture_size=lambda inst, val: setattr(self, "height", val[1] + dp(16)))

        # Обёртка для цвета
        bg = Button(
            size_hint=(None, None),
            background_normal="",
            background_color=(0.15, 0.45, 0.85, 1) if is_user else (0.22, 0.22, 0.22, 1),
            disabled=True,
        )
        bg.size = bubble.size
        bubble.bind(size=lambda inst, val: setattr(bg, "size", val))
        bubble.bind(pos=lambda inst, val: setattr(bg, "pos", val))

        if is_user:
            self.add_widget(Label(size_hint_x=None, width=0))
            self.add_widget(bubble)
        else:
            self.add_widget(bubble)
            self.add_widget(Label(size_hint_x=None, width=0))


class ChatScreen(Screen):
    def __init__(self, chat_id, **kwargs):
        super().__init__(**kwargs)
        self.chat_id = chat_id
        self.name = chat_id
        self.build_ui()
        self.load_messages()

    def build_ui(self):
        root = BoxLayout(orientation="vertical")

        # --- Верхняя панель ---
        top = BoxLayout(size_hint_y=None, height=dp(50), padding=(dp(6), dp(6)), spacing=dp(6))
        self.menu_btn = Button(text="☰", size_hint_x=None, width=dp(46),
                               background_normal="", background_color=(0.2, 0.2, 0.2, 1))
        self.menu_btn.bind(on_release=self.toggle_drawer)

        title = Label(text="Чат", bold=True, font_size="16sp")

        self.new_chat_btn = Button(text="+", size_hint_x=None, width=dp(46),
                                   background_normal="", background_color=(0.2, 0.2, 0.2, 1))
        self.new_chat_btn.bind(on_release=lambda *_: self.app_root.create_new_chat())

        top.add_widget(self.menu_btn)
        top.add_widget(title)
        top.add_widget(self.new_chat_btn)

        # --- Область сообщений ---
        self.scroll = ScrollView(do_scroll_x=False)
        self.messages_box = BoxLayout(orientation="vertical", spacing=dp(6),
                                      size_hint_y=None, padding=(dp(6), dp(6)))
        self.messages_box.bind(minimum_height=self.messages_box.setter("height"))
        self.scroll.add_widget(self.messages_box)

        # --- Поле ввода ---
        input_bar = BoxLayout(size_hint_y=None, height=dp(56), padding=(dp(6), dp(6)), spacing=dp(6))
        self.input = TextInput(
            hint_text="Сообщение...",
            multiline=False,
            size_hint_y=None,
            height=dp(44),
            background_color=(0.15, 0.15, 0.15, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(1, 1, 1, 1),
        )
        self.input.bind(on_text_validate=self.send_message)

        self.send_btn = Button(text="➤", size_hint_x=None, width=dp(52),
                               background_normal="", background_color=(0.15, 0.45, 0.85, 1))
        self.send_btn.bind(on_release=self.send_message)

        input_bar.add_widget(self.input)
        input_bar.add_widget(self.send_btn)

        root.add_widget(top)
        root.add_widget(self.scroll)
        root.add_widget(input_bar)
        self.add_widget(root)

    # ---------- Доступ к корневому приложению ----------
    @property
    def app_root(self):
        return App.get_running_app().root

    def toggle_drawer(self, *_):
        self.app_root.toggle_drawer()

    # ---------- Сообщения ----------
    def add_bubble(self, text, is_user):
        bubble = ChatBubble(text, is_user, size_hint_y=None)
        self.messages_box.add_widget(bubble)
        Clock.schedule_once(lambda dt: setattr(self.scroll, "scroll_y", 0), 0.05)
        return bubble

    def load_messages(self):
        self.messages_box.clear_widgets()
        msgs = self.app_root.get_messages(self.chat_id)
        for m in msgs:
            self.add_bubble(m["content"], m["role"] == "user")

    def send_message(self, *_):
        text = self.input.text.strip()
        if not text:
            return
        self.input.text = ""

        # добавляем сообщение пользователя
        self.app_root.append_message(self.chat_id, "user", text)
        self.add_bubble(text, True)

        # индикатор ожидания
        self.waiting = self.add_bubble("[i]Думаю...[/i]", False)

        threading.Thread(target=self.request_api, args=(text,), daemon=True).start()

    def request_api(self, user_text):
        history = self.app_root.get_messages(self.chat_id)
        payload = {
            "model": MODEL,
            "messages": [{"role": m["role"], "content": m["content"]} for m in history],
        }
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "ChatApp",
        }
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            data = r.json()
            if "choices" in data and data["choices"]:
                answer = data["choices"][0]["message"]["content"]
            else:
                answer = f"Ошибка: {json.dumps(data)[:400]}"
        except Exception as e:
            answer = f"Ошибка сети: {e}"
        Clock.schedule_once(lambda dt: self.show_answer(answer))

    @mainthread
    def show_answer(self, answer):
        # убираем индикатор
        if hasattr(self, "waiting") and self.waiting.parent:
            self.messages_box.remove_widget(self.waiting)
        self.app_root.append_message(self.chat_id, "assistant", answer)
        self.add_bubble(answer, False)


class ChatListItem(ButtonBehavior, BoxLayout):
    def __init__(self, chat_id, title, on_select, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(44)
        self.padding = (dp(8), 0)
        self.chat_id = chat_id
        self.on_select = on_select

        lbl = Label(text=title, halign="left", valign="middle",
                    text_size=(None, None), shorten=True, shorten_from="right")
        lbl.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(lbl)

    def on_release(self):
        self.on_select(self.chat_id)


class Drawer(BoxLayout):
    """Выдвижной список чатов."""
    def __init__(self, app_root, **kwargs):
        super().__init__(**kwargs)
        self.app_root = app_root
        self.orientation = "vertical"
        self.size_hint_x = 0.75
        self.width = Window.width * 0.75
        self.x = -self.width
        self.background_color = (0.12, 0.12, 0.12, 1)

        # Заголовок + кнопка нового чата
        head = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(8), dp(4)), spacing=dp(6))
        head.add_widget(Label(text="Чаты", bold=True, font_size="18sp"))
        new_btn = Button(text="+ Новый", size_hint_x=None, width=dp(100),
                         background_normal="", background_color=(0.15, 0.45, 0.85, 1))
        new_btn.bind(on_release=lambda *_: self.app_root.create_new_chat())
        head.add_widget(new_btn)
        self.add_widget(head)

        # Список чатов
        self.scroll = ScrollView()
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2),
                                  padding=(dp(4), dp(4)))
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.scroll.add_widget(self.list_box)
        self.add_widget(self.scroll)

        self.refresh()

    def refresh(self):
        self.list_box.clear_widgets()
        for cid, chat in self.app_root.chats.items():
            item = ChatListItem(cid, chat["title"], self.app_root.select_chat)
            self.list_box.add_widget(item)


class RootWidget(BoxLayout):
    """Главный контейнер: менеджер экранов + drawer поверх."""
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.store = JsonStore(STORE_PATH)
        self.chats = {}
        self.load_data()

        self.sm = ScreenManager()
        self.add_widget(self.sm)

        # Drawer как абсолютный виджет поверх
        self.drawer = Drawer(self)
        self.add_widget(self.drawer)
        self.drawer.opacity = 0
        self.drawer.disabled = True

        self.drawer_open = False

        # Создаём первый чат или открываем существующий
        if not self.chats:
            self.create_new_chat()
        else:
            first = next(iter(self.chats))
            self.open_chat_screen(first)

    # ---------- Хранилище ----------
    def load_data(self):
        try:
            if self.store.exists("data"):
                self.chats = self.store.get("data")["chats"]
        except Exception:
            self.chats = {}

    def save_data(self):
        try:
            self.store.put("data", chats=self.chats)
        except Exception as e:
            print("save error", e)

    # ---------- Чаты ----------
    def create_new_chat(self):
        cid = f"chat_{len(self.chats) + 1}_{int(Clock.get_time() * 1000) % 100000}"
        title = f"Чат {len(self.chats) + 1}"
        self.chats[cid] = {"title": title, "messages": []}
        self.save_data()
        self.drawer.refresh()
        self.open_chat_screen(cid)
        self.close_drawer()

    def select_chat(self, chat_id):
        self.open_chat_screen(chat_id)
        self.close_drawer()

    def open_chat_screen(self, chat_id):
        # Удаляем старый экран
        for scr in list(self.sm.screens):
            self.sm.remove_widget(scr)
        screen = ChatScreen(chat_id=chat_id, name=chat_id)
        self.sm.add_widget(screen)
        self.sm.current = chat_id

    def get_messages(self, chat_id):
        return self.chats.get(chat_id, {}).get("messages", [])

    def append_message(self, chat_id, role, content):
        if chat_id not in self.chats:
            return
        self.chats[chat_id]["messages"].append({"role": role, "content": content})
        self.save_data()

    # ---------- Drawer ----------
    def toggle_drawer(self, *_):
        if self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self):
        self.drawer.disabled = False
        self.drawer.opacity = 1
        from kivy.animation import Animation
        Animation(x=0, duration=0.2).start(self.drawer)
        self.drawer_open = True

    def close_drawer(self, *_):
        from kivy.animation import Animation
        anim = Animation(x=-self.drawer.width, duration=0.2)
        anim.bind(on_complete=lambda *a: self._finish_close())
        anim.start(self.drawer)
        self.drawer_open = False

    def _finish_close(self):
        self.drawer.opacity = 0
        self.drawer.disabled = True


class ChatApp(App):
    def build(self):
        self.title = "AI Chat"
        Window.clearcolor = (0.09, 0.09, 0.09, 1)
        return RootWidget()


if __name__ == "__main__":
    ChatApp().run()